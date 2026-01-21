"""Tests for TTS providers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codevid.audio import create_tts_provider, get_provider_for_name
from codevid.audio.edge_tts import EdgeTTSProvider
from codevid.audio.factory import NoOpTTSProvider
from codevid.audio.openai_tts import OpenAITTSProvider
from codevid.audio.tts import TTSError
from codevid.models.project import TTSConfig, TTSProviderType


class TestEdgeTTSProvider:
    def test_init_defaults(self):
        provider = EdgeTTSProvider()
        assert provider.provider_name == "edge"
        assert provider.current_voice == "en-US-AriaNeural"

    def test_voice_shorthand(self):
        provider = EdgeTTSProvider(voice="aria")
        assert provider.current_voice == "en-US-AriaNeural"

        provider = EdgeTTSProvider(voice="guy")
        assert provider.current_voice == "en-US-GuyNeural"

    def test_custom_voice(self):
        provider = EdgeTTSProvider(voice="en-GB-SoniaNeural")
        assert provider.current_voice == "en-GB-SoniaNeural"

    @pytest.mark.asyncio
    async def test_synthesize(self, tmp_path: Path):
        with patch("edge_tts.Communicate") as mock_communicate_class:
            mock_communicate = MagicMock()
            mock_communicate.save = AsyncMock()
            mock_communicate_class.return_value = mock_communicate

            provider = EdgeTTSProvider()
            output_path = tmp_path / "test.mp3"

            # Mock the audio duration calculation
            with patch.object(provider, "_get_audio_duration", new_callable=AsyncMock) as mock_duration:
                mock_duration.return_value = 2.5

                result = await provider.synthesize("Hello world", output_path)

            assert result.text == "Hello world"
            assert result.duration == 2.5
            mock_communicate_class.assert_called_once()
            mock_communicate.save.assert_called_once_with(str(output_path))

    @pytest.mark.asyncio
    async def test_list_voices(self):
        with patch(
            "edge_tts.list_voices",
            new_callable=AsyncMock,
            return_value=[
                {"ShortName": "en-US-AriaNeural"},
                {"ShortName": "en-US-GuyNeural"},
            ],
        ) as mock_list_voices:

            provider = EdgeTTSProvider()
            voices = await provider.list_voices()

            assert "en-US-AriaNeural" in voices
            assert "en-US-GuyNeural" in voices
            mock_list_voices.assert_awaited_once()


class TestOpenAITTSProvider:
    @patch("openai.OpenAI")
    def test_init_defaults(self, mock_openai_class):
        provider = OpenAITTSProvider(api_key="test-key")
        assert provider.provider_name == "openai"
        assert provider.current_voice == "alloy"

    @patch("openai.OpenAI")
    def test_custom_voice(self, mock_openai_class):
        provider = OpenAITTSProvider(api_key="key", voice="nova")
        assert provider.current_voice == "nova"

    @patch("openai.OpenAI")
    def test_invalid_voice_raises_error(self, mock_openai_class):
        with pytest.raises(TTSError) as exc_info:
            OpenAITTSProvider(api_key="key", voice="invalid")

        assert "Unknown voice" in str(exc_info.value)

    @patch("openai.OpenAI")
    def test_speed_clamping(self, mock_openai_class):
        # Speed should be clamped to valid range
        provider = OpenAITTSProvider(api_key="key", speed=10.0)
        assert provider._speed == 4.0

        provider = OpenAITTSProvider(api_key="key", speed=0.1)
        assert provider._speed == 0.25

    @patch("openai.OpenAI")
    @pytest.mark.asyncio
    async def test_synthesize(self, mock_openai_class, tmp_path: Path):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.stream_to_file = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response

        provider = OpenAITTSProvider(api_key="test-key")
        output_path = tmp_path / "test.mp3"

        result = await provider.synthesize("Hello world", output_path)

        assert result.text == "Hello world"
        assert result.duration > 0
        mock_client.audio.speech.create.assert_called_once()
        mock_response.stream_to_file.assert_called_once_with(str(output_path))

    @patch("openai.OpenAI")
    @pytest.mark.asyncio
    async def test_list_voices(self, mock_openai_class):
        provider = OpenAITTSProvider(api_key="key")
        voices = await provider.list_voices()

        assert "alloy" in voices
        assert "nova" in voices
        assert len(voices) == 6


class TestNoOpTTSProvider:
    @pytest.mark.asyncio
    async def test_synthesize_creates_file(self, tmp_path: Path):
        provider = NoOpTTSProvider()
        output_path = tmp_path / "silence.mp3"

        result = await provider.synthesize("Some text here", output_path)

        assert output_path.exists()
        assert result.text == "Some text here"
        assert result.duration > 0

    def test_provider_properties(self):
        provider = NoOpTTSProvider()
        assert provider.provider_name == "none"
        assert provider.current_voice == "none"


class TestTTSFactory:
    def test_create_edge_provider(self):
        config = TTSConfig(provider=TTSProviderType.EDGE, voice="aria")
        provider = create_tts_provider(config)
        assert isinstance(provider, EdgeTTSProvider)
        assert provider.current_voice == "en-US-AriaNeural"

    def test_create_edge_provider_with_speed(self):
        config = TTSConfig(provider=TTSProviderType.EDGE, speed=1.2)
        provider = create_tts_provider(config)
        assert isinstance(provider, EdgeTTSProvider)
        assert provider._rate == "+20%"

    @patch("openai.OpenAI")
    def test_create_openai_provider(self, mock_openai_class):
        config = TTSConfig(provider=TTSProviderType.OPENAI, api_key="key", voice="nova")
        provider = create_tts_provider(config)
        assert isinstance(provider, OpenAITTSProvider)
        assert provider.current_voice == "nova"

    def test_create_none_provider(self):
        config = TTSConfig(provider=TTSProviderType.NONE)
        provider = create_tts_provider(config)
        assert isinstance(provider, NoOpTTSProvider)

    def test_get_provider_for_name(self):
        provider = get_provider_for_name("edge", voice="guy")
        assert isinstance(provider, EdgeTTSProvider)
        assert provider.current_voice == "en-US-GuyNeural"

    def test_get_provider_for_name_none(self):
        provider = get_provider_for_name("none")
        assert isinstance(provider, NoOpTTSProvider)

    def test_unknown_provider_raises_error(self):
        with pytest.raises(TTSError) as exc_info:
            get_provider_for_name("unknown_provider")

        assert "Unknown provider" in str(exc_info.value)

    def test_elevenlabs_not_implemented(self):
        config = TTSConfig(provider=TTSProviderType.ELEVENLABS)

        with pytest.raises(TTSError) as exc_info:
            create_tts_provider(config)

        assert "not yet implemented" in str(exc_info.value)
