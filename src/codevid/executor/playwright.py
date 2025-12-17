"""Playwright test executor for running parsed tests."""

import asyncio
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import expect as async_expect

from codevid.models import ActionType, ParsedTest, TestStep
from codevid.recorder.screen import EventMarker

if TYPE_CHECKING:
    from codevid.recorder.screen import ScreenRecorder


@dataclass
class ExecutorConfig:
    """Configuration for test execution."""

    headless: bool = False  # Must be False for screen recording
    browser_type: str = "chromium"
    slow_mo: int = 100  # Milliseconds between Playwright actions
    viewport_width: int = 1280
    viewport_height: int = 720
    step_delay: float = 0.5  # Default delay after each step (fallback)
    step_delays: list[float] | None = None  # Per-step delays (overrides step_delay)
    record_video_dir: Path | None = None
    record_video_size: tuple[int, int] | None = None  # Defaults to viewport size


class PlaywrightExecutor:
    """Execute parsed Playwright tests with recording integration."""

    def __init__(self, config: ExecutorConfig | None = None):
        self.config = config or ExecutorConfig()
        self._browser: Browser | None = None
        self._page: Page | None = None

    def _get_step_delay(self, step_index: int) -> float:
        """Get the delay for a specific step.

        Uses per-step delays if available, otherwise falls back to default.
        """
        if self.config.step_delays and step_index < len(self.config.step_delays):
            return self.config.step_delays[step_index]
        return self.config.step_delay

    async def execute(
        self,
        test: ParsedTest,
        recorder: "ScreenRecorder | None" = None,
        on_step: Callable[[int, TestStep], None] | None = None,
    ) -> tuple[list["EventMarker"], Path | None]:
        """Execute all steps in a parsed test.

        Args:
            test: The parsed test to execute.
            recorder: Optional screen recorder for event marking.
            on_step: Optional callback called before each step.

        Returns:
            Tuple of (event markers, recorded video path if available).
        """
        markers: list[EventMarker] = []
        recorded_video: Path | None = None

        async with async_playwright() as p:
            # Launch browser (visible for recording)
            browser_launcher = getattr(p, self.config.browser_type)
            self._browser = await browser_launcher.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo,
            )

            context_kwargs: dict[str, object] = {
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                }
            }

            if self.config.record_video_dir:
                context_kwargs["record_video_dir"] = str(self.config.record_video_dir)
                if self.config.record_video_size:
                    w, h = self.config.record_video_size
                    context_kwargs["record_video_size"] = {"width": w, "height": h}

            context = await self._browser.new_context(**context_kwargs)
            self._page = await context.new_page()

            # Reset timer to align with the start of video recording (which begins at page creation)
            start_time = time.time()

            try:
                for i, step in enumerate(test.steps):
                    # Notify callback
                    if on_step:
                        on_step(i, step)

                    # Mark step start (always, for video composition timing)
                    step_start_time = time.time() - start_time
                    if recorder and recorder.is_recording:
                        marker = recorder.mark_event(
                            "step_start",
                            {
                                "index": i,
                                "action": step.action.value,
                                "target": step.target,
                                "description": step.description,
                            },
                        )
                    else:
                        marker = EventMarker(
                            timestamp=step_start_time,
                            event_type="step_start",
                            metadata={
                                "index": i,
                                "action": step.action.value,
                                "target": step.target,
                                "description": step.description,
                            },
                        )
                    markers.append(marker)

                    # Execute the step
                    await self._execute_step(step)

                    # Add delay for visual clarity (uses per-step delay if available)
                    delay = self._get_step_delay(i)
                    if delay > 0:
                        await asyncio.sleep(delay)

                    # Mark step end (always, for video composition timing)
                    step_end_time = time.time() - start_time
                    if recorder and recorder.is_recording:
                        marker = recorder.mark_event(
                            "step_end",
                            {
                                "index": i,
                            },
                        )
                    else:
                        marker = EventMarker(
                            timestamp=step_end_time,
                            event_type="step_end",
                            metadata={"index": i},
                        )
                    markers.append(marker)

                    # Safety Buffer: Add a gap between steps to prevent video bleed
                    # This time will be excluded from the final video segments
                    await asyncio.sleep(0.5)

            finally:
                if self._page:
                    try:
                        # Close page to ensure video is saved
                        await self._page.close()
                        # Capture video path
                        if self._page.video:
                            path = await self._page.video.path()
                            recorded_video = Path(path)
                    except Exception:
                        recorded_video = recorded_video
                await context.close()
                await self._browser.close()

        return markers, recorded_video

    async def _execute_step(self, step: TestStep) -> None:
        """Execute a single test step."""
        if self._page is None:
            raise ExecutorError("No page available")

        page = self._page

        match step.action:
            case ActionType.NAVIGATE:
                await page.goto(step.target)

            case ActionType.CLICK:
                locator = self._get_locator(page, step.target)
                await locator.click()

            case ActionType.TYPE:
                locator = self._get_locator(page, step.target)
                if step.value:
                    await locator.fill(step.value)
                else:
                    await locator.fill("")

            case ActionType.PRESS:
                locator = self._get_locator(page, step.target)
                if step.value:
                    await locator.press(step.value)

            case ActionType.HOVER:
                locator = self._get_locator(page, step.target)
                await locator.hover()

            case ActionType.SELECT:
                locator = self._get_locator(page, step.target)
                if step.value:
                    await locator.select_option(step.value)

            case ActionType.SCROLL:
                locator = self._get_locator(page, step.target)
                await locator.scroll_into_view_if_needed()

            case ActionType.WAIT:
                await self._execute_wait(step)

            case ActionType.ASSERT:
                await self._execute_assertion(step)

            case ActionType.SCREENSHOT:
                # Screenshot doesn't need special handling for recording
                pass

            case _:
                # Unknown action - skip
                pass

    def _get_locator(self, page: Page, target: str):
        """Get a Playwright locator from a target string."""
        # Handle get_by_* patterns from parsed code
        if target.startswith("get_by_role"):
            match = re.match(r"get_by_role\('([^']+)'", target)
            if match:
                return page.get_by_role(match.group(1))
        elif target.startswith("get_by_label"):
            match = re.match(r"get_by_label\('([^']+)'", target)
            if match:
                return page.get_by_label(match.group(1))
        elif target.startswith("get_by_text"):
            match = re.match(r"get_by_text\('([^']+)'", target)
            if match:
                return page.get_by_text(match.group(1))
        elif target.startswith("get_by_placeholder"):
            match = re.match(r"get_by_placeholder\('([^']+)'", target)
            if match:
                return page.get_by_placeholder(match.group(1))
        
        # Handle explicit xpath selector
        if target.startswith("xpath="):
            return page.locator(target)

        # Default: use as CSS selector
        return page.locator(target)

    async def _execute_wait(self, step: TestStep) -> None:
        """Execute a wait step."""
        if self._page is None:
            return

        source = step.source_code.lower()

        if "wait_for_load_state" in source:
            # Extract load state if specified
            if "networkidle" in source:
                await self._page.wait_for_load_state("networkidle")
            elif "domcontentloaded" in source:
                await self._page.wait_for_load_state("domcontentloaded")
            else:
                await self._page.wait_for_load_state("load")
        elif "wait_for_url" in source:
            # URL is in the target
            if step.target:
                await self._page.wait_for_url(step.target)
        elif "wait_for_selector" in source or step.target:
            await self._page.wait_for_selector(step.target)

    async def _execute_assertion(self, step: TestStep) -> None:
        """Execute an assertion step."""
        if self._page is None:
            return

        source = step.source_code.lower()

        # Get the locator if we have a target
        locator = None
        if step.target and not step.target.startswith("expect(page)"):
            locator = self._get_locator(self._page, step.target)

        # Determine assertion type from source code
        if "to_be_visible" in source:
            if locator:
                await async_expect(locator).to_be_visible()
        elif "to_be_hidden" in source:
            if locator:
                await async_expect(locator).to_be_hidden()
        elif "to_contain_text" in source and step.value:
            if locator:
                await async_expect(locator).to_contain_text(step.value)
        elif "to_have_text" in source and step.value:
            if locator:
                await async_expect(locator).to_have_text(step.value)
        elif "to_have_url" in source:
            # URL pattern is usually in target or value
            pattern = step.target or step.value
            if pattern:
                await async_expect(self._page).to_have_url(re.compile(pattern.replace("**", ".*")))
        elif "to_have_title" in source:
            if step.value:
                await async_expect(self._page).to_have_title(step.value)


class ExecutorError(Exception):
    """Raised when test execution fails."""

    pass