"""MBPP candidate execution boundary shared with the sandbox configuration."""

import asyncio
import json
from pathlib import Path
import os
import shutil
import signal
import sys
import tempfile
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.config_model import SandboxConfig


ROOT = Path(__file__).resolve().parents[1]


class MBPPExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    code: str = Field(min_length=1)
    test_list: list[str] = Field(min_length=1)
    test_imports: list[str] = Field(default_factory=list)
    config: SandboxConfig

    @model_validator(mode="after")
    def require_nonblank_input(self) -> "MBPPExecutionRequest":
        if not self.code.strip() or any(
            not text.strip() for text in self.test_list + self.test_imports
        ):
            raise ValueError(
                "Code, tests and import entries must be non-empty.")
        return self


class MBPPExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    success: bool
    output: str


def execution_result(
    success: bool, output: str, config: SandboxConfig, diagnostic: str = "",
) -> MBPPExecutionResult:
    """Apply the byte budget to every result, including preflight errors."""
    limit = config.max_output_bytes
    data = output.encode("utf-8", "replace")
    if len(data) > limit and not diagnostic:
        diagnostic = "Output truncated."
    if diagnostic:
        suffix = ("[" + diagnostic + "]").encode("utf-8", "replace")
        room = max(0, limit - len(suffix) - 1)
        output = data[:room].decode("utf-8", "ignore").rstrip()
        data = ((output.encode() + b"\n") if output else b"") + suffix
    return MBPPExecutionResult(
        success=success, output=data[:limit].decode("utf-8", "ignore").strip(),
    )


