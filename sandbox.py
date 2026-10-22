import typer
import sys
from typing import Optional
from pathlib import Path


# Init Typer app
app = typer.Typer(
    add_completion=False,
    help=("Agent Smith - SandBox (MCP Client)"
          " - Launch an interactive sandbox environment.")
)


def manual() -> str:
    """Generate the dynamic manual the LLM receives in the system prompt."""

    lines = [
        "Sandbox execution manual:",
        "- Write exactly one Python code block per step.",
        "- Tool calls are ordinary Python function calls.",
        "- Use final_answer(answer_string) when the task is solved.",
        "- Positional arguments are rejected for MCP tools;" +
        "use keyword arguments.",
        "",
        "Available tools:",
        "- final_answer(answer: str): terminate the agent " +
        "loop and return the solution.",
    ]

    # Add to lines tools available via MCP

    return "\n".join(lines)


@app.command(name="uv run -m sandbox")
def main(
    # Positional argument for the template file (optional)
    template: Optional[Path] = typer.Argument(
        None,
        help="Path to the sandbox configuration JSON template."
    ),
    # Option for Stdio MCP tools
    mcp_stdio: Optional[str] = typer.Option(
        None,
        "--mcp-stdio",
        help="Command to run MCP tools via stdio (e.g., 'python mpc_tool.py')."
    ),
    # Option for HTTP MCP server
    mcp_server: Optional[str] = typer.Option(
        None,
        "--mcp-server",
        help="URL of the MCP server to connect."
    ),
):
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


#  Make the script runnable directly via standard I/O (stdio)
if __name__ == "__main__":
    sys.argv[0] = "uv run -m sandbox"
    app()
