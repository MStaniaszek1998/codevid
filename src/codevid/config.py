"""Configuration management for Codevid."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from codevid.models.project import (
    LLMConfig,
    LLMProviderType,
    ProjectConfig,
    RecordingSettings,
    TestFramework,
    TTSConfig,
    TTSProviderType,
    VideoSettings,
)

CONFIG_FILE_NAMES = ["codevid.yaml", "codevid.yml", ".codevid.yaml", ".codevid.yml"]


class EnvSettings(BaseSettings):
    """Environment variable settings."""

    model_config = SettingsConfigDict(env_prefix="CODEVID_")

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"


def find_config_file(start_dir: Path | None = None) -> Path | None:
    """Find configuration file in current or parent directories."""
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    while current != current.parent:
        for name in CONFIG_FILE_NAMES:
            config_path = current / name
            if config_path.is_file():
                return config_path
        current = current.parent

    return None


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    with config_path.open() as f:
        return yaml.safe_load(f) or {}


def parse_llm_config(data: dict[str, Any], env: EnvSettings) -> LLMConfig:
    """Parse LLM configuration from dict."""
    provider_str = data.get("provider", "anthropic")
    provider = LLMProviderType(provider_str)

    api_key = data.get("api_key")
    if api_key is None:
        if provider == LLMProviderType.ANTHROPIC:
            api_key = env.anthropic_api_key
        elif provider == LLMProviderType.OPENAI:
            api_key = env.openai_api_key

    base_url = data.get("base_url")
    if base_url is None and provider == LLMProviderType.OLLAMA:
        base_url = env.ollama_base_url

    return LLMConfig(
        provider=provider,
        model=data.get("model"),
        api_key=api_key,
        base_url=base_url,
    )


def parse_tts_config(data: dict[str, Any], env: EnvSettings) -> TTSConfig:
    """Parse TTS configuration from dict."""
    provider_str = data.get("provider", "edge")
    provider = TTSProviderType(provider_str)

    api_key = data.get("api_key")
    if api_key is None:
        if provider == TTSProviderType.OPENAI:
            api_key = env.openai_api_key
        elif provider == TTSProviderType.ELEVENLABS:
            api_key = env.elevenlabs_api_key

    return TTSConfig(
        provider=provider,
        voice=data.get("voice"),
        speed=data.get("speed", 1.0),
        api_key=api_key,
    )


def parse_recording_settings(data: dict[str, Any]) -> RecordingSettings:
    """Parse recording settings from dict."""
    resolution = data.get("resolution")
    if resolution is not None:
        resolution = tuple(resolution)

    return RecordingSettings(
        fps=data.get("fps", 30),
        resolution=resolution,
        device_scale_factor=data.get("device_scale_factor"),
        highlight_clicks=data.get("highlight_clicks", True),
        mouse_spotlight=data.get("mouse_spotlight", True),
        capture_audio=data.get("capture_audio", False),
    )


def parse_video_settings(data: dict[str, Any], base_path: Path) -> VideoSettings:
    """Parse video settings from dict."""

    def resolve_path(p: str | None) -> Path | None:
        if p is None:
            return None
        path = Path(p)
        if not path.is_absolute():
            path = base_path / path
        return path

    encoding_raw = data.get("encoding", {})
    encoding: dict[str, Any]
    if isinstance(encoding_raw, dict):
        encoding = encoding_raw
    else:
        encoding = {}

    return VideoSettings(
        theme=data.get("theme", "default"),
        include_captions=data.get("include_captions", True),
        intro_template=resolve_path(data.get("intro_template")),
        outro_template=resolve_path(data.get("outro_template")),
        watermark_path=resolve_path(data.get("watermark", {}).get("image")),
        watermark_position=data.get("watermark", {}).get("position", "bottom-right"),
        crf=encoding.get("crf", data.get("crf", 18)),
        preset=encoding.get("preset", data.get("preset", "medium")),
        bitrate=encoding.get("bitrate", data.get("bitrate")),
        pixel_format=encoding.get("pixel_format", data.get("pixel_format", "yuv420p")),
        faststart=encoding.get("faststart", data.get("faststart", True)),
    )


def load_config(config_path: Path | None = None) -> ProjectConfig:
    """Load complete project configuration."""
    env = EnvSettings()

    if config_path is None:
        config_path = find_config_file()

    if config_path is None:
        return ProjectConfig(llm=parse_llm_config({}, env), tts=parse_tts_config({}, env))

    base_path = config_path.parent
    data = load_yaml_config(config_path)

    project_data = data.get("project", {})
    tests_data = data.get("tests", {})

    output_dir = project_data.get("output_dir", "./output")
    if not Path(output_dir).is_absolute():
        output_dir = base_path / output_dir

    framework_str = tests_data.get("framework", "playwright")

    return ProjectConfig(
        name=project_data.get("name", "Codevid Project"),
        output_dir=Path(output_dir),
        test_framework=TestFramework(framework_str),
        base_url=tests_data.get("base_url"),
        browser=tests_data.get("browser", "chromium"),
        llm=parse_llm_config(data.get("llm", {}), env),
        tts=parse_tts_config(data.get("tts", {}), env),
        recording=parse_recording_settings(data.get("recording", {})),
        video=parse_video_settings(data.get("video", {}), base_path),
    )
