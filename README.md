*This project has been created as part of the 42 curriculum by mnestere, obachuri, iiunusov.*

---

# Agent Smith
Building an agentic framework capable of autonomously solving coding challenges (create and fix code on Python).

Autonomous reasoning, code generation, and execution.

## Description

### System architecture

### Agent loop explanation

### Sandbox design

### Tool implementation details

### Benchmark results and analysis

#### MBPP (Mostly Basic Python Problems) benchmark

#### SWE-bench (Software Engineering Benchmark) 

## Instructions

###  Requirement

Docker, uv and deno must be installed in advance.

Docker install - https://docs.docker.com/engine/install/

Install uv: 
```
pip install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
# check 
uv --version
```

Install deno:
```
curl -fsSL https://deno.land/install.sh | sh
```

### MBPP MCP server

Start Docker and pull the candidate execution image once:

```bash
docker pull python:3.10-slim
uv sync --locked
```

Run the server using either MCP transport:

```bash
# stdio: the MCP client launches this command
uv run python mcp_tools_mbpp.py

# Streamable HTTP: connect the MCP client to http://127.0.0.1:8000/mcp
uv run python mcp_tools_mbpp.py --transport http
```

The `run_tests(code: str, test_list: list[str])` tool accepts a candidate
solution and the public test assertions. Include any required `test_imports`
in `code`. It returns a JSON string with `success` and `output`; failed
assertions, syntax errors, memory exhaustion and timeouts return
`success: false` with diagnostic output. Empty code or test lists are rejected.
The server also exposes the `agent://mbpp/task` metadata resource and the
`mbpp_solver` prompt. `final_answer` belongs to the agent sandbox, not this MCP.

Each call uses a fresh Python 3.10 container with no network, host mounts,
or host environment variables. It runs as a non-root user with a read-only
root filesystem, a 16 MiB writable `/tmp`, a 128 MiB memory limit, a 64-process
limit and one CPU. Execution is limited to 30 seconds, output retained by the
server to 8 KiB, and the container is removed after the call, including errors
and cancellation. Truncated output and incomplete execution are reported
explicitly. The image is never pulled automatically during a tool call.
The MCP server runs outside the agent sandbox; this container does not replace
the sandbox's own configurable restrictions.

Override the execution limits or HTTP address when needed:

```bash
uv run python mcp_tools_mbpp.py --transport http --port 8001 \
  --timeout-seconds 10 --memory-mb 256
```

Run the unit, Docker isolation and stdio/HTTP integration tests:

```bash
make test
make lint
```

Local Docker tests are skipped if Docker or the image is unavailable. CI pulls
the image before running them. No model API keys or benchmark datasets are
needed for these tests.

## Resources
- MBPP (Mostly Basic Python Problems) benchmark:
	- https://mcpbr.org/mbpp
	- https://github.com/google-research/google-research/tree/master/mbpp
	- https://huggingface.co/datasets/google-research-datasets/mbpp
- SWE-bench https://www.swebench.com/original.html

- Model Context Protocol Python SDK documentation: https://modelcontextprotocol.github.io/python-sdk/
- MCP Server/Client architecture https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture 
- OpenAI-compatible chat completions API documentation: https://platform.openai.com/docs/api-reference/chat


### AI Usage

Tools Used: ChatGPT (GPT-5, GPT-6, Gemini 2.5 and 3.0)

AI was used to conceptual understanding and to structuring this README to meet subject requirements.

## License

This project was created as part of the 42 curriculum.

It is intended for educational purposes.
