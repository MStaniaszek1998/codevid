"""Tests for video composition components."""

from pathlib import Path

import pytest

from codevid.composer.captions import Caption, CaptionGenerator
from codevid.composer.editor import _build_audio_indices_by_step, _build_step_ranges
from codevid.composer.overlays import OverlayConfig, OverlayGenerator
from codevid.composer.templates import get_theme, list_themes
from codevid.models import NarrationSegment, VideoScript
from codevid.recorder.screen import EventMarker


class TestCaption:
    def test_caption_duration(self):
        caption = Caption(text="Hello", start_time=1.0, end_time=3.0)
        assert caption.duration == 2.0

    def test_to_srt_entry(self):
        caption = Caption(text="Hello world", start_time=0.0, end_time=2.5)
        srt = caption.to_srt_entry(1)

        assert "1\n" in srt
        assert "00:00:00,000 --> 00:00:02,500" in srt
        assert "Hello world" in srt

    def test_timestamp_formatting(self):
        caption = Caption(text="Test", start_time=3661.5, end_time=3665.0)
        srt = caption.to_srt_entry(1)

        # 3661.5 seconds = 1 hour, 1 minute, 1.5 seconds
        assert "01:01:01,500" in srt


class TestCaptionGenerator:
    @pytest.fixture
    def generator(self):
        return CaptionGenerator(max_chars_per_line=40, max_lines=2)

    @pytest.fixture
    def sample_script(self):
        return VideoScript(
            title="Test Tutorial",
            introduction="Welcome to this tutorial.",
            segments=[
                NarrationSegment(text="First, we click the button.", step_index=0, timing_hint=3.0),
                NarrationSegment(text="Then we fill in the form.", step_index=1, timing_hint=2.5),
            ],
            conclusion="That's all for now!",
        )

    def test_generate_from_script(self, generator, sample_script):
        captions = generator.generate_from_script(sample_script, [])

        assert len(captions) > 0
        # Should have intro, 2 segments, and conclusion
        assert len(captions) >= 4

    def test_generate_with_audio_durations(self, generator, sample_script):
        audio_durations = [3.0, 2.5, 2.0, 2.0]  # intro, seg1, seg2, conclusion
        captions = generator.generate_from_script(sample_script, [], audio_durations)

        assert len(captions) >= 4

    def test_long_text_splits(self, generator):
        long_text = "This is a very long text that should be split into multiple captions because it exceeds the maximum characters per line limit."
        captions = generator._split_text(long_text, 0.0, 10.0)

        assert len(captions) > 1
        total_duration = sum(c.duration for c in captions)
        assert abs(total_duration - 10.0) < 1.0  # Allow small gap

    def test_text_wrapping(self, generator):
        text = "This is a moderately long line that needs wrapping"
        wrapped = generator._wrap_text(text)

        lines = wrapped.split("\n")
        assert len(lines) <= 2
        for line in lines:
            assert len(line) <= 40

    def test_export_srt(self, generator, sample_script, tmp_path):
        captions = generator.generate_from_script(sample_script, [])
        output_path = tmp_path / "captions.srt"

        result = generator.export_srt(captions, output_path)

        assert result.exists()
        content = result.read_text()
        assert "1\n" in content
        assert "-->" in content


