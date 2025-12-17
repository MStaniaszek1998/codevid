"""Main pipeline orchestration for Codevid."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from codevid.audio.tts import AudioSegment, TTSProvider
from codevid.composer.editor import CompositionConfig, CompositionResult, VideoComposer
from codevid.llm.base import LLMProvider
from codevid.models import ParsedTest, VideoScript
from codevid.models.project import ProjectConfig
from codevid.parsers.base import TestParser
from codevid.recorder.screen import EventMarker


@dataclass
class PipelineConfig:
    """Configuration for the generation pipeline."""

    test_file: Path
    output: Path
    project_config: ProjectConfig
    app_name: str | None = None
    preview_mode: bool = False


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    output_path: Path | None
    script: VideoScript
    duration: float = 0.0
    success: bool = True
    error: str | None = None


class Pipeline:
    """Main orchestration pipeline for video generation."""

    def __init__(
        self,
        config: PipelineConfig,
        parser: TestParser | None = None,
        llm: LLMProvider | None = None,
        tts: TTSProvider | None = None,
    ):
        self.config = config
        self._parser = parser
        self._llm = llm
        self._tts = tts
        self._progress_callback: Callable[[int, str], None] | None = None

    def on_progress(self, callback: Callable[[int, str], None]) -> None:
        """Set progress callback (percent, message)."""
        self._progress_callback = callback

    def _report_progress(self, percent: int, message: str = "") -> None:
        if self._progress_callback:
            self._progress_callback(percent, message)

    def _get_temp_dir(self) -> Path:
        """Get the temporary directory path."""
        return self.config.output.parent / ".codevid_temp"

    def _cleanup_temp(self) -> None:
        """Remove the temporary directory and all its contents."""
        temp_dir = self._get_temp_dir()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    def run(self) -> PipelineResult:
        """Execute the pipeline synchronously."""
        return asyncio.run(self.run_async())

    async def run_async(self) -> PipelineResult:
        """Execute the full pipeline asynchronously."""
        try:
            # Step 1: Parse test file
            self._report_progress(5, "Parsing test file...")
            parsed_test = self._parse_test()
            self._report_progress(10, f"Found {len(parsed_test.steps)} test steps")

            # Step 2: Generate script with LLM
            self._report_progress(15, "Generating narration script...")
            script = await self._generate_script(parsed_test)
            self._report_progress(25, "Script generated")

            # Preview mode stops here
            if self.config.preview_mode:
                return PipelineResult(
                    output_path=None,
                    script=script,
                    success=True,
                )

            # Step 3: Generate audio narration
            self._report_progress(30, "Synthesizing audio...")
            audio_segments = await self._generate_audio(script)
            self._report_progress(45, f"Generated {len(audio_segments)} audio segments")

            # Step 3.5: Calculate per-step delays from audio durations
            step_delays = self._calculate_step_delays(
                script, audio_segments, num_steps=len(parsed_test.steps)
            )

            # Step 4: Run test with recording (audio-synchronized timing)
            self._report_progress(50, "Recording test execution...")
            recording_path, markers = await self._record_test(parsed_test, step_delays)
            self._report_progress(75, "Recording complete")

            # Step 5: Compose final video
            self._report_progress(80, "Composing final video...")
            audio_paths = [seg.path for seg in audio_segments]
            result = self._compose_video(recording_path, script, audio_paths, markers)

            # Step 6: Cleanup temporary files
            self._report_progress(95, "Cleaning up temporary files...")
            self._cleanup_temp()
            self._report_progress(100, "Complete!")

            return PipelineResult(
                output_path=result.output_path,
                script=script,
                duration=result.duration,
                success=True,
            )

        except Exception as e:
            import traceback
            # Cleanup temp files even on failure
            self._cleanup_temp()
            return PipelineResult(
                output_path=None,
                script=VideoScript(title="", introduction="", segments=[], conclusion=""),
                success=False,
                error=f"{e}\n\n{traceback.format_exc()}",
            )

    def _parse_test(self) -> ParsedTest:
        """Parse the test file."""
        if self._parser is None:
            raise PipelineError("No parser configured")
        return self._parser.parse(self.config.test_file)

    async def _generate_script(self, test: ParsedTest) -> VideoScript:
        """Generate narration script using LLM."""
        if self._llm is None:
            raise PipelineError("No LLM provider configured")

        context = {"app_name": self.config.app_name or "the application"}
        return await self._llm.generate_script(test, context)

    async def _generate_audio(self, script: VideoScript) -> list[AudioSegment]:
        """Generate audio for all narration segments.

        Returns:
            List of AudioSegment objects with paths and durations.
            Order: [intro, segment_0, segment_1, ..., conclusion]
        """
        if self._tts is None or self._tts.provider_name == "none":
            raise PipelineError(
                "No text-to-speech provider is configured; narration audio cannot be generated. "
                "Set a TTS provider in codevid.yaml or pass --tts/--voice via the CLI."
            )

        audio_segments: list[AudioSegment] = []
        output_dir = self._get_temp_dir()
        output_dir.mkdir(exist_ok=True)

        # Generate intro audio
        intro_path = output_dir / "intro.mp3"
        intro_segment = await self._tts.synthesize(script.introduction, intro_path)
        audio_segments.append(intro_segment)

        # Generate segment audio
        for i, segment in enumerate(script.segments):
            segment_path = output_dir / f"segment_{i:03d}.mp3"
            audio_segment = await self._tts.synthesize(segment.text, segment_path)
            audio_segments.append(audio_segment)

        # Generate conclusion audio
        conclusion_path = output_dir / "conclusion.mp3"
        conclusion_segment = await self._tts.synthesize(script.conclusion, conclusion_path)
        audio_segments.append(conclusion_segment)

        return audio_segments

    def _calculate_step_delays(
        self,
        script: VideoScript,
        audio_segments: list[AudioSegment],
        num_steps: int,
        min_delay: float = 0.5,
    ) -> list[float]:
        """Calculate per-step delays based on audio segment durations.

        Maps narration audio durations to test steps so each step waits
        for its narration to complete.

        Args:
            script: The video script with segment-to-step mapping.
            audio_segments: Audio segments [intro, segment_0, ..., conclusion].
            num_steps: Total number of test steps.
            min_delay: Minimum delay per step regardless of audio.

        Returns:
            List of delays (in seconds) for each test step.
        """
        # Build step_index -> total audio duration mapping
        # (handles multiple segments per step by summing)
        step_durations: dict[int, float] = {}

        for i, narration_seg in enumerate(script.segments):
            # Audio index is i+1 (skip intro at index 0)
            audio_idx = i + 1
            if audio_idx < len(audio_segments) - 1:  # Exclude conclusion
                duration = audio_segments[audio_idx].duration
                step_idx = narration_seg.step_index
                step_durations[step_idx] = step_durations.get(step_idx, 0.0) + duration

        # Generate delays for all steps
        delays: list[float] = []
        for step_idx in range(num_steps):
            audio_duration = step_durations.get(step_idx, 0.0)
            # Step delay should be at least audio duration, but not less than min_delay
            delays.append(max(audio_duration, min_delay))

        return delays

    async def _record_test(
        self,
        test: ParsedTest,
        step_delays: list[float] | None = None,
    ) -> tuple[Path, list[EventMarker]]:
        """Execute test while recording screen.

        Args:
            test: The parsed test to execute.
            step_delays: Optional per-step delays (from audio durations).
        """
        from codevid.executor.playwright import ExecutorConfig, PlaywrightExecutor

        output_dir = self._get_temp_dir()
        output_dir.mkdir(exist_ok=True)
        video_dir = output_dir / "playwright_video"
        video_dir.mkdir(exist_ok=True)

        executor_config = ExecutorConfig(
            headless=True,
            slow_mo=100,
            step_delay=0.5,  # Fallback delay
            step_delays=step_delays,  # Per-step delays from audio durations
            record_video_dir=video_dir,
            record_video_size=self.config.project_config.recording.resolution,
        )
        executor = PlaywrightExecutor(executor_config)

        total_steps = len(test.steps)
        markers, video_path = await executor.execute(
            test,
            recorder=None,
            on_step=lambda i, step: self._report_progress(
                50 + int(25 * i / max(total_steps, 1)),
                f"Executing step {i + 1}/{total_steps}: {step.description}",
            ),
        )

        if video_path is None:
            raise PipelineError("Playwright did not produce a video file")

        return video_path, markers

    def _compose_video(
        self,
        recording_path: Path,
        script: VideoScript,
        audio_segments: list[Path],
        markers: list[EventMarker],
    ) -> CompositionResult:
        """Compose final video from all components."""
        comp_config = CompositionConfig(
            output_path=self.config.output,
            include_captions=self.config.project_config.video.include_captions,
            theme=self.config.project_config.video.theme,
            intro_path=self.config.project_config.video.intro_template,
            outro_path=self.config.project_config.video.outro_template,
            watermark_path=self.config.project_config.video.watermark_path,
            watermark_position=self.config.project_config.video.watermark_position,
        )

        composer = VideoComposer(comp_config)
        return composer.compose(recording_path, script, audio_segments, markers)


class PipelineError(Exception):
    """Raised when pipeline execution fails."""

    pass
