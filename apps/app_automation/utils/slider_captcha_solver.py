from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

try:
    import cv2
    import numpy as np

    SLIDER_SOLVER_AVAILABLE = True
    SLIDER_SOLVER_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    cv2 = None
    np = None
    SLIDER_SOLVER_AVAILABLE = False
    SLIDER_SOLVER_IMPORT_ERROR = exc


Bounds = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class SliderCaptchaSolution:
    confidence: float
    captcha_bounds: Bounds
    piece_bounds: Bounds
    target_bounds: Bounds
    slider_bounds: Bounds
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    distance_x: int
    debug_image_path: Path | None = None


class SliderCaptchaSolver:
    def solve(
        self,
        screenshot_path: Path,
        page_source: str,
        *,
        debug_image_path: Path | None = None,
        confidence_threshold: float = 0.2,
        x_offset: int = 0,
    ) -> SliderCaptchaSolution:
        if not SLIDER_SOLVER_AVAILABLE:
            raise RuntimeError(
                f"Slider solver dependencies are unavailable: {SLIDER_SOLVER_IMPORT_ERROR}"
            )

        image = cv2.imread(str(screenshot_path))
        if image is None:
            raise RuntimeError(f"Unable to read slider screenshot: {screenshot_path}")

        root = ET.fromstring(page_source)
        captcha_bounds = self._find_required_bounds(root, "tcImgArea", "slideBg")
        slider_bounds = self._find_slider_bounds(root)
        search_bounds = self._resolve_search_bounds(captcha_bounds, slider_bounds)

        x1, y1, x2, y2 = captcha_bounds
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            raise RuntimeError("Slider captcha crop is empty.")

        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edge_count = int(cv2.countNonZero(cv2.Canny(gray_crop, 80, 160)))
        gray_std = float(gray_crop.std())
        if gray_std < 8.0 or edge_count < 500:
            raise RuntimeError(
                f"Slider captcha is not ready: std={gray_std:.3f} edge_count={edge_count}"
            )

        bright_mask = cv2.inRange(gray_crop, 235, 255)
        bright_contours, _ = cv2.findContours(
            bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in bright_contours:
            x, y, w, h = cv2.boundingRect(contour)
            bright_area = float(cv2.contourArea(contour))
            if bright_area >= 100000 and w >= 300 and h >= 300:
                raise RuntimeError(
                    "Slider captcha placeholder is still loading: "
                    f"bright_area={bright_area:.1f} width={w} height={h}"
                )

        sx1, sy1, sx2, sy2 = search_bounds
        local_search = crop[sy1:sy2, sx1:sx2]
        if local_search.size == 0:
            raise RuntimeError("Slider captcha search crop is empty.")

        edge_map = cv2.Canny(cv2.cvtColor(local_search, cv2.COLOR_BGR2GRAY), 80, 160)
        target_box: Bounds | None = None
        confidence = 0.0
        try:
            piece_box, target_box, confidence = self._detect_piece_and_target(local_search, edge_map)
        except RuntimeError:
            target_reference = self._detect_reference_box(edge_map)
            if target_reference is None:
                raise
            piece_box, confidence = self._match_piece_box_from_reference(edge_map, target_reference)
            target_box = target_reference

        if target_box is None:
            target_box, confidence = self._match_target_box(edge_map, piece_box)
            contour_target = self._detect_target_contour_box(edge_map, piece_box)
            if contour_target is not None:
                contour_confidence = self._target_contour_confidence(piece_box, contour_target)
                if contour_confidence >= confidence:
                    target_box = contour_target
                    confidence = contour_confidence
        else:
            confidence = max(confidence, self._target_contour_confidence(piece_box, target_box))

        if confidence < confidence_threshold:
            raise RuntimeError(
                "Slider target confidence is too low: "
                f"confidence={confidence:.3f} threshold={confidence_threshold:.3f}"
            )

        absolute_piece = self._offset_bounds(piece_box, x1 + sx1, y1 + sy1)
        absolute_target = self._offset_bounds(target_box, x1 + sx1, y1 + sy1)
        slider_center_x, slider_center_y = self._center(slider_bounds)

        piece_center_x, _ = self._center(absolute_piece)
        target_center_x, _ = self._center(absolute_target)
        distance_x = target_center_x - piece_center_x
        if distance_x <= 0:
            raise RuntimeError(f"Detected slider distance is invalid: distance_x={distance_x}")

        handle_width = slider_bounds[2] - slider_bounds[0]
        min_end_x = slider_center_x + 20
        max_end_x = captcha_bounds[2] - max(20, handle_width // 2)
        end_x = max(min_end_x, min(max_end_x, slider_center_x + distance_x + x_offset))

        if debug_image_path is not None:
            self._save_debug_overlay(crop, piece_box, target_box, debug_image_path)

        return SliderCaptchaSolution(
            confidence=confidence,
            captcha_bounds=captcha_bounds,
            piece_bounds=absolute_piece,
            target_bounds=absolute_target,
            slider_bounds=slider_bounds,
            start_x=slider_center_x,
            start_y=slider_center_y,
            end_x=int(end_x),
            end_y=slider_center_y,
            distance_x=int(end_x - slider_center_x),
            debug_image_path=debug_image_path,
        )

    def _find_required_bounds(self, root: ET.Element, *resource_ids: str) -> Bounds:
        for resource_id in resource_ids:
            bounds = self._find_bounds(root, resource_id=resource_id)
            if bounds is not None:
                return bounds
        raise RuntimeError(f"Unable to locate slider captcha bounds from: {resource_ids}")

    def _find_slider_bounds(self, root: ET.Element) -> Bounds:
        by_text = self._find_bounds(root, text="slider")
        if by_text is not None:
            return by_text

        by_text_contains = self._find_bounds(root, text_contains="拖动下方滑块完成拼图")
        if by_text_contains is not None:
            return by_text_contains

        raise RuntimeError("Unable to locate slider handle bounds.")

    def _resolve_search_bounds(self, captcha_bounds: Bounds, slider_bounds: Bounds) -> Bounds:
        slider_top_local = max(0, slider_bounds[1] - captcha_bounds[1] - 24)
        search_bottom = min(captcha_bounds[3] - captcha_bounds[1], max(180, slider_top_local))
        return (0, 0, captcha_bounds[2] - captcha_bounds[0], search_bottom)

    def _detect_piece_and_target(self, search_image, edge_map) -> tuple[Bounds, Bounds, float]:
        candidates = self._build_piece_candidates(search_image, edge_map)
        if not candidates:
            raise RuntimeError("Unable to detect movable slider piece.")

        best_match: tuple[Bounds, Bounds, float] | None = None
        for piece_box in candidates:
            target_box, match_confidence = self._match_target_box(edge_map, piece_box)
            contour_target = self._detect_target_contour_box(edge_map, piece_box)
            confidence = match_confidence
            if contour_target is not None:
                contour_confidence = self._target_contour_confidence(piece_box, contour_target)
                if contour_confidence >= confidence:
                    target_box = contour_target
                    confidence = contour_confidence
            if target_box[0] <= piece_box[0]:
                continue
            if best_match is None or confidence > best_match[2]:
                best_match = (piece_box, target_box, confidence)

        if best_match is None:
            raise RuntimeError("Unable to detect movable slider piece.")
        return best_match

    def _build_piece_candidates(self, search_image, edge_map) -> list[Bounds]:
        candidates = self._detect_piece_boxes_from_white_mask(search_image)
        candidates.extend(self._detect_piece_boxes_from_edges(edge_map))
        return self._deduplicate_bounds(candidates)

    def _detect_piece_boxes_from_edges(self, edge_map) -> list[Bounds]:
        contours, _ = cv2.findContours(edge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        width = edge_map.shape[1]
        candidates: list[tuple[float, Bounds]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if x > int(width * 0.45):
                continue
            if y < int(edge_map.shape[0] * 0.12):
                continue
            if w < 70 or h < 70 or w > 180 or h > 180:
                continue
            aspect_ratio = w / float(h)
            if aspect_ratio < 0.65 or aspect_ratio > 1.35:
                continue
            edge_pixels = int(cv2.countNonZero(edge_map[y:y + h, x:x + w]))
            if edge_pixels < 120:
                continue
            density = edge_pixels / float(w * h)
            score = min(density * 15.0, 1.0) + min(w, h) / 220.0
            candidates.append((score, (x, y, x + w, y + h)))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [bounds for _, bounds in candidates[:6]]

    def _detect_piece_boxes_from_white_mask(self, search_image) -> list[Bounds]:
        hsv = cv2.cvtColor(search_image, cv2.COLOR_BGR2HSV)
        white_mask = cv2.inRange(hsv, (0, 0, 165), (180, 85, 255))
        kernel = np.ones((3, 3), np.uint8)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, kernel)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        width = search_image.shape[1]
        height = search_image.shape[0]
        candidates: list[tuple[float, Bounds]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if x > int(width * 0.42):
                continue
            if y < int(height * 0.18) or y > int(height * 0.78):
                continue
            if w < 80 or h < 80 or w > 180 or h > 180:
                continue
            aspect_ratio = w / float(h)
            if aspect_ratio < 0.7 or aspect_ratio > 1.3:
                continue
            area = float(cv2.contourArea(contour))
            fill_ratio = area / float(w * h)
            if fill_ratio < 0.18 or fill_ratio > 0.72:
                continue
            score = (1.0 - abs(1.0 - aspect_ratio)) * 0.55 + min(fill_ratio * 1.8, 1.0) * 0.45
            candidates.append((score, (x, y, x + w, y + h)))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [bounds for _, bounds in candidates[:6]]

    def _match_target_box(self, edge_map, piece_box: Bounds) -> tuple[Bounds, float]:
        x1, y1, x2, y2 = piece_box
        template = edge_map[y1:y2, x1:x2]
        result = cv2.matchTemplate(edge_map, template, cv2.TM_CCOEFF_NORMED)
        if result.size == 0:
            raise RuntimeError("Unable to build slider template match result.")

        result = result.copy()
        template_width = x2 - x1
        template_height = y2 - y1
        exclusion_x1 = max(0, x1 - template_width)
        exclusion_y1 = max(0, y1 - template_height)
        exclusion_x2 = min(result.shape[1], x1 + template_width)
        exclusion_y2 = min(result.shape[0], y1 + template_height)
        result[exclusion_y1:exclusion_y2, exclusion_x1:exclusion_x2] = -1

        piece_center_y = (y1 + y2) // 2
        vertical_tolerance = max(16, int(template_height * 0.22))
        min_center_y = piece_center_y - vertical_tolerance
        max_center_y = piece_center_y + vertical_tolerance
        for row in range(result.shape[0]):
            center_y = row + template_height // 2
            if center_y < min_center_y or center_y > max_center_y:
                result[row, :] = -1

        _, max_value, _, max_location = cv2.minMaxLoc(result)
        target_x, target_y = max_location
        return ((target_x, target_y, target_x + template_width, target_y + template_height), float(max_value))

    def _detect_target_contour_box(self, edge_map, piece_box: Bounds) -> Bounds | None:
        contours, _ = cv2.findContours(edge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        piece_x1, piece_y1, piece_x2, piece_y2 = piece_box
        piece_width = piece_x2 - piece_x1
        piece_height = piece_y2 - piece_y1
        piece_center_y = (piece_y1 + piece_y2) // 2
        width = edge_map.shape[1]

        candidates: list[tuple[float, int, int, int, int]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if x <= piece_x2 or x < int(width * 0.35) or y > int(edge_map.shape[0] * 0.55):
                continue
            aspect_ratio = w / float(h)
            if aspect_ratio < 0.65 or aspect_ratio > 1.4:
                continue
            if w < int(piece_width * 0.6) or w > int(piece_width * 1.5):
                continue
            if h < int(piece_height * 0.55) or h > int(piece_height * 1.5):
                continue
            edge_pixels = int(cv2.countNonZero(edge_map[y:y + h, x:x + w]))
            if edge_pixels < 120:
                continue

            center_y = y + h // 2
            if abs(center_y - piece_center_y) > max(18, int(piece_height * 0.25)):
                continue

            score = edge_pixels / float(max(w * h, 1))
            score += max(0.0, 1.0 - abs(center_y - piece_center_y) / max(piece_height, 1))
            candidates.append((score, x, y, x + w, y + h))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        _, x1, y1, x2, y2 = candidates[0]
        return (x1, y1, x2, y2)

    def _target_contour_confidence(self, piece_box: Bounds, target_box: Bounds) -> float:
        piece_width = piece_box[2] - piece_box[0]
        piece_height = piece_box[3] - piece_box[1]
        target_width = target_box[2] - target_box[0]
        target_height = target_box[3] - target_box[1]
        width_score = 1.0 - min(abs(target_width - piece_width) / max(piece_width, 1), 1.0)
        height_score = 1.0 - min(abs(target_height - piece_height) / max(piece_height, 1), 1.0)
        return max(0.0, (width_score + height_score) / 2.0)

    def _detect_reference_box(self, edge_map) -> Bounds | None:
        contours, _ = cv2.findContours(edge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        width = edge_map.shape[1]
        height = edge_map.shape[0]
        candidates: list[tuple[float, Bounds]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if x < int(width * 0.35):
                continue
            if y < int(height * 0.12) or y > int(height * 0.55):
                continue
            if w < 80 or h < 80 or w > 180 or h > 180:
                continue
            aspect_ratio = w / float(h)
            if aspect_ratio < 0.7 or aspect_ratio > 1.3:
                continue
            edge_pixels = int(cv2.countNonZero(edge_map[y:y + h, x:x + w]))
            if edge_pixels < 120:
                continue
            score = edge_pixels / float(max(w * h, 1))
            candidates.append((score, (x, y, x + w, y + h)))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _match_piece_box_from_reference(self, edge_map, target_reference: Bounds) -> tuple[Bounds, float]:
        reference_x1, reference_y1, reference_x2, reference_y2 = target_reference
        template_width = reference_x2 - reference_x1
        template_height = reference_y2 - reference_y1

        search_width = edge_map.shape[1]
        search_region = edge_map[:, :max(int(search_width * 0.45), template_width + 1)]
        template = edge_map[reference_y1:reference_y2, reference_x1:reference_x2]
        result = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
        if result.size == 0:
            raise RuntimeError("Unable to match slider piece from reference box.")

        piece_center_y = (reference_y1 + reference_y2) // 2
        vertical_tolerance = max(18, int(template_height * 0.25))
        for row in range(result.shape[0]):
            center_y = row + template_height // 2
            if abs(center_y - piece_center_y) > vertical_tolerance:
                result[row, :] = -1

        max_location = None
        max_value = -1.0
        for row in range(result.shape[0]):
            for col in range(result.shape[1]):
                score = float(result[row, col])
                if score > max_value:
                    max_value = score
                    max_location = (col, row)

        if max_location is None:
            raise RuntimeError("Unable to match slider piece from reference box.")

        piece_x, piece_y = max_location
        if piece_x >= reference_x1:
            raise RuntimeError("Matched slider piece is not left of the target hole.")

        return ((piece_x, piece_y, piece_x + template_width, piece_y + template_height), float(max_value))

    def _save_debug_overlay(self, crop, piece_box: Bounds, target_box: Bounds, output_path: Path) -> None:
        overlay = crop.copy()
        cv2.rectangle(overlay, (piece_box[0], piece_box[1]), (piece_box[2], piece_box[3]), (0, 255, 0), 3)
        cv2.rectangle(overlay, (target_box[0], target_box[1]), (target_box[2], target_box[3]), (0, 0, 255), 3)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), overlay)

    def _find_bounds(
        self,
        root: ET.Element,
        *,
        resource_id: str | None = None,
        text: str | None = None,
        text_contains: str | None = None,
    ) -> Bounds | None:
        for node in root.iter("node"):
            attrs = node.attrib
            node_resource_id = str(attrs.get("resource-id", "")).strip()
            node_text = str(attrs.get("text", "")).strip()
            if resource_id:
                if node_resource_id == resource_id or node_resource_id.split("/")[-1] == resource_id.split("/")[-1]:
                    bounds = self._parse_bounds(attrs.get("bounds"))
                    if bounds is not None:
                        return bounds
            if text and node_text == text:
                bounds = self._parse_bounds(attrs.get("bounds"))
                if bounds is not None:
                    return bounds
            if text_contains and text_contains in node_text:
                bounds = self._parse_bounds(attrs.get("bounds"))
                if bounds is not None:
                    return bounds
        return None

    def _parse_bounds(self, bounds: str | None) -> Bounds | None:
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(bounds or "").strip())
        if not match:
            return None
        return tuple(int(group) for group in match.groups())

    def _offset_bounds(self, bounds: Bounds, offset_x: int, offset_y: int) -> Bounds:
        x1, y1, x2, y2 = bounds
        return (x1 + offset_x, y1 + offset_y, x2 + offset_x, y2 + offset_y)

    def _center(self, bounds: Bounds) -> tuple[int, int]:
        x1, y1, x2, y2 = bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def _deduplicate_bounds(self, bounds_list: list[Bounds]) -> list[Bounds]:
        deduplicated: list[Bounds] = []
        for bounds in bounds_list:
            if bounds not in deduplicated:
                deduplicated.append(bounds)
        return deduplicated
