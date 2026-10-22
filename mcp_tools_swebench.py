"""MCP server for SWE-bench"""

# Code in docker

from fastmcp import FastMCP

mcp = FastMCP("Agent Smith - MCP Server for test SWE-bench task")


@mcp.tool()
def run_tests(path_file_to_run: str = "") -> str:
    """Run Python code"""
    return "Call - run_tests"


@mcp.prompt()
def mbpp_solver() -> str:
    return (
        "Solve the task by writing Python code, "
        "test it with run_tests(code with test), "
        "then call final_answer(path)."
    )


#  Make the script runnable directly via standard I/O (stdio)
if __name__ == "__main__":
    mcp.run()