class TestOverlayGenerator:
    @pytest.fixture
    def generator(self):
        return OverlayGenerator(OverlayConfig())

    @pytest.fixture
    def click_markers(self):
        return [
            EventMarker(timestamp=1.0, event_type="click", metadata={"x": 100, "y": 200}),
            EventMarker(timestamp=3.0, event_type="click", metadata={"x": 300, "y": 400}),
        ]

    @pytest.fixture
    def step_markers(self):
        return [
            EventMarker(timestamp=0.5, event_type="step_start", metadata={"index": 0, "action": "navigate"}),
            EventMarker(timestamp=2.0, event_type="step_end", metadata={"index": 0}),
            EventMarker(timestamp=2.5, event_type="step_start", metadata={"index": 1, "action": "click"}),
            EventMarker(timestamp=4.0, event_type="step_end", metadata={"index": 1}),
        ]

    def test_create_click_highlights(self, generator, click_markers):
        highlights = generator.create_click_highlights(click_markers, (1920, 1080))

        assert len(highlights) == 2
        assert highlights[0]["type"] == "click_ripple"
        assert highlights[0]["x"] == 100
        assert highlights[0]["y"] == 200
        assert highlights[0]["timestamp"] == 1.0

    def test_click_highlights_disabled(self, click_markers):
        config = OverlayConfig(click_highlight_enabled=False)
        generator = OverlayGenerator(config)

        highlights = generator.create_click_highlights(click_markers, (1920, 1080))
        assert len(highlights) == 0

    def test_create_step_indicators(self, generator, step_markers):
        indicators = generator.create_step_indicators(step_markers, (1920, 1080))

        assert len(indicators) == 2
        assert indicators[0]["type"] == "step_indicator"
        assert indicators[0]["step_number"] == 1
        assert indicators[0]["action"] == "navigate"
        assert indicators[1]["step_number"] == 2

    def test_step_indicators_disabled(self, step_markers):
        config = OverlayConfig(step_indicator_enabled=False)
        generator = OverlayGenerator(config)

        indicators = generator.create_step_indicators(step_markers, (1920, 1080))
        assert len(indicators) == 0


class TestVideoThemes:
    def test_list_themes(self):
        themes = list_themes()

        assert "default" in themes
        assert "modern" in themes
        assert "minimal" in themes
        assert "professional" in themes
        assert "dark" in themes

    def test_get_default_theme(self):
        theme = get_theme("default")

        assert theme.name == "default"
        assert theme.caption_style.font_size == 28
        assert theme.caption_style.color == "white"

    def test_get_modern_theme(self):
        theme = get_theme("modern")

        assert theme.name == "modern"
        assert theme.click_highlight_color == (100, 180, 255)

    def test_get_minimal_theme(self):
        theme = get_theme("minimal")

        assert theme.name == "minimal"
        assert theme.step_indicator_enabled is False

    def test_unknown_theme_returns_default(self):
        theme = get_theme("nonexistent")

        assert theme.name == "default"

    def test_theme_caption_style(self):
        theme = get_theme("professional")

        assert theme.caption_style.font == "Georgia"
        assert theme.caption_style.margin_bottom == 60

    def test_theme_transition_style(self):
        theme = get_theme("modern")

        assert theme.transition_style.type == "crossfade"
        assert theme.transition_style.duration == 0.3


class TestOverlayConfig:
    def test_default_config(self):
        config = OverlayConfig()

        assert config.click_highlight_enabled is True
        assert config.click_highlight_color == (255, 100, 100)
        assert config.click_highlight_radius == 30
        assert config.step_indicator_enabled is True

    def test_custom_config(self):
        config = OverlayConfig(
            click_highlight_color=(0, 255, 0),
            click_highlight_radius=50,
            step_indicator_enabled=False,
        )

        assert config.click_highlight_color == (0, 255, 0)
        assert config.click_highlight_radius == 50
        assert config.step_indicator_enabled is False


class TestAudioVideoSyncPlanning:
    def test_build_audio_indices_by_step_groups_segments(self):
        script = VideoScript(
            title="Test Tutorial",
            introduction="Intro",
            segments=[
                NarrationSegment(text="A", step_index=0, timing_hint=1.0),
                NarrationSegment(text="B", step_index=0, timing_hint=1.0),
                NarrationSegment(text="C", step_index=2, timing_hint=1.0),
            ],
            conclusion="End",
        )

        assert _build_audio_indices_by_step(script) == {0: [1, 2], 2: [3]}

    def test_build_step_ranges_closes_open_steps_at_video_end(self):
        markers = [
            EventMarker(timestamp=0.0, event_type="step_start", metadata={"index": 0}),
            EventMarker(timestamp=2.0, event_type="step_end", metadata={"index": 0}),
            EventMarker(timestamp=2.5, event_type="step_start", metadata={"index": 1}),
            EventMarker(timestamp=3.0, event_type="step_start", metadata={"index": "bad"}),
        ]

        assert _build_step_ranges(markers, video_duration=10.0) == [(0, 0.0, 2.0), (1, 2.5, 10.0)]
