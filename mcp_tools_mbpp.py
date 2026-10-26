"""MBPP MCP tools backed by the configured Deno sandbox executor."""

from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from pydantic import ValidationError
import typer

from src.config_model import SandboxConfig
from src.mbpp_executor import (
    MBPPExecutionRequest, execute_mbpp, execution_result,
)


mcp = FastMCP("Agent Smith - MBPP")
app = typer.Typer(add_completion=False)
sandbox_config = SandboxConfig()


@mcp.tool()
async def run_tests(
    code: str, test_list: list[str], test_imports: list[str] | None = None,
) -> str:
    """Test a candidate against supplied assertions in the Deno sandbox.

    Optional test_imports are executed before code and test_list in the same
    isolated namespace. Returns a JSON string containing success and output.
    Setup errors explain why tests did not run and how to repair the server.
    The server uses the sandbox's trusted configuration;
    the caller cannot override execution limits. No hidden tests are accessed.
    """
    try:
        request = MBPPExecutionRequest(
            code=code, test_list=test_list, config=sandbox_config,
            test_imports=test_imports if test_imports is not None else [],
        )
    except ValidationError as error:
        details = "; ".join(
            ".".join(str(part) for part in item["loc"]) + ": " + item["msg"]
            for item in error.errors(include_input=False, include_url=False)
        )
        return execution_result(
            False, "Invalid MBPP request: " + details +
            " No code or tests were executed. Supply non-empty Python code "
            "and at least one assertion. Import entries must be non-empty.",
            sandbox_config,
        ).model_dump_json()
    result = await execute_mbpp(request)
    return result.model_dump_json()


@mcp.resource("agent://mbpp/task")
def task_resource() -> dict[str, str]:
    """Server metadata; the caller supplies task code and public tests."""
    return {"runtime": "deno/pyodide",
            "tool": "run_tests(code, test_list, test_imports=None)"}


@mcp.prompt()
def mbpp_solver() -> str:
    return (
        "Solve the MBPP task. Call run_tests(code=solution_code, "
        "test_list=the_public_assertions, test_imports=task.test_imports). "
        "The server runs those imports before the solution and assertions. "
        "If a setup error says tests did not run, repair the server setup "
        "before retrying; do not treat it as assertion feedback. "
        "Use the real test feedback to improve the solution. "
        "When finished, call the sandbox's final_answer(solution_code)."
    )


@app.command()
def main(
    config: Annotated[Path | None, typer.Option(
        "--sandbox-config", exists=True, dir_okay=False, readable=True,
    )] = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
) -> None:
    global sandbox_config
    if transport not in ("stdio", "http"):
        raise typer.BadParameter("Transport must be stdio or http.")
    if config is not None:
        try:
            sandbox_config = SandboxConfig.model_validate_json(
                config.read_text(),
            )
        except (OSError, ValidationError) as error:
            raise typer.BadParameter(
                f"Cannot load sandbox configuration: {error}",
                param_hint="--sandbox-config",
            ) from None
    if transport == "http":
        mcp.run(transport="http", host=host, port=port, show_banner=False)
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    app()
