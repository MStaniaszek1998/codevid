"""CLI entry point for Codevid."""

from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from codevid import __version__
from codevid.config import load_config
from codevid.models.project import LLMProviderType, TTSProviderType
from codevid.llm.factory import LLMError, create_llm_provider
from codevid.llm.provider_simple import SimpleLLM
from codevid.parsers.playwright import PlaywrightParser
from codevid.pipeline import Pipeline, PipelineConfig
from codevid.audio.factory import TTSError, create_tts_provider

app = typer.Typer(
    name="codevid",
    help="Generate video tutorials from automated tests using LLMs.",
    add_completion=False,
)
console = Console()


class LLMChoice(str, Enum):
    openai = "openai"
    anthropic = "anthropic"
    ollama = "ollama"
    simple = "simple"


class TTSChoice(str, Enum):
    edge = "edge"
    openai = "openai"
    kokoro = "local_kokoro"
    elevenlabs = "elevenlabs"
    none = "none"


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]codevid[/bold] version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Codevid - Generate video tutorials from automated tests."""
    pass


@app.command()
def generate(
    test_file: Path = typer.Argument(
        ...,
        help="Path to the test file to generate a tutorial from.",
        exists=True,
        readable=True,
    ),
    output: Path = typer.Option(
        Path("./output.mp4"),
        "-o",
        "--output",
        help="Output video path.",
    ),
    llm: Optional[LLMChoice] = typer.Option(
        None,
        "--llm",
        help="LLM provider for script generation (overrides config file).",
    ),
    llm_model: Optional[str] = typer.Option(
        None,
        "--llm-model",
        help="Specific LLM model to use.",
    ),
    tts: Optional[TTSChoice] = typer.Option(
        None,
        "--tts",
        help="Text-to-speech provider (overrides config file).",
    ),
    voice: Optional[str] = typer.Option(
        None,
        "--voice",
        help="TTS voice name.",
    ),
    theme: Optional[str] = typer.Option(
        None,
        "--theme",
        help="Video theme/style.",
    ),
    app_name: Optional[str] = typer.Option(
        None,
        "--app-name",
        help="Application name for narration context.",
    ),
    captions: Optional[bool] = typer.Option(
        None,
        "--captions/--no-captions",
        help="Include captions in video.",
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Preview script without recording.",
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file.",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Enable verbose output.",
    ),
) -> None:
    """Generate a video tutorial from a test file."""
    # Load configuration from file (or defaults)
    config = load_config(config_file)

    # Override with CLI options only if explicitly provided
    if llm is not None:
        config.llm.provider = LLMProviderType(llm.value)
    if llm_model is not None:
        config.llm.model = llm_model
    if tts is not None:
        config.tts.provider = TTSProviderType(tts.value)
    if voice is not None:
        config.tts.voice = voice
    if theme is not None:
        config.video.theme = theme
    if captions is not None:
        config.video.include_captions = captions

    console.print(
        Panel(
            f"[bold]Generating tutorial from:[/bold] {test_file}\n"
            f"[bold]Output:[/bold] {output}\n"
            f"[bold]LLM:[/bold] {config.llm.provider.value} ({config.llm.model or 'default'})\n"
            f"[bold]TTS:[/bold] {config.tts.provider.value}",
            title="Codevid",
            border_style="blue",
        )
    )

    if preview:
        _run_preview(test_file, config, app_name, verbose)
    else:
        _run_generate(test_file, output, config, app_name, verbose)


def _run_preview(
    test_file: Path,
    project_config,
    app_name: Optional[str],
    verbose: bool,
) -> None:
    """Preview the generated script without recording."""
    console.print("\n[yellow]Preview mode - generating script only...[/yellow]\n")

    project_config.ensure_output_dir()
    parser = PlaywrightParser()
    llm_provider = _build_llm_provider(project_config)

    pipeline = Pipeline(
        PipelineConfig(
            test_file=test_file,
            output=project_config.output_dir / "preview.mp4",
            project_config=project_config,
            app_name=app_name,
            preview_mode=True,
        ),
        parser=parser,
        llm=llm_provider,
        tts=None,
    )

    def on_progress(percent: int, message: str) -> None:
        console.print(f"[dim][{percent:3d}%][/dim] {message or 'Working...'}")

    pipeline.on_progress(on_progress)
    result = pipeline.run()

    if result.success:
        console.print("\n[green]Script preview complete.[/green]")
        console.print(f"[bold]Title:[/bold] {result.script.title}")
        console.print(f"[bold]Intro:[/bold] {result.script.introduction}")
        for segment in result.script.segments:
            console.print(f"  - {segment.text}")
        console.print("[dim]Use without --preview to generate the full video.[/dim]")
    else:
        console.print(f"\n[red]Preview failed:[/red] {result.error or 'Unknown error'}")


def _run_generate(
    test_file: Path,
    output: Path,
    project_config,
    app_name: Optional[str],
    verbose: bool,
) -> None:
    """Run the full generation pipeline."""
    project_config.ensure_output_dir()
    output.parent.mkdir(parents=True, exist_ok=True)

    parser = PlaywrightParser()
    llm_provider = _build_llm_provider(project_config)
    tts_provider = _build_tts_provider(project_config)

    pipeline = Pipeline(
        PipelineConfig(
            test_file=test_file,
            output=output,
            project_config=project_config,
            app_name=app_name,
            preview_mode=False,
        ),
        parser=parser,
        llm=llm_provider,
        tts=tts_provider,
    )

    def on_progress(percent: int, message: str) -> None:
        console.print(f"[dim][{percent:3d}%][/dim] {message or 'Working...'}")

    pipeline.on_progress(on_progress)
    result = pipeline.run()

    if result.success and result.output_path:
        console.print(f"\n[green]Video saved to:[/green] {result.output_path}")
    else:
        console.print(f"\n[red]Generation failed:[/red] {result.error or 'Unknown error'}")


@app.command()
def preview(
    test_file: Path = typer.Argument(
        ...,
        help="Path to the test file.",
        exists=True,
        readable=True,
    ),
    llm: Optional[LLMChoice] = typer.Option(
        None,
        "--llm",
        help="LLM provider (overrides config file).",
    ),
    llm_model: Optional[str] = typer.Option(
        None,
        "--llm-model",
        help="Specific LLM model.",
    ),
    app_name: Optional[str] = typer.Option(
        None,
        "--app-name",
        help="Application name for context.",
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file.",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Verbose output.",
    ),
) -> None:
    """Preview the generated script without recording.

    This is a shortcut for `codevid generate --preview`.
    """
    config = load_config(config_file)
    if llm is not None:
        config.llm.provider = LLMProviderType(llm.value)
    if llm_model is not None:
        config.llm.model = llm_model

    _run_preview(test_file, config, app_name, verbose)


@app.command("list-voices")
def list_voices(
    provider: TTSChoice = typer.Argument(
        ...,
        help="TTS provider to list voices for.",
    ),
) -> None:
    """List available voices for a TTS provider."""
    console.print(f"\n[bold]Available voices for {provider.value}:[/bold]\n")

    if provider == TTSChoice.edge:
        # Common Edge TTS voices
        voices = [
            ("en-US-AriaNeural", "English (US) - Female, conversational"),
            ("en-US-GuyNeural", "English (US) - Male, conversational"),
            ("en-US-JennyNeural", "English (US) - Female, friendly"),
            ("en-GB-SoniaNeural", "English (UK) - Female"),
            ("en-GB-RyanNeural", "English (UK) - Male"),
            ("en-AU-NatashaNeural", "English (AU) - Female"),
        ]
        for voice_id, description in voices:
            console.print(f"  [cyan]{voice_id}[/cyan] - {description}")
        console.print("\n[dim]Run `edge-tts --list-voices` for full list.[/dim]")

    elif provider == TTSChoice.openai:
        voices = [
            ("alloy", "Neutral, balanced"),
            ("echo", "Male, warm"),
            ("fable", "British accent"),
            ("onyx", "Deep, authoritative"),
            ("nova", "Female, friendly"),
            ("shimmer", "Female, expressive"),
        ]
        for voice_id, description in voices:
            console.print(f"  [cyan]{voice_id}[/cyan] - {description}")

    elif provider == TTSChoice.kokoro:
        voices = [
            ("af_bella", "American Female (Bella)"),
            ("af_nicole", "American Female (Nicole)"),
            ("af_sarah", "American Female (Sarah)"),
            ("af_sky", "American Female (Sky)"),
            ("am_adam", "American Male (Adam)"),
            ("am_michael", "American Male (Michael)"),
            ("bf_emma", "British Female (Emma)"),
            ("bf_isabella", "British Female (Isabella)"),
            ("bm_george", "British Male (George)"),
            ("bm_lewis", "British Male (Lewis)"),
        ]
        for voice_id, description in voices:
            console.print(f"  [cyan]{voice_id}[/cyan] - {description}")

    elif provider == TTSChoice.elevenlabs:
        console.print("  [dim]ElevenLabs voices require API access.[/dim]")
        console.print("  [dim]Visit https://elevenlabs.io to view available voices.[/dim]")

    elif provider == TTSChoice.none:
        console.print("  [dim]No TTS - video will have no narration.[/dim]")


@app.command()
def init(
    path: Path = typer.Argument(
        Path("."),
        help="Directory to initialize.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing config.",
    ),
) -> None:
    """Initialize a new Codevid project with a configuration file."""
    config_path = path / "codevid.yaml"

    if config_path.exists() and not force:
        console.print(
            f"[red]Configuration file already exists:[/red] {config_path}\n"
            "[dim]Use --force to overwrite.[/dim]"
        )
        raise typer.Exit(1)

    default_config = """\
