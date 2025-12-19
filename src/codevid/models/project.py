"""Project configuration models."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TestFramework(Enum):
    """Supported test frameworks."""

    PLAYWRIGHT = "playwright"
    SELENIUM = "selenium"
    CYPRESS = "cypress"


class LLMProviderType(Enum):
    """Available LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class TTSProviderType(Enum):
    """Available TTS providers."""

    EDGE = "edge"
    OPENAI = "openai"
    ELEVENLABS = "elevenlabs"
    NONE = "none"


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: LLMProviderType = LLMProviderType.ANTHROPIC
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None  # For Ollama or custom endpoints


@dataclass
class TTSConfig:
    """TTS provider configuration."""

    provider: TTSProviderType = TTSProviderType.EDGE
    voice: str | None = None
    speed: float = 1.0
    api_key: str | None = None


@dataclass
class RecordingSettings:
    """Screen recording settings."""

    fps: int = 30
    resolution: tuple[int, int] | None = None  # None = auto-detect
    device_scale_factor: float | None = None
    highlight_clicks: bool = True
    mouse_spotlight: bool = True
    capture_audio: bool = False


@dataclass
class VideoSettings:
    """Video composition settings."""

    theme: str = "default"
    include_captions: bool = True
    intro_template: Path | None = None
    outro_template: Path | None = None
    watermark_path: Path | None = None
    watermark_position: str = "bottom-right"
    crf: int = 18
    preset: str = "medium"
    bitrate: str | None = None
    pixel_format: str = "yuv420p"
    faststart: bool = True


@dataclass
class ProjectConfig:
    """Complete project configuration."""

    name: str = "Codevid Project"
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    test_framework: TestFramework = TestFramework.PLAYWRIGHT
    base_url: str | None = None
    browser: str = "chromium"

    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    recording: RecordingSettings = field(default_factory=RecordingSettings)
    video: VideoSettings = field(default_factory=VideoSettings)

    def ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
