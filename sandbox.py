import typer
import sys
from typing import Optional
from pathlib import Path
from fastmcp import Client

# Init Typer app
app = typer.Typer(
    add_completion=False,
    help=("Agent Smith - SandBox (MCP Client)"
          " - Launch an interactive sandbox environment.")
)

# ==== EXAMPLE ===========================================================
import asyncio

async def get_tools() -> list:
    async with Client("https://mcp.webrobot.eu/mcp") as client:
        result = await client.list_tools()

        return result

        # print(f"There are {len(result)} tools")
        # for tool in result:
        #     print(f"\n{tool.name}: {tool.description}")
        #     print(tool.input_schema)
# ========================================================================


def manual() -> str:
    """Generate the dynamic manual the LLM receives in the system prompt."""

    tools = asyncio.run(get_tools())
    tools_to_show = [tools[i] for i in range(5)]

    lines = [
        "Sandbox execution manual:",
        "- Write exactly one Python code block per step.",
        "- Tool calls are ordinary Python function calls.",
        "- Use final_answer(answer_string) when the task is solved.",
        "- Positional arguments are rejected for MCP tools;" +
        "use keyword arguments.\n",
        "Available tools:"
    ]
    for tool in tools_to_show:
        lines.append(f"- {tool.name}: {tool.description}")
    lines.append("- final_answer(answer: str): terminate the agent " +
        "loop and return the solution.")

    # Add to lines tools available via MCP

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

    typer.echo(manual())

    data = ""

    while (data != "exit" and data != "exit()"):
        data = sys.stdin.read().strip()
        # -- run the command
        print("-"*20, "Received command for sandbox:\n", data, "\n", "-"*20)

    print("Sandbox: Work is complete,",
          "all connections terminate, all resources released. Bye!")

if __name__ == "__main__":
    app()









# #  Make the script runnable directly via standard I/O (stdio)
# if __name__ == "__main__":
#     sys.argv[0] = "uv run -m sandbox"
#     app()