# Codevid Configuration
# See https://github.com/codevid/codevid for documentation

project:
  name: "My App Tutorials"
  output_dir: "./tutorials"

llm:
  provider: anthropic
  # model: claude-sonnet-4-20250514  # Optional: specify model

tts:
  provider: edge
  voice: en-US-AriaNeural
  speed: 1.0

recording:
  fps: 30
  # resolution: [1920, 1080]  # Recommended for sharper recordings
  # device_scale_factor: 2  # Optional: higher DPI (may affect responsive layouts)
  highlight_clicks: true
  mouse_spotlight: true

video:
  theme: default
  include_captions: true
  # encoding:
  #   crf: 18            # Lower = higher quality (typical: 18-23)
  #   preset: medium     # Slower = better compression (medium/slow/slower)
  #   pixel_format: yuv420p
  #   faststart: true    # Enables fast streaming playback for MP4
  #   # bitrate: 8000k   # Optional: set if you want constant-ish bitrate output
  # intro_template: ./assets/intro.mp4
  # outro_template: ./assets/outro.mp4
  # watermark:
  #   enabled: true
  #   image: ./assets/logo.png
  #   position: bottom-right

tests:
  framework: playwright
  # base_url: http://localhost:3000
  browser: chromium
"""

    config_path.write_text(default_config)
    console.print(f"[green]Created configuration file:[/green] {config_path}")


def _build_llm_provider(config) -> object:
    """Create an LLM provider, falling back to a local rule-based generator."""
    try:
        return create_llm_provider(config.llm)
    except LLMError as e:
        console.print(
            f"[yellow]LLM provider unavailable ({e}). Falling back to local script generation.[/yellow]"
        )
        return SimpleLLM()


def _build_tts_provider(config):
    """Create a TTS provider; fail loudly if unavailable to avoid silent videos."""
    return create_tts_provider(config.tts)


if __name__ == "__main__":
    app()
