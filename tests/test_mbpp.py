"""MBPP result, container isolation, cleanup, and real MCP transport tests."""

import asyncio
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import AsyncMock, patch

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from mcp.types import TextContent

import mcp_tools_mbpp as mbpp


ROOT = Path(__file__).resolve().parents[1]


def decode_result(text: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(text)
    assert isinstance(result["success"], bool)
    assert isinstance(result["output"], str)
    return result


class UnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_inputs_do_not_start_docker(self) -> None:
        with patch.object(mbpp, "_docker", new_callable=AsyncMock) as docker:
            for code, tests in [("", ["assert True"]), ("pass", []),
                                ("pass", [" "])]:
                result = decode_result(await mbpp.run_tests(code, tests))
                self.assertFalse(result["success"])
            docker.assert_not_called()

    async def test_missing_docker_is_a_result_not_a_crash(self) -> None:
        with patch.object(mbpp.shutil, "which", return_value=None):
            result = decode_result(await mbpp.run_tests("pass", ["pass"]))
        self.assertFalse(result["success"])
        self.assertIn("Docker CLI", result["output"])

    async def test_daemon_failure_is_reported(self) -> None:
        with (
            patch.object(mbpp.shutil, "which", return_value="/bin/docker"),
            patch.object(mbpp, "_docker", new_callable=AsyncMock) as docker,
        ):
            docker.side_effect = [(1, "daemon unavailable"),
                                  (1, "No such container")]
            result = decode_result(await mbpp.run_tests("pass", ["pass"]))
        self.assertFalse(result["success"])
        self.assertIn("daemon unavailable", result["output"])
        self.assertEqual(docker.call_args.args[0], "rm")

    async def test_cleanup_failure_cannot_report_success(self) -> None:
        with (
            patch.object(mbpp.shutil, "which", return_value="/bin/docker"),
            patch.object(mbpp, "_docker", new_callable=AsyncMock) as docker,
            patch.object(mbpp, "_execute", new_callable=AsyncMock) as run,
        ):
            docker.side_effect = [(0, "container"), (0, "0 false"),
                                  (1, "permission denied")]
            run.return_value = ("", True, False)
            result = decode_result(await mbpp.run_tests("pass", ["pass"]))
        self.assertFalse(result["success"])
        self.assertIn("cleanup failed", result["output"])

    async def test_bounded_output_keeps_completion(self) -> None:
        stream = asyncio.StreamReader()
        marker = b"\nCOMPLETED\n"
        stream.feed_data(b"x" * 100_000 + marker)
        stream.feed_eof()
        output, completed = await mbpp._read_output(stream, marker)
        self.assertTrue(completed)
        self.assertIn("truncated", output)
        self.assertLess(len(output), mbpp.MAX_OUTPUT_BYTES + 100)

    async def test_completion_can_precede_delayed_stderr(self) -> None:
        stream = asyncio.StreamReader()
        marker = b"\nCOMPLETED\n"
        stream.feed_data(b"x" * 4093 + marker + b"stderr")
        stream.feed_eof()
        output, completed = await mbpp._read_output(stream, marker)
        self.assertTrue(completed)
        self.assertTrue(output.endswith("stderr"))
        self.assertNotIn("COMPLETED", output)


class DockerCase(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("docker") is None:
            raise unittest.SkipTest("Docker CLI unavailable")
        check = subprocess.run(
            ["docker", "image", "inspect", mbpp.IMAGE],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10,
        )
        if check.returncode:
            raise unittest.SkipTest(
                f"Start Docker and run: docker pull {mbpp.IMAGE}"
            )

    def containers(self) -> set[str]:
        output = subprocess.check_output(
            ["docker", "ps", "--all", "--quiet", "--filter",
             "label=agent-smith.mbpp=true"], text=True, timeout=10,
        )
        return set(output.split())

    async def asyncSetUp(self) -> None:
        self.before = self.containers()
        timeout = patch.object(mbpp, "TIMEOUT_SECONDS", 5)
        timeout.start()
        self.addCleanup(timeout.stop)

    async def asyncTearDown(self) -> None:
        self.assertEqual(self.containers(), self.before,
                         "MBPP calls leaked a Docker container")


class DockerTests(DockerCase):
    async def test_solution_imports_stdout_and_stderr(self) -> None:
        result = decode_result(await mbpp.run_tests(
            "import math, sys\n"
            "print('stdout')\nprint('stderr', file=sys.stderr)\n"
            "def root(x): return math.sqrt(x)",
            ["assert root(9) == 3", "assert root(0) == 0"],
        ))
        self.assertTrue(result["success"], result["output"])
        self.assertIn("stdout", result["output"])
        self.assertIn("stderr", result["output"])

    async def test_failed_assertion_syntax_and_runtime_error(self) -> None:
        for code, tests, error in [
            ("def solve(): return 1", ["assert solve() == 2"],
             "AssertionError"),
            ("def solve(:", ["assert True"], "SyntaxError"),
            ("raise ValueError('broken')", ["assert True"], "ValueError"),
        ]:
            with self.subTest(error=error):
                result = decode_result(await mbpp.run_tests(code, tests))
                self.assertFalse(result["success"])
                self.assertIn(error, result["output"])

    async def test_premature_zero_exit_cannot_pass(self) -> None:
        for code in ["raise SystemExit(0)", "import os\nos._exit(0)"]:
            with self.subTest(code=code):
                result = decode_result(await mbpp.run_tests(
                    code, ["assert False, 'must not be skipped'"],
                ))
                self.assertFalse(result["success"])

    async def test_timeout_returns_partial_output_and_removes_container(
        self,
    ) -> None:
        with patch.object(mbpp, "TIMEOUT_SECONDS", 1):
            result = decode_result(await mbpp.run_tests(
                "print('partial', flush=True)\nwhile True: pass",
                ["assert True"],
            ))
        self.assertFalse(result["success"])
        self.assertIn("partial", result["output"])
        self.assertIn("timed out", result["output"])

    async def test_memory_limit(self) -> None:
        result = decode_result(await mbpp.run_tests(
            "allocation = bytearray(512 * 1024 * 1024)", ["assert True"],
        ))
        self.assertFalse(result["success"])
        self.assertIn("Memory limit exceeded", result["output"])

    async def test_outbound_network_is_blocked(self) -> None:
        result = decode_result(await mbpp.run_tests(
            "import socket\n"
            "socket.create_connection(('1.1.1.1', 80), timeout=1)",
            ["assert True"],
        ))
        self.assertFalse(result["success"])
        self.assertIn("Error", result["output"])

    async def test_no_host_mounts_and_non_root_execution(self) -> None:
        with tempfile.NamedTemporaryFile() as host_file:
            code = (
                "import os\nfrom pathlib import Path\n"
                f"assert not Path({host_file.name!r}).exists()\n"
                "assert not Path('/var/run/docker.sock').exists()\n"
                "assert os.getuid() == 65534\n"
                "Path('/tmp/scratch').write_text('allowed')"
            )
            result = decode_result(await mbpp.run_tests(
                code, ["assert Path('/tmp/scratch').read_text() == 'allowed'"],
            ))
        self.assertTrue(result["success"], result["output"])
        denied = decode_result(await mbpp.run_tests(
            "open('/etc/mbpp-test', 'w')", ["assert True"],
        ))
        self.assertFalse(denied["success"])

    async def test_output_flood_still_passes(self) -> None:
        result = decode_result(await mbpp.run_tests(
            "print('x' * 100_000)", ["assert True"],
        ))
        self.assertTrue(result["success"], result["output"])
        self.assertIn("truncated", result["output"])
        self.assertLess(len(result["output"]), mbpp.MAX_OUTPUT_BYTES + 100)

    async def test_concurrent_calls_do_not_share_files(self) -> None:
        code = ("from pathlib import Path\n"
                "assert not Path('/tmp/previous').exists()\n"
                "Path('/tmp/previous').write_text('private')")
        results = await asyncio.gather(
            mbpp.run_tests(code, ["assert True"]),
            mbpp.run_tests(code, ["assert True"]),
        )
        self.assertTrue(all(decode_result(r)["success"] for r in results))

    async def test_cancellation_removes_container(self) -> None:
        task = asyncio.create_task(mbpp.run_tests(
            "while True: pass", ["assert True"],
        ))
        try:
            deadline = asyncio.get_running_loop().time() + 5
            while self.containers() == self.before:
                if asyncio.get_running_loop().time() > deadline:
                    self.fail("Test container did not start")
                await asyncio.sleep(0.05)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


class TransportTests(DockerCase):
    async def check_client(self, client: Client[Any]) -> None:
        async with client:
            tools = await client.list_tools()
            self.assertEqual([tool.name for tool in tools], ["run_tests"])
            self.assertEqual(set(tools[0].input_schema["required"]),
                             {"code", "test_list"})
            self.assertEqual(len(await client.list_resources()), 1)
            self.assertEqual(len(await client.list_prompts()), 1)
            for expected in [False, True]:
                answer = 42 if expected else 0
                response = await client.call_tool("run_tests", {
                    "code": "def solve(): return 42",
                    "test_list": [f"assert solve() == {answer}"],
                })
                self.assertFalse(response.is_error)
                content = response.content[0]
                assert isinstance(content, TextContent)
                result = decode_result(content.text)
                self.assertEqual(result["success"], expected, result["output"])

    async def test_stdio(self) -> None:
        transport = StdioTransport(
            command=sys.executable,
            args=[str(ROOT / "mcp_tools_mbpp.py"), "--timeout-seconds", "5"],
            cwd=str(ROOT),
        )
        await self.check_client(Client(transport))

    async def test_streamable_http(self) -> None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "mcp_tools_mbpp.py"),
            "--transport", "http", "--port", str(port),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            deadline = asyncio.get_running_loop().time() + 10
            while True:
                try:
                    _, writer = await asyncio.open_connection(
                        "127.0.0.1", port,
                    )
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    if process.returncode is not None:
                        self.fail("HTTP server exited before becoming ready")
                    if asyncio.get_running_loop().time() > deadline:
                        self.fail("HTTP server did not become ready")
                    await asyncio.sleep(0.05)
            await self.check_client(Client(f"http://127.0.0.1:{port}/mcp"))
        finally:
            if process.returncode is None:
                process.terminate()
            await asyncio.wait_for(process.communicate(), 10)


if __name__ == "__main__":
    unittest.main()
