import typer
import sys
import asyncio
from typing import Optional
from pathlib import Path
from fastmcp import Client
from fastmcp.tools import Tool

# Init Typer app
app = typer.Typer(
    add_completion=False,
    help=("Agent Smith - SandBox (MCP Client)"
          " - Launch an interactive sandbox environment.")
)


async def get_tools(server: str) -> list[Tool]:
    async with Client(server) as client:
        result: list[Tool] = await client.list_tools()

        return result


# def python_type(schema: dict) -> str:
#     t = schema.get("type")

#     if isinstance(t, list):
#         return " | ".join(
#             python_type({**schema, "type": typ})
#             for typ in t
#         )

#     mapping = {
#         "string": "str",
#         "integer": "int",
#         "number": "float",
#         "boolean": "bool",
#         "null": "None",
#         "object": "dict",
#         "array": "list",
#     }

#     return mapping.get(t, "Any")


def manual(tools: list[Tool] | None) -> str:
    """Generate the dynamic manual the LLM receives in the system prompt."""

    lines = [
        "Sandbox execution manual:",
        "- Write exactly one Python code block per step.",
        "- Tool calls are ordinary Python function calls.",
        "- Use final_answer(answer_string) when the task is solved.",
        "- Positional arguments are rejected for MCP tools;" +
        "use keyword arguments.\n",
        "Available tools:"
    ]

    if tools:
        for tool in tools:
            schema = tool.inputSchema
            params = schema.get("properties", {})
            signature = ", ".join(
                # f"{name}: {python_type(spec)}"
                f"{name}: {spec}"
                for name, spec in params.items()
            )
            lines.append(f"- {tool.name}({signature}): {tool.description}")

    lines.append("- final_answer(answer: str): terminate the agent loop and " +
                 "return the solution.")

    return "\n".join(lines)


# @app.command(name="uv run -m sandbox")
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

    tools = None
    if mcp_server:
        # EXAMPLE: uv run sandbox --mcp-server https://mcp.webrobot.eu/mcp
        tools = asyncio.run(get_tools(mcp_server))

    typer.echo(manual(tools))

    data = ""

    while (data != "exit" and data != "exit()"):
        data = sys.stdin.read().strip()
        # -- run the command
        print("-"*20, "Received command for sandbox:\n", data, "\n", "-"*20)

    print("Sandbox: Work is complete,",
          "all connections terminate, all resources released. Bye!")


if __name__ == "__main__":
    app()
