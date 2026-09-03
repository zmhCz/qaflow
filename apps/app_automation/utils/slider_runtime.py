from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from airtest.core.api import swipe

try:
    import allure

    ALLURE_AVAILABLE = True
except ImportError:  # pragma: no cover
    allure = None
    ALLURE_AVAILABLE = False

from .slider_captcha_solver import (
    SLIDER_SOLVER_AVAILABLE,
    SliderCaptchaSolution,
    SliderCaptchaSolver,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SliderHandlerConfig:
    success_target: Any = None
    appearance_timeout: float = 6.0
    settle_timeout: float = 5.0
    solve_timeout: float = 8.0
    max_attempts: int = 4
    confidence_threshold: float = 0.2
    duration_ms: int = 1200
    overshoot_px: int = 8
    post_login_timeout: float = 8.0
    x_offset: int = 0
    attempt_x_offsets: tuple[int, ...] = (0, 12, -12, 20)
    reload_between_attempts: bool = True


class SliderCaptchaHandler:
    def __init__(
        self,
        *,
        capture_snapshot_path: Callable[[str], Path],
        get_ui_source_safe: Callable[[], str],
        attach_file_if_possible: Callable[[Path, str, Any], None],
        target_exists: Callable[[Any], bool],
        tap_login_privacy_dialog_if_present: Callable[[], bool],
        wait_for_post_login_ready: Callable[..., bool],
        device_shell: Callable[[str], Any],
        find_selector_node: Callable[[dict[str, Any]], Any],
        node_center: Callable[[Any], Optional[tuple[int, int]]],
    ) -> None:
        self._capture_snapshot_path = capture_snapshot_path
        self._get_ui_source_safe = get_ui_source_safe
        self._attach_file_if_possible = attach_file_if_possible
        self._target_exists = target_exists
        self._tap_login_privacy_dialog_if_present = tap_login_privacy_dialog_if_present
        self._wait_for_post_login_ready = wait_for_post_login_ready
        self._device_shell = device_shell
        self._find_selector_node = find_selector_node
        self._node_center = node_center

    def handle(self, config: SliderHandlerConfig) -> None:
        logger.info(
            "Start slider handling: appearance_timeout=%s solve_timeout=%s max_attempts=%s",
            config.appearance_timeout,
            config.solve_timeout,
            config.max_attempts,
        )

        transition_deadline = time.time() + max(config.appearance_timeout, 1.0)
        while True:
            if config.success_target is not None:
                try:
                    if self._target_exists(config.success_target):
                        logger.info("Home target already exists before slider")
                        return
                except Exception as exc:
                    logger.debug("Pre-slider home target check failed: %s", exc)
            if self._tap_login_privacy_dialog_if_present():
                continue
            if self.is_slider_present():
                break
            if time.time() >= transition_deadline:
                logger.info("No privacy dialog or slider detected, continue next step")
                return
            time.sleep(0.35)

        last_error = "slider handling did not start"
        for attempt in range(1, max(1, config.max_attempts) + 1):
            offset_delta = 0
            if config.attempt_x_offsets:
                try:
                    offset_delta = int(
                        config.attempt_x_offsets[
                            min(attempt - 1, len(config.attempt_x_offsets) - 1)
                        ]
                    )
                except Exception:
                    offset_delta = 0

            effective_x_offset = config.x_offset + offset_delta
            logger.info(
                "Slider handling attempt %s/%s, x_offset=%s",
                attempt,
                config.max_attempts,
                effective_x_offset,
            )

            try:
                solution = self.solve(
                    attempt=attempt,
                    solve_timeout=config.solve_timeout,
                    confidence_threshold=config.confidence_threshold,
                    x_offset=effective_x_offset,
                )
                logger.info(
                    "Slider solved: confidence=%.3f distance_x=%s start=(%s,%s) end=(%s,%s)",
                    solution.confidence,
                    solution.distance_x,
                    solution.start_x,
                    solution.start_y,
                    solution.end_x,
                    solution.end_y,
                )
                self.perform_drag(
                    solution,
                    duration_ms=config.duration_ms,
                    overshoot_px=config.overshoot_px,
                )
                if self.wait_for_cleared(
                    config.settle_timeout,
                    success_target=config.success_target,
                ):
                    logger.info("Slider captcha cleared")
                    if self._wait_for_post_login_ready(
                        success_target=config.success_target,
                        timeout=config.post_login_timeout,
                    ):
                        logger.info("Post-login transition completed")
                        return
                    last_error = "post-login ready target not found after slider cleared"
                    logger.warning(last_error)
                    continue
                last_error = "slider page still present after drag"
                logger.warning(last_error)
            except Exception as exc:
                error_text = str(exc) or repr(exc)
                last_error = f"{type(exc).__name__}: {error_text}"
                logger.warning("Slider handling failed, attempt=%s, error=%s", attempt, last_error)

            if attempt < config.max_attempts and config.reload_between_attempts:
                self.tap_reload()

        raise RuntimeError(f"Slider captcha handling failed: {last_error}")

    def is_slider_present(self, ui_source: Optional[str] = None) -> bool:
        source = (ui_source or self._get_ui_source_safe() or "").lower()
        if not source:
            return False
        slider_signals = (
            "tcimgarea",
            "slidebg",
            "tcaptcha",
            "secverify",
            "instructiontext",
            "drag the slider",
            "鎷栧姩涓嬫柟婊戝潡瀹屾垚鎷煎浘",
            'text="slider"',
            'resource-id="reload"',
        )
        return any(signal in source for signal in slider_signals)

    def wait_for_cleared(
        self,
        timeout: float,
        *,
        success_target: Any = None,
        interval: float = 0.4,
    ) -> bool:
        deadline = time.time() + max(float(timeout or 0), 0.0)
        while True:
            if success_target is not None:
                try:
                    if self._target_exists(success_target):
                        return True
                except Exception as exc:
                    logger.debug("Check slider success target failed: %s", exc)

            ui_source = self._get_ui_source_safe()
            if ui_source and not self.is_slider_present(ui_source):
                return True

            if time.time() >= deadline:
                return False
            time.sleep(interval)

    def solve(
        self,
        *,
        attempt: int,
        solve_timeout: float,
        confidence_threshold: float,
        x_offset: int,
    ) -> SliderCaptchaSolution:
        if not SLIDER_SOLVER_AVAILABLE:
            raise RuntimeError("Slider solver dependencies are unavailable, check opencv/numpy.")

        solver = SliderCaptchaSolver()
        deadline = time.time() + max(float(solve_timeout or 0), 4.0)
        last_error = "slider solve did not start"

        while True:
            screenshot_path = self._capture_snapshot_path(f"slider_attempt_{attempt}")
            debug_path = screenshot_path.with_name(f"{screenshot_path.stem}_match.png")
            page_source = self._get_ui_source_safe()
            if not self.is_slider_present(page_source):
                raise RuntimeError("Slider captcha is no longer present.")

            try:
                solution = solver.solve(
                    screenshot_path,
                    page_source,
                    debug_image_path=debug_path,
                    confidence_threshold=confidence_threshold,
                    x_offset=x_offset,
                )
                if ALLURE_AVAILABLE:
                    self._attach_file_if_possible(
                        screenshot_path,
                        name=f"slider-attempt-{attempt}",
                        attachment_type=allure.attachment_type.PNG,
                    )
                    self._attach_file_if_possible(
                        debug_path,
                        name=f"slider-match-{attempt}",
                        attachment_type=allure.attachment_type.PNG,
                    )
                return solution
            except RuntimeError as exc:
                last_error = str(exc)
                lowered = last_error.lower()
                transient_markers = (
                    "not ready",
                    "still loading",
                    "placeholder",
                    "unable to locate slider",
                    "captcha crop is empty",
                    "search crop is empty",
                    "confidence is too low",
                )
                if not any(marker in lowered for marker in transient_markers):
                    raise
                logger.info("Slider detection retry: attempt=%s error=%s", attempt, last_error)
                if time.time() >= deadline:
                    break
                time.sleep(0.5)

            if time.time() >= deadline:
                break

        raise RuntimeError(last_error)

    def perform_drag(
        self,
        solution: SliderCaptchaSolution,
        *,
        duration_ms: int,
        overshoot_px: int,
    ) -> None:
        start_x = int(solution.start_x)
        start_y = int(solution.start_y)
        end_x = int(min(solution.captcha_bounds[2] - 20, solution.end_x + max(0, overshoot_px)))
        end_y = int(solution.end_y)
        logger.info(
            "Execute slider drag: (%s,%s) -> (%s,%s), duration_ms=%s, confidence=%.3f, distance_x=%s",
            start_x,
            start_y,
            end_x,
            end_y,
            duration_ms,
            solution.confidence,
            solution.distance_x,
        )
        try:
            self._device_shell(f"input swipe {start_x} {start_y} {end_x} {end_y} {int(duration_ms)}")
        except Exception:
            logger.exception("ADB slider drag failed, fallback to Airtest swipe")
            swipe((start_x, start_y), (end_x, end_y), duration=max(duration_ms / 1000.0, 0.2))
        time.sleep(0.3)

    def tap_reload(self) -> bool:
        reload_selector = {
            "_selector_kind": "android_selector",
            "resource_id": "reload",
        }
        node = self._find_selector_node(reload_selector)
        if not node:
            logger.info("Slider reload button not found, skip reload")
            return False
        center = self._node_center(node)
        if not center:
            logger.info("Slider reload button has no bounds, skip reload")
            return False
        x, y = center
        logger.info("Tap slider reload button: (%s,%s)", x, y)
        self._device_shell(f"input tap {x} {y}")
        time.sleep(0.6)
        return True
