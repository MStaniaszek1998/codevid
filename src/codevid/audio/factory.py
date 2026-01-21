"""Factory for creating TTS providers."""

from codevid.audio.tts import TTSError, TTSProvider
from codevid.models.project import TTSConfig, TTSProviderType


class NoOpTTSProvider(TTSProvider):
    """A no-op TTS provider that generates silence."""

    @property
    def provider_name(self) -> str:
        return "none"

    @property
    def current_voice(self) -> str:
        return "none"

    async def synthesize(self, text: str, output_path):
        """Create a silent audio file."""
        from pathlib import Path
        from codevid.audio.tts import AudioSegment

        # Create an empty/silent audio file
        # For now, just touch the file - in practice you'd create actual silence
        output_path = Path(output_path)
        output_path.touch()

        # Estimate duration based on text
        words = len(text.split())
        duration = (words / 150) * 60  # ~150 words per minute

        return AudioSegment(
            path=output_path,
            duration=max(0.5, duration),
            text=text,
        )

    async def list_voices(self) -> list[str]:
        return ["none"]


def create_tts_provider(config: TTSConfig) -> TTSProvider:
    """Create a TTS provider from configuration.

    Args:
        config: TTS configuration specifying provider and settings.

    Returns:
        Configured TTS provider instance.

    Raises:
        TTSError: If the provider cannot be created.
    """
    if config.provider == TTSProviderType.NONE:
        return NoOpTTSProvider()

    elif config.provider == TTSProviderType.EDGE:
        from codevid.audio.edge_tts import EdgeTTSProvider

        # Convert speed (1.0 = normal) to rate string ("+0%" = normal)
        rate = "+0%"
        if config.speed != 1.0:
            rate_pct = int(round((config.speed - 1.0) * 100))
            rate = f"{rate_pct:+d}%"

        return EdgeTTSProvider(
            voice=config.voice,
            rate=rate,
        )

    elif config.provider == TTSProviderType.OPENAI:
        from codevid.audio.openai_tts import OpenAITTSProvider

        return OpenAITTSProvider(
            api_key=config.api_key,
            voice=config.voice,
            speed=config.speed,
        )

    elif config.provider == TTSProviderType.KOKORO:
        from codevid.audio.kokoro_provider import KokoroTTSProvider

        return KokoroTTSProvider(
            voice=config.voice,
            speed=config.speed,
        )

    elif config.provider == TTSProviderType.ELEVENLABS:
        raise TTSError(
            "ElevenLabs TTS is not yet implemented",
            provider="elevenlabs",
        )

    else:
        raise TTSError(
            f"Unknown TTS provider: {config.provider}",
            provider=str(config.provider),
        )


def get_provider_for_name(
    provider_name: str,
    voice: str | None = None,
    speed: float = 1.0,
    api_key: str | None = None,
) -> TTSProvider:
    """Create a TTS provider by name.

    This is a convenience function for creating providers without a full config.

    Args:
        provider_name: Name of the provider ("edge", "openai", "none").
        voice: Optional voice name.
        speed: Speech speed multiplier.
        api_key: Optional API key for paid providers.

    Returns:
        Configured TTS provider instance.
    """
    try:
        provider_type = TTSProviderType(provider_name.lower())
    except ValueError:
        raise TTSError(
            f"Unknown provider: {provider_name}. "
            f"Available: {', '.join(p.value for p in TTSProviderType)}",
            provider=provider_name,
        )

    config = TTSConfig(
        provider=provider_type,
        voice=voice,
        speed=speed,
        api_key=api_key,
    )

    return create_tts_provider(config)
