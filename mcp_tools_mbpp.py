"""MBPP MCP tools: execute only the code and tests supplied by the caller."""

import argparse
import asyncio
import json
import shutil
from uuid import uuid4

from fastmcp import FastMCP


mcp = FastMCP("Agent Smith - MBPP")
IMAGE = "python:3.10-slim"
TIMEOUT_SECONDS = 30
MEMORY_MB = 128
MAX_OUTPUT_BYTES = 8192

_DRIVER = """
import json
import sys
import traceback

payload = json.load(sys.stdin)
namespace = {"__name__": "__main__"}
try:
    exec(compile(payload["code"], "<solution>", "exec"), namespace)
    for index, test in enumerate(payload["test_list"], 1):
        exec(compile(test, "<test %d>" % index, "exec"), namespace)
except BaseException:
    traceback.print_exc()
    sys.exit(1)
sys.stdout.write("\\n" + sys.argv[1] + "\\n")
sys.stdout.flush()
"""


async def _docker(*arguments: str) -> tuple[int, str]:
    """Run a bounded Docker control command, never a shell command."""
    process = await asyncio.create_subprocess_exec(
        "docker", *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode is not None
        return process.returncode, output.decode("utf-8", errors="replace")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _read_output(
    stream: asyncio.StreamReader, marker: bytes,
) -> tuple[str, bool]:
    """Drain output without retaining an unbounded amount in server memory."""
    prefix = bytearray()
    tail = b""
    total = 0
    completed = False
    while chunk := await stream.read(4096):
        total += len(chunk)
        room = MAX_OUTPUT_BYTES + len(marker) - len(prefix)
        prefix.extend(chunk[:max(0, room)])
        window = tail + chunk
        completed = completed or marker in window
        tail = window[-len(marker):]
    # Docker may deliver stderr after the stdout completion marker.
    data = bytes(prefix).replace(marker, b"")
    output = data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace").strip()
    if total - (len(marker) if completed else 0) > MAX_OUTPUT_BYTES:
        output += "\n[Output truncated to %d bytes.]" % MAX_OUTPUT_BYTES
    return output, completed


async def _execute(
    name: str, payload: bytes, marker: bytes,
) -> tuple[str, bool, bool]:
    process = await asyncio.create_subprocess_exec(
        "docker", "start", "--attach", "--interactive", name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    writer = process.stdin
    reader = asyncio.create_task(_read_output(process.stdout, marker))

    async def execute() -> None:
        writer.write(payload)
        await writer.drain()
        writer.close()
        await process.wait()

    timed_out = False
    try:
        await asyncio.wait_for(execute(), TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        writer.close()
        if process.returncode is None:
            process.kill()
            await process.wait()
        output, completed = await reader
    return output, completed, timed_out


@mcp.tool()
async def run_tests(code: str, test_list: list[str]) -> str:
    """Test Python code against the supplied assertions in isolated Docker.

    Include required imports in code. Returns a JSON string containing
    success (all tests completed and passed) and output (stdout/errors).
    No benchmark dataset or hidden tests are accessed.
    """
    if not code.strip() or not test_list or any(
        not test.strip() for test in test_list
    ):
        return json.dumps({
            "success": False,
            "output": "Code and at least one test must be non-empty.",
        })
    if shutil.which("docker") is None:
        return json.dumps({
            "success": False,
            "output": "Docker CLI is required and must be on PATH.",
        })

    name = "agent-smith-mbpp-" + uuid4().hex
    token = "__MBPP_COMPLETED_" + uuid4().hex + "__"
    marker = ("\n" + token + "\n").encode()
    payload = json.dumps({"code": code, "test_list": test_list}).encode()
    success = False
    output = ""
    try:
        status, output = await _docker(
            "create", "--pull=never", "--name", name,
            "--label", "agent-smith.mbpp=true", "--interactive", "--init",
            "--network", "none", "--read-only", "--user", "65534:65534",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", f"{MEMORY_MB}m",
            "--memory-swap", f"{MEMORY_MB}m",
            "--pids-limit", "64", "--cpus", "1", "--log-driver", "none",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",
            "--workdir", "/tmp", IMAGE,
            "python", "-I", "-B", "-u", "-c", _DRIVER, token,
        )
        if status:
            output = (output.strip() +
                      f"\nStart Docker. Run: docker pull {IMAGE}")
        else:
            output, completed, timed_out = await _execute(
                name, payload, marker,
            )
            if timed_out:
                output += f"\nExecution timed out after {TIMEOUT_SECONDS}s."
            else:
                status, state = await _docker(
                    "inspect", "--format",
                    "{{.State.ExitCode}} {{.State.OOMKilled}}", name,
                )
                if status:
                    output += "\nCannot inspect execution: " + state.strip()
                elif state.strip().endswith(" true"):
                    output += f"\nMemory limit exceeded ({MEMORY_MB} MiB)."
                elif state.strip() == "0 false" and completed:
                    success = True
                    if not output:
                        output = f"All {len(test_list)} tests passed."
                elif not output:
                    output = "Execution ended before all tests passed."
    except (OSError, asyncio.TimeoutError) as error:
        output = f"Docker execution failed: {error}"
    finally:
        try:
            status, cleanup = await _docker("rm", "--force", name)
            if status and "No such container" not in cleanup:
                success = False
                output += "\nContainer cleanup failed: " + cleanup.strip()
        except (OSError, asyncio.TimeoutError) as error:
            success = False
            output += f"\nContainer cleanup failed: {error}"
    return json.dumps({"success": success, "output": output})


@mcp.resource("agent://mbpp/task")
def task_resource() -> dict[str, str]:
    """Server metadata; the caller supplies task code and public tests."""
    return {"image": IMAGE, "tool": "run_tests(code, test_list)"}


@mcp.prompt()
def mbpp_solver() -> str:
    return (
        "Solve the MBPP task. Include required imports in your Python code, "
        "then call run_tests(code=code, test_list=the_public_assertions). "
        "Use the real test feedback to improve the solution. "
        "When finished, call the sandbox's final_answer(solution_code)."
    )


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main() -> None:
    global TIMEOUT_SECONDS, MEMORY_MB
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "http"),
                        default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=_positive_int, default=8000)
    parser.add_argument("--timeout-seconds", type=_positive_int, default=30)
    parser.add_argument("--memory-mb", type=_positive_int, default=128)
    arguments = parser.parse_args()
    TIMEOUT_SECONDS = arguments.timeout_seconds
    MEMORY_MB = arguments.memory_mb
    if arguments.transport == "http":
        mcp.run(transport="http", host=arguments.host, port=arguments.port,
                show_banner=False)
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
