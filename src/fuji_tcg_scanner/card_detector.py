"""
Card detection module for automatic TCG card identification and cropping.

This module uses computer vision techniques to detect TCG cards in scanned
images and extract them with proper alignment.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class DetectionConfig:
    """Configuration for card detection."""

    # Card size constraints (in pixels at 600 DPI)
    min_card_area: int = 100000  # Minimum area in pixels
    max_card_area: int = 5000000  # Maximum area in pixels

    # Aspect ratio tolerance
    expected_aspect_ratio: float = 0.714  # 63.5/88.9
    aspect_ratio_tolerance: float = 0.1

    # Edge detection parameters
    canny_low: int = 50
    canny_high: int = 150

    # Contour filtering
    min_contour_points: int = 4
    approx_epsilon_factor: float = 0.02

    # Card border detection
    border_margin: int = 5  # Pixels to include around detected card

    # Multiple card detection
    max_cards: int = 9  # Maximum cards to detect (3x3 grid common)
    min_card_spacing: int = 50  # Minimum pixels between cards

    # Background detection
    background_threshold: int = 240  # Brightness threshold for white background

    # Rotation correction
    max_rotation_angle: float = 15.0  # Maximum auto-rotation angle


@dataclass
class DetectedCard:
    """Represents a detected card in an image."""

    # Bounding box (x, y, width, height)
    bbox: Tuple[int, int, int, int]

    # Corner points in clockwise order from top-left
    corners: List[Tuple[int, int]]

    # Rotation angle from horizontal
    angle: float

    # Detection confidence (0-1)
    confidence: float

    # Card index (for multiple cards)
    index: int = 0

    # Extracted card image (set after extraction)
    image: Optional[Image.Image] = None

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def width(self) -> int:
        return self.bbox[2]

    @property
    def height(self) -> int:
        return self.bbox[3]

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def aspect_ratio(self) -> float:
        if self.height == 0:
            return 0
        return self.width / self.height


class CardDetector:
    """
    Detects and extracts TCG cards from scanned images.

    Uses contour detection and geometric analysis to find
    rectangular card shapes and extract them with proper alignment.
    """

    # Standard TCG card dimensions
    STANDARD_CARD_WIDTH_MM = 63.5
    STANDARD_CARD_HEIGHT_MM = 88.9
    STANDARD_ASPECT_RATIO = STANDARD_CARD_WIDTH_MM / STANDARD_CARD_HEIGHT_MM

    def __init__(self, config: Optional[DetectionConfig] = None):
        """
        Initialize the card detector.

        Args:
            config: Detection configuration. Uses defaults if None.
        """
        self.config = config or DetectionConfig()

    def detect(self, image: Image.Image) -> List[DetectedCard]:
        """
        Detect all TCG cards in an image.

        Args:
            image: Input PIL Image.

        Returns:
            List of DetectedCard objects.
        """
        logger.info(f"Detecting cards in {image.width}x{image.height} image")

        # Convert to OpenCV format
        img_array = np.array(image)
        if len(img_array.shape) == 2:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)

        # Preprocessing
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Edge detection
        edges = cv2.Canny(
            blurred,
            self.config.canny_low,
            self.config.canny_high,
        )

        # Dilate edges to connect broken lines
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            edges,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        # Filter and score contours
        candidates = []
        for contour in contours:
            card = self._analyze_contour(contour, img_array.shape)
            if card is not None:
                candidates.append(card)

        # Sort by confidence and position
        candidates.sort(key=lambda c: (-c.confidence, c.y, c.x))

        # Remove overlapping detections
        cards = self._remove_overlaps(candidates)

        # Limit to max cards
        cards = cards[: self.config.max_cards]

        # Assign indices
        for i, card in enumerate(cards):
            card.index = i

        logger.info(f"Detected {len(cards)} card(s)")
        return cards

    def _analyze_contour(
        self, contour: np.ndarray, image_shape: Tuple[int, ...]
    ) -> Optional[DetectedCard]:
        """
        Analyze a contour to determine if it's a card.

        Args:
            contour: OpenCV contour.
            image_shape: Shape of the source image.

        Returns:
            DetectedCard if valid, None otherwise.
        """
        # Get contour area
        area = cv2.contourArea(contour)
        if area < self.config.min_card_area or area > self.config.max_card_area:
            return None

        # Approximate contour to polygon
        epsilon = self.config.approx_epsilon_factor * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        # Must be quadrilateral
        if len(approx) != 4:
            return None

        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(approx)

        # Check aspect ratio
        aspect = min(w, h) / max(w, h) if max(w, h) > 0 else 0
        if abs(aspect - self.config.expected_aspect_ratio) > self.config.aspect_ratio_tolerance:
            return None

        # Get rotated rectangle for angle
        rect = cv2.minAreaRect(contour)
        angle = rect[2]

        # Normalize angle
        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90

        # Skip if rotation is too extreme
        if abs(angle) > self.config.max_rotation_angle:
            return None

        # Order corners (top-left, top-right, bottom-right, bottom-left)
        corners = self._order_corners(approx.reshape(4, 2))

        # Calculate confidence score
        confidence = self._calculate_confidence(contour, approx, area, aspect)

        return DetectedCard(
            bbox=(x, y, w, h),
            corners=corners,
            angle=angle,
            confidence=confidence,
        )

    def _order_corners(
        self, corners: np.ndarray
    ) -> List[Tuple[int, int]]:
        """
        Order corners in clockwise order starting from top-left.

        Args:
            corners: Array of 4 corner points.

        Returns:
            Ordered list of corner tuples.
        """
        # Sort by sum of coordinates (top-left has smallest sum)
        sorted_by_sum = corners[np.argsort(corners.sum(axis=1))]
        top_left = sorted_by_sum[0]
        bottom_right = sorted_by_sum[3]

        # Sort by difference (top-right has largest difference y-x)
        sorted_by_diff = corners[np.argsort(np.diff(corners, axis=1).flatten())]
        top_right = sorted_by_diff[3]
        bottom_left = sorted_by_diff[0]

        return [
            (int(top_left[0]), int(top_left[1])),
            (int(top_right[0]), int(top_right[1])),
            (int(bottom_right[0]), int(bottom_right[1])),
            (int(bottom_left[0]), int(bottom_left[1])),
        ]

    def _calculate_confidence(
        self,
        contour: np.ndarray,
        approx: np.ndarray,
        area: float,
        aspect: float,
    ) -> float:
        """
        Calculate detection confidence score.

        Args:
            contour: Original contour.
            approx: Approximated polygon.
            area: Contour area.
            aspect: Aspect ratio.

        Returns:
            Confidence score from 0 to 1.
        """
        score = 1.0

        # Aspect ratio match (40% weight)
        aspect_diff = abs(aspect - self.STANDARD_ASPECT_RATIO)
        aspect_score = max(0, 1 - aspect_diff / 0.2)
        score *= 0.4 + 0.6 * aspect_score

        # Contour convexity (30% weight)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        if hull_area > 0:
            convexity = area / hull_area
            score *= 0.3 + 0.7 * convexity

        # Rectangle fit (30% weight)
        rect_area = cv2.minAreaRect(contour)[1][0] * cv2.minAreaRect(contour)[1][1]
        if rect_area > 0:
            rect_fit = area / rect_area
            score *= 0.3 + 0.7 * rect_fit

        return min(1.0, max(0.0, score))

    def _remove_overlaps(
        self, cards: List[DetectedCard]
    ) -> List[DetectedCard]:
        """
        Remove overlapping card detections, keeping highest confidence.

        Args:
            cards: List of detected cards.

        Returns:
            Filtered list without overlaps.
        """
        if len(cards) <= 1:
            return cards

        result = []
        for card in cards:
            overlap = False
            for kept in result:
                if self._boxes_overlap(card.bbox, kept.bbox):
                    overlap = True
                    break
            if not overlap:
                result.append(card)

        return result

    def _boxes_overlap(
        self,
        box1: Tuple[int, int, int, int],
        box2: Tuple[int, int, int, int],
        threshold: float = 0.3,
    ) -> bool:
        """
        Check if two bounding boxes overlap significantly.

        Args:
            box1: First box (x, y, w, h).
            box2: Second box (x, y, w, h).
            threshold: Overlap ratio threshold.

        Returns:
            True if boxes overlap more than threshold.
        """
        x1, y1, w1, h1 = box1
        x2, y2, w2, h2 = box2

        # Calculate intersection
        ix1 = max(x1, x2)
        iy1 = max(y1, y2)
        ix2 = min(x1 + w1, x2 + w2)
        iy2 = min(y1 + h1, y2 + h2)

        if ix2 <= ix1 or iy2 <= iy1:
            return False

        intersection = (ix2 - ix1) * (iy2 - iy1)
        union = w1 * h1 + w2 * h2 - intersection

        return intersection / union > threshold if union > 0 else False

    def extract(
        self,
        image: Image.Image,
        card: DetectedCard,
        correct_perspective: bool = True,
    ) -> Image.Image:
        """
        Extract a detected card from the image.

        Args:
            image: Source image.
            card: Detected card to extract.
            correct_perspective: Apply perspective correction.

        Returns:
            Extracted card image.
        """
        img_array = np.array(image)

        if correct_perspective and abs(card.angle) > 0.5:
            # Apply perspective transform
            return self._perspective_extract(img_array, card)
        else:
            # Simple crop with margin
            margin = self.config.border_margin
            x1 = max(0, card.x - margin)
            y1 = max(0, card.y - margin)
            x2 = min(image.width, card.x + card.width + margin)
            y2 = min(image.height, card.y + card.height + margin)

            return image.crop((x1, y1, x2, y2))

    def _perspective_extract(
        self, img_array: np.ndarray, card: DetectedCard
    ) -> Image.Image:
        """
        Extract card with perspective correction.

        Args:
            img_array: Source image array.
            card: Detected card.

        Returns:
            Perspective-corrected card image.
        """
        # Source points (detected corners)
        src_points = np.array(card.corners, dtype=np.float32)

        # Calculate output dimensions based on longest edges
        width_top = np.linalg.norm(
            np.array(card.corners[0]) - np.array(card.corners[1])
        )
        width_bottom = np.linalg.norm(
            np.array(card.corners[3]) - np.array(card.corners[2])
        )
        height_left = np.linalg.norm(
            np.array(card.corners[0]) - np.array(card.corners[3])
        )
        height_right = np.linalg.norm(
            np.array(card.corners[1]) - np.array(card.corners[2])
        )

        max_width = int(max(width_top, width_bottom))
        max_height = int(max(height_left, height_right))

        # Destination points
        dst_points = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype=np.float32)

        # Compute perspective transform
        matrix = cv2.getPerspectiveTransform(src_points, dst_points)

        # Apply transform
        warped = cv2.warpPerspective(
            img_array,
            matrix,
            (max_width, max_height),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REPLICATE,
        )

        return Image.fromarray(warped)

    def extract_all(
        self,
        image: Image.Image,
        cards: Optional[List[DetectedCard]] = None,
    ) -> List[DetectedCard]:
        """
        Detect and extract all cards from an image.

        Args:
            image: Source image.
            cards: Pre-detected cards (will detect if None).

        Returns:
            List of DetectedCard objects with extracted images.
        """
        if cards is None:
            cards = self.detect(image)

        for card in cards:
            card.image = self.extract(image, card)

        return cards

    def auto_crop_single(
        self, image: Image.Image
    ) -> Tuple[Image.Image, Optional[DetectedCard]]:
        """
        Automatically detect and crop a single card from an image.

        Convenience method for when exactly one card is expected.

        Args:
            image: Source image.

        Returns:
            Tuple of (cropped image, detected card info).
            Returns (original image, None) if no card detected.
        """
        cards = self.detect(image)

        if not cards:
            logger.warning("No card detected, returning original image")
            return image, None

        # Use highest confidence card
        best_card = max(cards, key=lambda c: c.confidence)
        best_card.image = self.extract(image, best_card)

        return best_card.image, best_card

    def detect_grid(
        self,
        image: Image.Image,
        rows: int = 3,
        cols: int = 3,
    ) -> List[DetectedCard]:
        """
        Detect cards arranged in a grid pattern.

        Useful for batch scanning multiple cards at once.

        Args:
            image: Source image with cards in grid.
            rows: Expected number of rows.
            cols: Expected number of columns.

        Returns:
            List of detected cards ordered by grid position.
        """
        cards = self.detect(image)

        if len(cards) == 0:
            return []

        # Sort by position (top to bottom, left to right)
        # First group by approximate row
        row_threshold = image.height / (rows * 2)

        rows_grouped: List[List[DetectedCard]] = []
        for card in sorted(cards, key=lambda c: c.y):
            placed = False
            for row in rows_grouped:
                if abs(card.y - row[0].y) < row_threshold:
                    row.append(card)
                    placed = True
                    break
            if not placed:
                rows_grouped.append([card])

        # Sort each row by x position
        result = []
        for row in rows_grouped:
            row.sort(key=lambda c: c.x)
            result.extend(row)

        # Re-index
        for i, card in enumerate(result):
            card.index = i

        return result

    def estimate_dpi(
        self,
        card: DetectedCard,
        card_width_mm: float = STANDARD_CARD_WIDTH_MM,
    ) -> int:
        """
        Estimate the scanning DPI based on detected card size.

        Args:
            card: Detected card.
            card_width_mm: Known card width in mm.

        Returns:
            Estimated DPI.
        """
        # Width in inches
        width_inches = card_width_mm / 25.4

        # Pixels per inch
        dpi = int(card.width / width_inches)

        return dpi

    def visualize_detections(
        self,
        image: Image.Image,
        cards: List[DetectedCard],
        show_corners: bool = True,
        show_index: bool = True,
    ) -> Image.Image:
        """
        Create visualization of detected cards for debugging.

        Args:
            image: Source image.
            cards: Detected cards.
            show_corners: Draw corner points.
            show_index: Show card index numbers.

        Returns:
            Image with detection overlays.
        """
        img_array = np.array(image).copy()

        for card in cards:
            # Draw bounding box
            color = (0, 255, 0)  # Green
            cv2.rectangle(
                img_array,
                (card.x, card.y),
                (card.x + card.width, card.y + card.height),
                color,
                3,
            )

            # Draw corners
            if show_corners:
                for i, corner in enumerate(card.corners):
                    cv2.circle(img_array, corner, 8, (255, 0, 0), -1)
                    if show_index:
                        cv2.putText(
                            img_array,
                            str(i),
                            (corner[0] + 10, corner[1]),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 255, 255),
                            2,
                        )

            # Draw card index and confidence
            if show_index:
                label = f"#{card.index} ({card.confidence:.2f})"
                cv2.putText(
                    img_array,
                    label,
                    (card.x, card.y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 0),
                    2,
                )

        return Image.fromarray(img_array)
