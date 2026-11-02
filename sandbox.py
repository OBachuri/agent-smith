import typer
import sys
import asyncio
import shlex
import ast
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from contextlib import AsyncExitStack
from typing import Optional, Any
from pathlib import Path
from fastmcp import Client
from mcp.types import Tool
from fastmcp.client.transports import StdioTransport
from dataclasses import dataclass
from src.config_model import SandboxConfig, SandboxIntermediateResult


SANDBOX_TEMPLATE_PATH = "src/sandbox_template.json"


@dataclass(frozen=True)
class ParsedCall:
    name: str
    arguments: dict[str, Any]


# Init Typer app
app = typer.Typer(
    add_completion=False,
    help=("Agent Smith - SandBox (MCP Client)"
          " - Launch an interactive sandbox environment.")
)


def parse_tool_call(source: str) -> ParsedCall:
    try:
        tree = ast.parse(source.strip(), mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python syntax: {exc.msg}") from exc

    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr):
        raise ValueError("Expected exactly one function call")

    expression = tree.body[0].value

    if not isinstance(expression, ast.Call):
        raise ValueError("Expected a function call")

    if not isinstance(expression.func, ast.Name):
        raise ValueError("Only direct function calls are allowed")

    if expression.args:
        raise ValueError("Positional arguments are not allowed")

    arguments: dict[str, Any] = {}

    for keyword in expression.keywords:
        if keyword.arg is None:
            raise ValueError("Unpacking keyword arguments is not allowed")

        if keyword.arg in arguments:
            raise ValueError(f"Duplicate argument: {keyword.arg}")

        try:
            arguments[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError, SyntaxError) as exc:
            raise ValueError(
                f"Argument '{keyword.arg}' must be a literal value"
            ) from exc

    return ParsedCall(
        name=expression.func.id,
        arguments=arguments
    )


def validate_tool_call(
    call: ParsedCall,
    tool_registry: dict[str, Tool]
) -> Tool | None:
    if call.name == "final_answer":
        if set(call.arguments) != {"answer"}:
            raise ValueError(
                "final_answer requires exactly one argument: answer"
            )
        if not isinstance(call.arguments["answer"], str):
            raise ValueError("final_answer.answer must be a string")
        return None

    tool = tool_registry.get(call.name)
    if tool is None:
        raise ValueError(f"Unknown tool: {call.name}")

    schema = tool.input_schema or {}

    try:
        validator = Draft202012Validator(schema)
        validator.check_schema(schema)
        validator.validate(call.arguments)
    except SchemaError as exc:
        raise ValueError(
            f"Invalid schema for MCP tool '{call.name}'"
        ) from exc
    except ValidationError as exc:
        path = ".".join(str(item) for item in exc.absolute_path)
        location = f" at '{path}'" if path else ""

        raise ValueError(
            f"Invalid arguments for '{call.name}'{location}: {exc.message}"
        ) from exc

    return tool


async def dispatch_tool_call(
    call: ParsedCall,
    tool_registry: dict[str, Tool],
    client: Optional[Client],
) -> SandboxIntermediateResult:
    tool = validate_tool_call(call, tool_registry)

    if tool is None:
        return SandboxIntermediateResult(
            success=True,
            tool_name="final_answer",
            sandbox_output=call.arguments["answer"]
        )

    if not client:
        raise ValueError("There is no active MCP client")

    try:
        result = await client.call_tool(
            call.name,
            call.arguments
        )
    except Exception as exc:
        return SandboxIntermediateResult(
            success=False,
            tool_name=call.name,
            sandbox_output=f"MCP tool failed: {exc}"
        )

    return SandboxIntermediateResult(
        success=True,
        tool_name=call.name,
        sandbox_output=str(result)
    )


def get_python_type(prop: Any) -> str:
    types = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "object": "dict[str, Any]"
    }

    if "anyOf" in prop:
        options = prop["anyOf"]
        non_null = [p for p in options if p.get("type") != "null"]
        return " | ".join(get_python_type(p) for p in non_null)

    typ = prop.get("type")

    if typ == "array":
        item_type = get_python_type(prop.get("items", {}))
        return f"list[{item_type}]"

    return types.get(typ, "Any")


def schema_to_signature(tool: Tool) -> str:
    schema = tool.input_schema or {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    params = []
    for name, prop in properties.items():
        typ = get_python_type(prop)

        default = "" if name in required else " | None = None"
        params.append(f"{name}: {typ}{default}")

    return f"- {tool.name}({', '.join(params)}): {tool.description})"


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
            lines.append(schema_to_signature(tool))

    return "\n".join(lines)


def build_tool_registry(tools: list[Tool]) -> dict[str, Tool]:
    registry: dict[str, Tool] = {}

    for tool in tools:
        if tool.name in registry:
            raise ValueError(f"Duplicate MCP tool name: {tool.name}")
        registry[tool.name] = tool

    return registry


async def run_main_loop(
        tool_registry: dict[str, Tool],
        client: Optional[Client],
        sndbx_cnfg: Optional[SandboxConfig]
) -> None:
    data = " "

    while (True):
        data = sys.stdin.read().strip()
        if not data or data == "exit" or data == "exit()":
            # TODO: some quit function
            print("Sandbox: Work complete,",
                  "all connections terminated, all resources released. Bye!")
            return

        call = parse_tool_call(data)
        result = await dispatch_tool_call(call, tool_registry, client)
        print(result.model_dump_json(indent=2))


async def sandbox(
        template: Optional[Path] = None,
        mcp_stdio: Optional[str] = None,
        mcp_server: Optional[str] = None) -> None:
    async with AsyncExitStack() as stack:
        tool_registry: dict[str, Tool] = {}
        client: Optional[Client] = None
        active_client: Optional[Client] = None
        sndbx_cnfg: Optional[SandboxConfig] = None

        if not template:
            template = Path(SANDBOX_TEMPLATE_PATH)
        with open(template) as f:
            sndbx_cnfg = SandboxConfig.model_validate_json(f.read())

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
            tools = await active_client.list_tools() if active_client else []
            tool_registry = build_tool_registry(tools)

        typer.echo(manual(list(tool_registry.values())))

        await run_main_loop(tool_registry, active_client, sndbx_cnfg)


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

    if mcp_stdio and mcp_server:
        raise ValueError("Wrong format 'uv run --mcp-stdio ... --mcp-server "
                         "...'. It must contain either mcp-stdio or mcp-server"
                         ", but not both")

    asyncio.run(sandbox(template, mcp_stdio, mcp_server))


if __name__ == "__main__":
    app()
