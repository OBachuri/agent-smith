"""MCP server for test simple Python code (MBPP task tools)."""

from fastmcp import FastMCP

#from __future__ import annotations
# from agent_smith.tool_impl import MBPPToolContext
   
mcp = FastMCP("Agent Smith - MCP Servver for test MBPP task")

@mcp.tool()
def describe_task() -> str:
    """Return the current MBPP task JSON."""

    return "Call - describe_task"

@mcp.tool()
def public_tests() -> str:
    """Return public imports and assertions for the current MBPP task."""

    return "Call - public_tests"

@mcp.tool()
def run_tests(candidate_code: str = "") -> str:
    """Run public MBPP tests against candidate_code."""

    return "Call - run_tests"

@mcp.resource("agent://mbpp/task")
def task_resource() -> str:
    """Provides application version and support info."""
    return {"version": "1.0.0", "status": "operational"}

@mcp.prompt()
def mbpp_solver() -> str:
    return (
        "Solve the MBPP task by writing Python code, testing it with run_tests, "
        "then call final_answer(code)."
    )


#  Make the script runnable directly via standard I/O (stdio)
if __name__ == "__main__":
    mcp.run()
