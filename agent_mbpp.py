import sys
import time
from pathlib import Path
from typing import Annotated
import typer
from src.llm_connector import ProviderConfig, LLMConnector
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
    provider_api_key: Annotated[
        list[str],
        typer.Option(
            "--provider-api-key",
            help="Provider API KEY.",
        )
    ] = [],
    provider_api_keys_file: Annotated[
        Path | None,
        typer.Option(
            "--provider-api-keys-file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to JSON file containing API Keys."
        )
    ] = None,
):

    typer.echo("-"*20)
    typer.echo("Agent Smith CLI (MBPP)")
    typer.echo(f"📂 Task file: {task_file}")
    typer.echo(f"📥 Output file: {output}")
    typer.echo(f"🤖 Model name: {model_name}")
    typer.echo(f"🌐 Provider URL: {provider_url}")
    typer.echo("-"*20)

    if not provider_api_key:
        if provider_api_keys_file is not None:
            print(f"Reading API keys from file: {provider_api_keys_file}")

        typer.secho("Error: Missing API Key!"
                    , fg=typer.colors.RED, err=True)
        typer.secho("Provide --provider-api-key  or --provider-api-keys-file \n"
                    "For more information run: \n" + sys.argv[0] + " --help \n"
                    , err=True)
        raise typer.Exit(code=1)
    
    print(provider_api_keys_file)

    # Record start time
    start_time = time.perf_counter()
    typer.echo("🚀 Start...")
    # -----------

    provider = ProviderConfig(
        name="test",
        base_url=provider_url,
        model=model_name,
        api_keys=provider_api_key
    )

    print(provider)
    print("Keys:", provider.api_keys)

    # llm = LLMConnector(provider)

    # response = llm.chat(
    #     [
    #         {
    #             "role": "system",
    #             "content": "You are a Python coding assistant.",
    #         },
    #         {
    #             "role": "user",
    #             "content": "Write a function that adds two numbers.",
    #         },
    #     ],
    #     temperature=0,
    # )

    # print(response.choices[0].message.content)

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
