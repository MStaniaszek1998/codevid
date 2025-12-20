"""Video composition and editing."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codevid.composer.captions import Caption, CaptionGenerator
from codevid.composer.overlays import OverlayConfig, OverlayGenerator
from codevid.composer.templates import get_theme
from codevid.models import VideoScript
from codevid.recorder.screen import EventMarker


def _build_step_ranges(
    markers: list[EventMarker],
    *,
    video_duration: float,
) -> list[tuple[int, float, float]]:
    """Build ordered (step_index, start, end) ranges from step markers.

    Robust to missing step_end markers (closes at video end) and ignores malformed indices.
    """
    open_starts: dict[int, float] = {}
    ranges: list[tuple[int, float, float]] = []

    for marker in markers:
        idx = marker.metadata.get("index")
        if not isinstance(idx, int):
            continue

        if marker.event_type == "step_start":
            open_starts.setdefault(idx, float(marker.timestamp))
            continue

        if marker.event_type == "step_end":
            start = open_starts.pop(idx, None)
            if start is None:
                continue
            end = float(marker.timestamp)
            if end >= start:
                ranges.append((idx, start, end))

    # Close any still-open steps at the end of the recording.
    for idx, start in open_starts.items():
        ranges.append((idx, start, video_duration))

    # Use timestamps rather than indices to preserve execution order.
    ranges.sort(key=lambda r: r[1])
    return ranges


def _build_audio_indices_by_step(script: VideoScript) -> dict[int, list[int]]:
    """Map step_index -> audio_segments indices for that step.

    audio_segments is expected to be laid out as: [intro, seg_0, seg_1, ..., conclusion].
    """
    by_step: dict[int, list[int]] = {}
    for segment_index, segment in enumerate(script.segments):
        audio_index = segment_index + 1  # offset by intro
        by_step.setdefault(segment.step_index, []).append(audio_index)
    return by_step


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
    crf: int = 18
    preset: str = "medium"
    bitrate: str | None = None
    pixel_format: str = "yuv420p"
    faststart: bool = True


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

        try:
            from moviepy import concatenate_audioclips
        except ImportError:  # pragma: no cover
            from moviepy.audio.AudioClip import concatenate_audioclips

        # Load base recording
        video = VideoFileClip(str(recording_path))
        video_size = (video.w, video.h)
        final_clips = []
        opened_audio_clips: list[Any] = []

        step_ranges = _build_step_ranges(markers, video_duration=float(video.duration))

        # audio_durations is used by CaptionGenerator and expects:
        # [intro_duration, seg_0_duration, ..., seg_n_duration, conclusion_duration]
        audio_durations: list[float] = []
        intro_duration = 5.0 if script.introduction else 0.0
        conclusion_duration = 4.0 if script.conclusion else 0.0

        # 1. Intro segment (title card + intro audio)
        intro_path = audio_segments[0] if audio_segments else None
        intro_audio = None
        if intro_path and intro_path.exists():
            intro_audio = AudioFileClip(str(intro_path))
            opened_audio_clips.append(intro_audio)
            intro_duration = float(intro_audio.duration)

        if script.introduction and intro_duration > 0:
            intro_video = self._create_title_card(script.title, duration=intro_duration, size=video_size)
            if intro_audio is not None:
                intro_video = intro_video.with_audio(intro_audio)
            final_clips.append(intro_video)

        audio_durations.append(intro_duration)

        # Load narration audio per script segment, then group by step_index.
        segment_audio_clips: list[AudioFileClip | None] = []
        step_audio_clips: dict[int, list[AudioFileClip]] = {}

        max_segment_audio_index = max(0, len(audio_segments) - 2)  # exclude intro & conclusion
        for segment_index, segment in enumerate(script.segments):
            audio_index = segment_index + 1  # offset by intro

            if audio_index <= max_segment_audio_index:
                path = audio_segments[audio_index]
                if path.exists():
                    clip = AudioFileClip(str(path))
                    opened_audio_clips.append(clip)
                    segment_audio_clips.append(clip)
                    step_audio_clips.setdefault(segment.step_index, []).append(clip)
                    audio_durations.append(float(clip.duration))
                    continue

            segment_audio_clips.append(None)
            audio_durations.append(float(segment.timing_hint))

        # 2. Step segments (video segment + step audio)
        for step_index, start, end in step_ranges:
            step_audio = None
            target_duration = max(0.1, float(end - start))

            clips_for_step = step_audio_clips.get(step_index, [])
            if clips_for_step:
                step_audio = (
                    clips_for_step[0]
                    if len(clips_for_step) == 1
                    else concatenate_audioclips(clips_for_step)
                )
                if len(clips_for_step) > 1:
                    opened_audio_clips.append(step_audio)
                target_duration = max(0.1, float(step_audio.duration))

            step_video = self._extract_video_segment(video, start, end, target_duration)
            if step_audio is not None:
                step_video = step_video.with_audio(step_audio)
            final_clips.append(step_video)

        # 3. Conclusion segment (last frame + conclusion audio)
        conclusion_path = audio_segments[-1] if len(audio_segments) >= 2 else None
        conclusion_audio = None
        if conclusion_path and conclusion_path.exists():
            conclusion_audio = AudioFileClip(str(conclusion_path))
            opened_audio_clips.append(conclusion_audio)
            conclusion_duration = float(conclusion_audio.duration)

        if script.conclusion and conclusion_duration > 0:
            # Freeze the last frame
            last_frame_time = max(0, video.duration - 0.01)
            conclusion_video = video.to_ImageClip(t=last_frame_time).with_duration(conclusion_duration)
            if conclusion_audio is not None:
                conclusion_video = conclusion_video.with_audio(conclusion_audio)
            final_clips.append(conclusion_video)

        audio_durations.append(conclusion_duration)

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
        ffmpeg_params: list[str] = []
        if self.config.codec in {"libx264", "libx265"}:
            ffmpeg_params.extend(["-preset", self.config.preset, "-crf", str(self.config.crf)])
        if self.config.pixel_format:
            ffmpeg_params.extend(["-pix_fmt", self.config.pixel_format])
        if self.config.faststart and self.config.output_path.suffix.lower() in {".mp4", ".m4v"}:
            ffmpeg_params.extend(["-movflags", "+faststart"])

        final_video.write_videofile(
            str(self.config.output_path),
            fps=self.config.fps,
            codec=self.config.codec,
            audio_codec=self.config.audio_codec,
            bitrate=self.config.bitrate,
            ffmpeg_params=ffmpeg_params,
            logger=None,
        )

        # Clean up
        final_duration = float(final_video.duration)
        final_video.close()
        video.close()
        for clip in opened_audio_clips:
            try:
                clip.close()
            except Exception:
                pass

        return CompositionResult(
            output_path=self.config.output_path,
            duration=final_duration,
            resolution=video_size,
            captions_path=captions_path,
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



class CompositionError(Exception):
    """Raised when video composition fails."""

    pass
