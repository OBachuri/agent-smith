import sys
import time
from pathlib import Path
from typing import Annotated
import typer
# import fire

# from src.config_model import AgConfig

# Init Typer app
app = typer.Typer(
    add_completion=False,
    help="Agent Smith CLI (MBPP)"
)


@app.command(name="uv run -m agent_mbpp")
def main(
    task_file: Annotated[
        Path,
        typer.Option(
            "--task-file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to the JSON file containing tasks (must exist)."
        )
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            file_okay=True,
            dir_okay=False,
            writable=True,
            help="Path to the JSON file for saving the generated solutions."
        )
    ],
    model_name: Annotated[
        str,
        typer.Option(
            "--model-name",
            help="LLM Model name"
        )
    ],
    provider_url: Annotated[
        str,
        typer.Option(
            "--provider-url",
            help="Provider API URL."
        )
    ],
):

    typer.echo("-"*20)
    typer.echo("Agent Smith CLI (MBPP)")
    typer.echo(f"📂 Task file: {task_file}")
    typer.echo(f"📥 Output file: {output}")
    typer.echo(f"🤖 Model name: {model_name}")
    typer.echo(f"🌐 Provider: {provider_url}")
    typer.echo("-"*20)

    # Record start time
    start_time = time.perf_counter()
    typer.echo("🚀 Start...")

    # -----------
    typer.echo("✅ Готово!")

    end_time = time.perf_counter()
    # Calculate duration
    duration = int(end_time - start_time)
    typer.echo(f"⏱ Execution time: {duration // 60}:{duration % 60}"
               " (minutes:seconds)")
    typer.echo("-"*20)


if __name__ == "__main__":
    sys.argv[0] = "uv run -m agent_mbpp"
    app()
