"""Video composition and editing."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codevid.composer.captions import Caption, CaptionGenerator
from codevid.composer.overlays import OverlayConfig, OverlayGenerator
from codevid.composer.templates import CaptionStyle, VideoTheme, get_theme
from codevid.models import VideoScript
from codevid.recorder.screen import EventMarker


@dataclass
class CompositionConfig:
    """Configuration for video composition."""

    output_path: Path
    include_captions: bool = True
    theme: str = "default"
    intro_path: Path | None = None
    outro_path: Path | None = None
    watermark_path: Path | None = None
    watermark_position: str = "bottom-right"
    watermark_opacity: float = 0.7
    fps: int = 30
    codec: str = "libx264"
    audio_codec: str = "aac"


@dataclass
class CompositionResult:
    """Result of video composition."""

    output_path: Path
    duration: float
    resolution: tuple[int, int]
    captions_path: Path | None = None


class VideoComposer:
    """Compose final video from recording and generated assets."""

    def __init__(self, config: CompositionConfig):
        self.config = config
        self.theme = get_theme(config.theme)
        self.caption_generator = CaptionGenerator()
        self.overlay_generator = OverlayGenerator(
            OverlayConfig(
                click_highlight_color=self.theme.click_highlight_color,
                click_highlight_radius=self.theme.click_highlight_radius,
                step_indicator_enabled=self.theme.step_indicator_enabled,
            )
        )

    def compose(
        self,
        recording_path: Path,
        script: VideoScript,
        audio_segments: list[Path],
        markers: list[EventMarker],
    ) -> CompositionResult:
        """Compose final video from all components using segment-based approach.

        Each video segment is matched to its corresponding audio segment,
        with video duration adjusted to match audio. This ensures perfect sync.

        Args:
            recording_path: Path to the screen recording.
            script: The video script with narration.
            audio_segments: Paths to audio files for each segment.
            markers: Event markers from recording.

        Returns:
            CompositionResult with output path and metadata.
        """
        from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips

        # Load base recording
        video = VideoFileClip(str(recording_path))
        video_size = (video.w, video.h)
        final_clips = []
        audio_durations = []

        # Build step timing from markers
        step_times: list[tuple[float, float]] = []
        for marker in markers:
            if marker.event_type == "step_start":
                idx = marker.metadata.get("index")
                start = marker.timestamp
                # Find matching step_end
                end = next(
                    (
                        m.timestamp
                        for m in markers
                        if m.event_type == "step_end" and m.metadata.get("index") == idx
                    ),
                    video.duration,
                )
                step_times.append((start, end))

        audio_idx = 0

        # 1. Intro segment (title card + intro audio)
        if audio_segments and len(audio_segments) > audio_idx:
            intro_path = audio_segments[audio_idx]
            if intro_path.exists():
                intro_audio = AudioFileClip(str(intro_path))
                audio_durations.append(intro_audio.duration)
                intro_video = self._create_title_card(
                    script.title, duration=intro_audio.duration, size=video_size
                )
                intro_video = intro_video.with_audio(intro_audio)
                final_clips.append(intro_video)
                audio_idx += 1

        # 2. Step segments (video segment + step audio)
        for start, end in step_times:
            if audio_idx < len(audio_segments):
                step_path = audio_segments[audio_idx]
                if step_path.exists():
                    step_audio = AudioFileClip(str(step_path))
                    audio_durations.append(step_audio.duration)
                    step_video = self._extract_video_segment(
                        video, start, end, step_audio.duration
                    )
                    step_video = step_video.with_audio(step_audio)
                    final_clips.append(step_video)
                    audio_idx += 1

        # 3. Conclusion segment (last frame + conclusion audio)
        if audio_idx < len(audio_segments):
            conclusion_path = audio_segments[audio_idx]
            if conclusion_path.exists():
                conclusion_audio = AudioFileClip(str(conclusion_path))
                audio_durations.append(conclusion_audio.duration)
                # Freeze the last frame
                last_frame_time = max(0, video.duration - 0.01)
                conclusion_video = video.to_ImageClip(t=last_frame_time).with_duration(
                    conclusion_audio.duration
                )
                conclusion_video = conclusion_video.with_audio(conclusion_audio)
                final_clips.append(conclusion_video)

        # 4. Concatenate all segments
        if final_clips:
            final_video = concatenate_videoclips(final_clips, method="compose")
        else:
            # Fallback: just use the original video
            final_video = video

        # Generate captions (using the actual audio durations)
        captions_path = None
        if self.config.include_captions and script:
            captions = self.caption_generator.generate_from_script(
                script, markers, audio_durations
            )
            # Export SRT file
            captions_path = self.config.output_path.with_suffix(".srt")
            self.caption_generator.export_srt(captions, captions_path)

        # Add watermark if configured
        if self.config.watermark_path:
            final_video = self._add_watermark(final_video)

        # Export final video
        final_video.write_videofile(
            str(self.config.output_path),
            fps=self.config.fps,
            codec=self.config.codec,
            audio_codec=self.config.audio_codec,
            logger=None,
        )

        # Clean up
        final_video.close()
        video.close()

        return CompositionResult(
            output_path=self.config.output_path,
            duration=final_video.duration,
            resolution=video_size,
            captions_path=captions_path,
        )

    def _add_caption_clips(self, video: Any, captions: list[Caption]) -> Any:
        """Add caption text overlays to video."""
        try:
            from moviepy import CompositeVideoClip
        except ImportError:
            return video

        style = self.theme.caption_style
        caption_clips = []

        for caption in captions:
            txt_clip = self._create_text_clip(
                caption.text,
                font_size=style.font_size,
                color=style.color,
                font=style.font,
                bg_color=style.bg_color if style.bg_color != "transparent" else None,
                stroke_color=style.stroke_color,
                stroke_width=style.stroke_width if style.stroke_color else 0,
                method="caption",
                size=(video.w - 100, None),
                text_align="center",
            )
            if txt_clip is None:
                # Skip caption if TextClip fails even after fallback
                continue

            # Position at bottom
            y_pos = video.h - style.margin_bottom - txt_clip.h
            txt_clip = txt_clip.with_position(("center", y_pos))
            txt_clip = txt_clip.with_start(caption.start_time)
            txt_clip = txt_clip.with_duration(caption.duration)

            caption_clips.append(txt_clip)

        if caption_clips:
            return CompositeVideoClip([video, *caption_clips])

        return video

    def _add_overlays(self, video: Any, markers: list[EventMarker]) -> Any:
        """Add click highlights and step indicators."""
        # Generate overlay specifications
        click_highlights = self.overlay_generator.create_click_highlights(
            markers, (video.w, video.h)
        )
        step_indicators = self.overlay_generator.create_step_indicators(
            markers, (video.w, video.h)
        )

        all_overlays = click_highlights + step_indicators

        if all_overlays:
            return self.overlay_generator.apply_overlays_moviepy(video, all_overlays)

        return video

    def _add_intro_outro(self, video: Any) -> Any:
        """Add intro and outro clips if configured."""
        from moviepy import vfx
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = []

        if self.config.intro_path and self.config.intro_path.exists():
            intro = VideoFileClip(str(self.config.intro_path))
            # Resize intro to match main video
            intro = intro.resize((video.w, video.h))
            clips.append(intro)

        clips.append(video)

        if self.config.outro_path and self.config.outro_path.exists():
            outro = VideoFileClip(str(self.config.outro_path))
            outro = outro.resize((video.w, video.h))
            clips.append(outro)

        if len(clips) > 1:
            transition = self.theme.transition_style
            if transition.type == "crossfade" and transition.duration > 0:
                # Apply crossfade transitions
                final_clips = [clips[0]]
                for clip in clips[1:]:
                    final_clips.append(clip.with_effects([vfx.CrossFadeIn(transition.duration)]))
                return concatenate_videoclips(final_clips, method="compose")
            else:
                return concatenate_videoclips(clips, method="compose")

        return video

    def _add_watermark(self, video: Any) -> Any:
        """Add watermark to the video."""
        from moviepy import CompositeVideoClip, ImageClip

        if not self.config.watermark_path or not self.config.watermark_path.exists():
            return video

        try:
            watermark = ImageClip(str(self.config.watermark_path))

            # Scale watermark if too large (max 10% of video width)
            max_width = video.w * 0.1
            if watermark.w > max_width:
                scale = max_width / watermark.w
                watermark = watermark.resize(scale)

            # Position based on config
            margin = 20
            positions = {
                "bottom-right": (video.w - watermark.w - margin, video.h - watermark.h - margin),
                "bottom-left": (margin, video.h - watermark.h - margin),
                "top-right": (video.w - watermark.w - margin, margin),
                "top-left": (margin, margin),
            }
            pos = positions.get(self.config.watermark_position, positions["bottom-right"])

            watermark = watermark.with_position(pos)
            watermark = watermark.with_duration(video.duration)
            watermark = watermark.with_opacity(self.config.watermark_opacity)

            return CompositeVideoClip([video, watermark])
        except Exception:
            # Skip watermark if it fails
            return video

    def _create_title_card(
        self, title: str, duration: float, size: tuple[int, int]
    ) -> Any:
        """Create a title card with the tutorial name."""
        from moviepy import ColorClip, CompositeVideoClip

        # Dark background
        bg = ColorClip(size=size, color=(30, 30, 30), duration=duration)

        # Wrap title to avoid cramped lines and mid-word breaks
        wrapped_title = self._wrap_text(
            title,
            max_width_px=int(size[0] * 0.8),
            font_size=60,
        )
        txt = self._create_text_clip(
            wrapped_title,
            font_size=60,
            color="white",
            font=None,
            method="caption",
            size=(int(size[0] * 0.8), None),
            text_align="center",
            interline=6,
        )
        if txt is None:
            # If TextClip fails even after fallback, just return background
            return bg

        txt = txt.with_position("center").with_duration(duration)
        return CompositeVideoClip([bg, txt])

    def _create_text_clip(
        self, text: str, *, font: str | None = None, **kwargs: Any
    ) -> Any | None:
        """Create a TextClip, falling back to a default font when the requested one fails."""
        try:
            from moviepy import TextClip
        except ImportError:
            return None

        try:
            return TextClip(text=text, font=font, **kwargs)
        except Exception:
            if font:
                try:
                    # Retry with default font to avoid missing font errors.
                    return TextClip(text=text, font=None, **kwargs)
                except Exception:
                    return None
            return None

    def _wrap_text(self, text: str, *, max_width_px: int, font_size: int) -> str:
        """Word-wrap text to roughly fit within a target pixel width."""
        import textwrap

        # Approximate characters that fit in the requested width for the given font size.
        # Empirically ~0.55 * font_size is a reasonable average character width.
        avg_char_px = max(font_size * 0.55, 1)
        max_chars = max(20, int(max_width_px / avg_char_px))

        return textwrap.fill(
            text,
            width=max_chars,
            break_long_words=False,
            break_on_hyphens=False,
        )

    def _extract_video_segment(
        self, video: Any, start_time: float, end_time: float, target_duration: float
    ) -> Any:
        """Extract a segment from video and adjust to target duration."""
        from moviepy import concatenate_videoclips

        # Clamp times to video bounds
        start_time = max(0, min(start_time, video.duration))
        end_time = max(start_time, min(end_time, video.duration))

        # Extract segment
        if end_time > start_time:
            segment = video.subclipped(start_time, end_time)
        else:
            # Fallback: use a single frame
            segment = video.to_ImageClip(t=start_time).with_duration(0.1)

        # Adjust duration to match target
        if segment.duration < target_duration:
            # Extend with frozen last frame
            freeze_duration = target_duration - segment.duration
            last_frame_time = max(0, segment.duration - 0.01)
            last_frame = segment.to_ImageClip(t=last_frame_time).with_duration(
                freeze_duration
            )
            segment = concatenate_videoclips([segment, last_frame])
        elif segment.duration > target_duration:
            # Trim to target duration
            segment = segment.subclipped(0, target_duration)

        return segment


class CompositionError(Exception):
    """Raised when video composition fails."""

    pass