async def execute_mbpp(request: MBPPExecutionRequest) -> MBPPExecutionResult:
    """Execute in a fresh offline Deno process, never in the MCP process."""
    deno = shutil.which("deno")
    if deno is None:
        return execution_result(
            False, "MBPP setup error: Deno was not found on PATH. "
            "No code or tests were executed. Install the locked dependencies "
            "with `make install` and launch this server with "
            "`uv run python mcp_tools_mbpp.py`, or install Deno on PATH.",
            request.config,
        )
    assets = ROOT / "node_modules/pyodide"
    missing = [name for name in (
        "pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm",
        "pyodide.asm.data", "pyodide_py.tar", "repodata.json",
    ) if not (assets / name).is_file()]
    if missing:
        return execution_result(
            False, "MBPP setup error: the local Pyodide installation is "
            "missing or incomplete. Missing files: " + ", ".join(missing) +
            ". No code or tests were executed. From the project directory "
            f"({ROOT}), run `make install` (installs Pyodide using "
            "`npm ci --ignore-scripts`), then retry the call.",
            request.config,
        )
    if sys.platform not in ("linux", "darwin"):
        return execution_result(
            False, "MBPP setup error: memory monitoring requires Linux or "
            "macOS. No code or tests were executed. Run the server on a "
            "supported operating system.",
            request.config,
        )

    config = request.config
    token = "__MBPP_" + uuid4().hex + "__"
    payload = request.model_dump()
    payload["token"] = token
    prefix = bytearray()
    completed = False
    truncated = False
    failure = ""
    process: asyncio.subprocess.Process | None = None
    readers: list[asyncio.Task[None]] = []
    monitor: asyncio.Task[None] | None = None

    def retain(data: bytes) -> None:
        nonlocal truncated
        room = config.max_output_bytes - len(prefix)
        prefix.extend(data[:max(0, room)])
        truncated = truncated or len(data) > room

    async def read_output(
        stream: asyncio.StreamReader, framed: bool = False,
    ) -> None:
        nonlocal completed
        marker = ("\n" + token + "\n").encode()
        pending = b""
        while chunk := await stream.read(4096):
            if not framed:
                retain(chunk)
                continue
            pending += chunk
            if marker in pending:
                completed = True
                pending = pending.replace(marker, b"")
            room = max(0, len(pending) - len(marker) + 1)
            retain(pending[:room])
            pending = pending[room:]
        retain(pending)

    async def monitor_memory(pid: int) -> None:
        nonlocal failure
        # shortcut: RSS sampling can miss spikes; use OS limits for a hard cap.
        while True:
            check = await asyncio.create_subprocess_exec(
                "ps", "-o", "rss=", "-p", str(pid),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                rss, _ = await check.communicate()
            finally:
                if check.returncode is None:
                    check.kill()
                    await check.wait()
            if check.returncode or not rss.strip():
                assert process is not None
                if process.returncode is not None:
                    return
                raise OSError("ps failed or returned no memory measurement")
            if int(rss) > config.max_memory_mb * 1024:
                failure = "Memory limit exceeded (%s MiB)." % (
                    config.max_memory_mb)
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return
            await asyncio.sleep(0.02)

    try:
        with tempfile.TemporaryDirectory(prefix="mbpp-") as directory:
            process = await asyncio.create_subprocess_exec(
                deno, "run", "--no-prompt", "--no-config", "--no-lock",
                "--cached-only", "--no-remote", "--node-modules-dir=manual",
                "--allow-read=" + str(ROOT / "node_modules") + "," +
                str(ROOT / "runtime"),
                "--allow-env=WS_NO_BUFFER_UTIL,WS_NO_UTF_8_VALIDATE",
                "--deny-net", "--deny-run", "--deny-write", "--deny-ffi",
                "--deny-sys", "--deny-import",
                f"--v8-flags=--wasm-max-mem-pages={config.max_memory_mb * 16},"
                f"--max-old-space-size={config.max_memory_mb}",
                str(ROOT / "runtime/mbpp.mjs"),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=directory, start_new_session=True,
                env={"HOME": directory, "PATH": os.defpath,
                     "DENO_NO_UPDATE_CHECK": "1", "NO_COLOR": "1"},
            )
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            readers.append(asyncio.create_task(read_output(process.stderr)))

            async def supervise_memory() -> None:
                nonlocal failure
                assert process is not None
                try:
                    await monitor_memory(process.pid)
                except (OSError, ValueError) as error:
                    failure = f"Memory monitoring failed: {error}"
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

            monitor = asyncio.create_task(supervise_memory())

            async def initialize() -> bytes:
                assert process is not None and process.stdin is not None
                assert process.stdout is not None
                process.stdin.write(json.dumps(payload).encode())
                await process.stdin.drain()
                process.stdin.close()
                return await process.stdout.readline()

            # Startup has its own watchdog; candidate time starts at ready.
            ready = await asyncio.wait_for(initialize(), 30)
            if ready != (token + "\n").encode():
                retain(ready)
                failure = failure or "Runtime failed before execution."
            readers.append(asyncio.create_task(read_output(
                process.stdout, framed=True,
            )))
            try:
                await asyncio.wait_for(
                    process.wait(), config.max_execution_time_seconds,
                )
            except asyncio.TimeoutError:
                failure = ("Execution timed out after %ss; "
                           "output is partial." %
                           config.max_execution_time_seconds)
    except asyncio.TimeoutError:
        failure = ("MBPP runtime initialization timed out after 30s. "
                   "No code or tests were executed.")
    except (OSError, ValueError) as error:
        failure = failure or f"Runtime execution failed: {error}"
    finally:
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        if monitor is not None:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        await asyncio.gather(*readers, return_exceptions=True)

    output = bytes(prefix).decode("utf-8", "replace")
    success = (not failure and completed and process is not None and
               process.returncode == 0)
    diagnostic = " ".join(text for text in (
        failure, "Output truncated." if truncated else "",
    ) if text)
    if (not success and not diagnostic and process is not None and
            not output.strip()):
        diagnostic = (f"MBPP runtime exited with status {process.returncode} "
                      "before confirming that all tests completed. "
                      "The result is a failure, not a passing test run.")
    if not output.strip() and not diagnostic:
        output = (f"All {len(request.test_list)} tests passed." if success else
                  "Execution ended before all tests passed.")
    return execution_result(success, output, config, diagnostic)
