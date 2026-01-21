"""Tests for Kokoro TTS provider."""

import builtins
import importlib.machinery
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codevid.audio.tts import TTSError

# Mock kokoro module before importing the provider
module_mock = MagicMock()
module_mock.__spec__ = importlib.machinery.ModuleSpec("kokoro", loader=None)
sys.modules["kokoro"] = module_mock

soundfile_mock = MagicMock()
soundfile_mock.__spec__ = importlib.machinery.ModuleSpec("soundfile", loader=None)
sys.modules["soundfile"] = soundfile_mock


def test_kokoro_provider_init_success() -> None:
    """Test successful initialization of Kokoro provider."""
    from codevid.audio.kokoro_provider import KokoroTTSProvider

    with patch("kokoro.KPipeline") as mock_pipeline:
        provider = KokoroTTSProvider(voice="af_bella", speed=1.2)

        mock_pipeline.assert_called_once_with(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        assert provider.current_voice == "af_bella"
        assert provider._speed == 1.2


def test_kokoro_provider_init_import_error() -> None:
    """Test initialization when kokoro is not installed."""
    from codevid.audio.kokoro_provider import KokoroTTSProvider

    real_import = builtins.__import__

    def _import_missing_kokoro(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):
        if name == "kokoro":
            raise ImportError("No module named 'kokoro'")
        return real_import(name, globals, locals, fromlist, level)

    with patch.dict(sys.modules):
        sys.modules.pop("kokoro", None)
        with patch("builtins.__import__", side_effect=_import_missing_kokoro), pytest.raises(
            TTSError
        ):
            KokoroTTSProvider()


@pytest.mark.asyncio
async def test_kokoro_synthesize() -> None:
    """Test synthesis using Kokoro."""
    from codevid.audio.kokoro_provider import KokoroTTSProvider

    with (
        patch("kokoro.KPipeline") as mock_pipeline_cls,
        patch("soundfile.write") as mock_sf_write,
    ):
        # Setup mock pipeline instance
        mock_pipeline_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_pipeline_instance

        # Setup generator return value
        import numpy as np

        fake_audio = np.array([0.1, 0.2, 0.3])
        # Generator yields (graphemes, phonemes, audio)
        mock_pipeline_instance.return_value = iter([("text", "phonemes", fake_audio)])

        provider = KokoroTTSProvider()

        result = await provider.synthesize("Hello world", Path("output.wav"))

        # Verify pipeline called with correct args
        mock_pipeline_instance.assert_called_once()
        args, kwargs = mock_pipeline_instance.call_args
        assert args[0] == "Hello world"
        assert kwargs["voice"] == "af_bella"
        assert kwargs["speed"] == 1.0

        # Verify file writing
        mock_sf_write.assert_called_once()
        assert str(result.path) == "output.wav"
        assert result.text == "Hello world"
