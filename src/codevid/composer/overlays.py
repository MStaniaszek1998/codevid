"""Visual overlays for video composition."""

from dataclasses import dataclass
from typing import Any

from codevid.recorder.screen import EventMarker


@dataclass
class OverlayConfig:
    """Configuration for video overlays."""

    # Click highlight settings
    click_highlight_enabled: bool = True
    click_highlight_color: tuple[int, int, int] = (255, 100, 100)  # RGB
    click_highlight_radius: int = 30
    click_highlight_duration: float = 0.5  # seconds

    # Mouse cursor spotlight
    cursor_spotlight_enabled: bool = False
    cursor_spotlight_radius: int = 100
    cursor_spotlight_opacity: float = 0.3

    # Step indicator
    step_indicator_enabled: bool = True
    step_indicator_position: str = "top-left"  # top-left, top-right, bottom-left, bottom-right


class OverlayGenerator:
    """Generate visual overlays for video composition."""

    def __init__(self, config: OverlayConfig | None = None):
        self.config = config or OverlayConfig()

    def create_click_highlights(
        self,
        markers: list[EventMarker],
        video_size: tuple[int, int],
    ) -> list[dict[str, Any]]:
        """Create click highlight overlay definitions.

        Returns a list of overlay specifications that can be applied
        to the video during composition.
        """
        if not self.config.click_highlight_enabled:
            return []

        highlights = []
        for marker in markers:
            if marker.event_type == "click" and "x" in marker.metadata and "y" in marker.metadata:
                highlights.append({
                    "type": "click_ripple",
                    "timestamp": marker.timestamp,
                    "duration": self.config.click_highlight_duration,
                    "x": marker.metadata["x"],
                    "y": marker.metadata["y"],
                    "radius": self.config.click_highlight_radius,
                    "color": self.config.click_highlight_color,
                })

        return highlights

    def create_step_indicators(
        self,
        markers: list[EventMarker],
        video_size: tuple[int, int],
    ) -> list[dict[str, Any]]:
        """Create step indicator overlay definitions."""
        if not self.config.step_indicator_enabled:
            return []

        indicators = []
        step_count = 0

        for marker in markers:
            if marker.event_type == "step_start":
                step_count += 1
                # Find the corresponding step_end
                end_time = None
                for end_marker in markers:
                    if (end_marker.event_type == "step_end" and
                        end_marker.timestamp > marker.timestamp and
                        end_marker.metadata.get("index") == marker.metadata.get("index")):
                        end_time = end_marker.timestamp
                        break

                indicators.append({
                    "type": "step_indicator",
                    "timestamp": marker.timestamp,
                    "end_time": end_time,
                    "step_number": step_count,
                    "action": marker.metadata.get("action", ""),
                    "position": self.config.step_indicator_position,
                })

        return indicators

    def apply_overlays_moviepy(
        self,
        video_clip: Any,
        overlays: list[dict[str, Any]],
    ) -> Any:
        """Apply overlays to a MoviePy video clip.

        Args:
            video_clip: MoviePy VideoClip object.
            overlays: List of overlay specifications.

        Returns:
            VideoClip with overlays applied.
        """
        try:
            from moviepy import CompositeVideoClip
        except ImportError:
            return video_clip

        overlay_clips = []

        for overlay in overlays:
            if overlay["type"] == "click_ripple":
                clip = self._create_click_ripple_clip(overlay, video_clip.size)
                if clip:
                    overlay_clips.append(clip)
            elif overlay["type"] == "step_indicator":
                clip = self._create_step_indicator_clip(overlay, video_clip)
                if clip:
                    overlay_clips.append(clip)

        if overlay_clips:
            return CompositeVideoClip([video_clip, *overlay_clips])

        return video_clip

    def _create_click_ripple_clip(
        self,
        overlay: dict[str, Any],
        video_size: tuple[int, int],
    ) -> Any | None:
        """Create a click ripple effect clip."""
        try:
            from moviepy import vfx
            from moviepy import ColorClip
            import numpy as np
        except ImportError:
            return None

        x, y = overlay["x"], overlay["y"]
        radius = overlay["radius"]
        duration = overlay["duration"]
        timestamp = overlay["timestamp"]
        color = overlay["color"]

        # Create a simple colored circle that fades out
        def make_frame(t):
            # Create transparent frame
            frame = np.zeros((video_size[1], video_size[0], 4), dtype=np.uint8)

            # Calculate fade (1.0 at start, 0.0 at end)
            fade = 1.0 - (t / duration)
            current_radius = int(radius * (1 + t / duration))  # Expand over time

            # Draw circle (simplified - just a filled circle)
            y_coords, x_coords = np.ogrid[:video_size[1], :video_size[0]]
            mask = (x_coords - x) ** 2 + (y_coords - y) ** 2 <= current_radius ** 2

            frame[mask] = [*color, int(200 * fade)]

            return frame[:, :, :3]  # Return RGB only

        # For simplicity, return a basic ColorClip positioned at the click
        # In production, you'd use make_frame with a custom clip
        clip = ColorClip(
            size=(radius * 2, radius * 2),
            color=color,
            duration=duration,
        )
        clip = clip.with_position((x - radius, y - radius))
        clip = clip.with_start(timestamp)
        clip = clip.with_effects([vfx.CrossFadeOut(duration)])
        clip = clip.with_opacity(0.6)

        return clip

    def _create_step_indicator_clip(
        self,
        overlay: dict[str, Any],
        video_clip: Any,
    ) -> Any | None:
        """Create a step indicator text clip."""
        try:
            from moviepy import TextClip
        except ImportError:
            return None

        step_num = overlay["step_number"]
        action = overlay["action"]
        timestamp = overlay["timestamp"]
        end_time = overlay.get("end_time") or timestamp + 3.0
        position = overlay["position"]

        text = f"Step {step_num}"
        if action:
            text += f": {action}"

        clip = self._safe_text_clip(
            text,
            font_size=24,
            color="white",
            bg_color="rgba(0,0,0,0.7)",
            font="Arial",
        )
        if clip is None:
            return None

        # Position based on config
        pos_map = {
            "top-left": (20, 20),
            "top-right": (video_clip.w - clip.w - 20, 20),
            "bottom-left": (20, video_clip.h - clip.h - 20),
            "bottom-right": (video_clip.w - clip.w - 20, video_clip.h - clip.h - 20),
        }

        clip = clip.with_position(pos_map.get(position, (20, 20)))
        clip = clip.with_start(timestamp)
        clip = clip.with_duration(end_time - timestamp)

        return clip

    def _safe_text_clip(self, text: str, **kwargs: Any) -> Any | None:
        """Build a TextClip but fall back to default font if the requested font is missing."""
        try:
            from moviepy import TextClip
        except ImportError:
            return None

        try:
            return TextClip(text=text, **kwargs)
        except Exception:
            font = kwargs.pop("font", None)
            try:
                return TextClip(text=text, font=None, **kwargs)
            except Exception:
                # Still failed; skip overlay gracefully.
                return None
