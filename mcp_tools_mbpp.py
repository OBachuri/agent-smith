"""MCP server for test simple Python code (MBPP task tools)."""

# Run Python code in controlled enviroment via Deno

from fastmcp import FastMCP

mcp = FastMCP("Agent Smith - MCP Server for test MBPP task")


@mcp.tool()
def run_tests(code_on_python: str = "") -> str:
    """Run Python code"""
    return "Call - run_tests"


@mcp.resource("agent://mbpp/task")
def task_resource() -> dict[str, str]:
    """Provides application version and support info."""
    return {"version": "1.0.0", "status": "operational"}


@mcp.prompt()
def mbpp_solver() -> str:
    return (
        "Solve the MBPP task by writing Python code,"
        "test it with run_tests(code with test), "
        "then call final_answer(code)."
    )


#  Make the script runnable directly via standard I/O (stdio)
#  Write command and press Ctrl+D
if __name__ == "__main__":
    mcp.run()
