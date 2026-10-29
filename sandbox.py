import typer
import sys
import asyncio
import shlex
from contextlib import AsyncExitStack
from typing import Optional
from pathlib import Path
from fastmcp import Client
from mcp.types import Tool
from fastmcp.client.transports import StdioTransport

# Init Typer app
app = typer.Typer(
    add_completion=False,
    help=("Agent Smith - SandBox (MCP Client)"
          " - Launch an interactive sandbox environment.")
)


def manual(tools: list[Tool] | None) -> str:
    """Generate the dynamic manual the LLM receives in the system prompt."""

    lines = [
        "Sandbox execution manual:",
        "- Write exactly one Python code block per step.",
        "- Tool calls are ordinary Python function calls.",
        "- Use final_answer(answer_string) when the task is solved.",
        "- Positional arguments are rejected for MCP tools;" +
        "use keyword arguments.\n",
        "Available tools:",
        "- final_answer(answer: str): terminate the agent loop and " +
        "return the solution."
    ]

    if tools:
        for tool in tools:
            schema = tool.input_schema
            params = schema.get("properties", {})
            signature = ", ".join(
                # f"{name}: {python_type(spec)}"
                f"{name}: {spec}"
                for name, spec in params.items()
            )
            lines.append(f"- {tool.name}({signature}): {tool.description}")

    return "\n".join(lines)


async def sandbox(
        template: Optional[Path] = None,
        mcp_stdio: Optional[str] = None,
        mcp_server: Optional[str] = None) -> None:
    async with AsyncExitStack() as stack:
        tools: Optional[list[Tool]] = None
        client: Optional[Client] = None

        if mcp_stdio:
            cmd = shlex.split(mcp_stdio)
            client = Client(
                StdioTransport(
                    command=cmd[0],
                    args=cmd[1:]
                )
            )
        elif mcp_server:
            # EXAMPLE: uv run sandbox --mcp-server https://mcp.webrobot.eu/mcp
            client = Client(mcp_server)

        if client is not None:
            active_client = await stack.enter_async_context(client)
            tools = await active_client.list_tools()

        typer.echo(manual(tools))

        data = ""

        while (data != "exit" and data != "exit()"):
            data = sys.stdin.read().strip()
            # -- run the command
            print("-"*20, "Received command for sandbox:\n",
                  data, "\n", "-"*20)

        print("Sandbox: Work is complete,",
              "all connections terminate, all resources released. Bye!")


@app.command()
def main(
    template: Optional[Path] = typer.Argument(
        None,
        help="Path to the sandbox template JSON file.",
    ),
    mcp_stdio: Optional[str] = typer.Option(
        None,
        "--mcp-stdio",
        help="Command to run MCP tools via stdio (e.g., 'python mcp_tool.py')."
    ),
    mcp_server: Optional[str] = typer.Option(
        None,
        "--mcp-server",
        help="MCP server URL.",
    )
) -> None:
    """
    Sandbox CLI - for Agent Smith.

    Write command and press Ctrl+D
    """

    # if mcp_stdio and mcp_server:
    #     wrong format ???

    asyncio.run(sandbox(template, mcp_stdio, mcp_server))


if __name__ == "__main__":
    app()
