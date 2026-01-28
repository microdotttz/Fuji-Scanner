"""Tests for card detector module."""

import numpy as np
import pytest
from PIL import Image

from fuji_tcg_scanner.card_detector import (
    CardDetector,
    DetectedCard,
    DetectionConfig,
)


class TestDetectionConfig:
    """Tests for DetectionConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DetectionConfig()
        assert config.min_card_area == 100000
        assert config.max_cards == 9
        assert config.expected_aspect_ratio == pytest.approx(0.714, rel=0.01)


class TestDetectedCard:
    """Tests for DetectedCard."""

    def test_card_properties(self):
        """Test DetectedCard properties."""
        card = DetectedCard(
            bbox=(100, 200, 300, 400),
            corners=[(100, 200), (400, 200), (400, 600), (100, 600)],
            angle=0.0,
            confidence=0.95,
            index=0,
        )

        assert card.x == 100
        assert card.y == 200
        assert card.width == 300
        assert card.height == 400
        assert card.center == (250, 400)
        assert card.area == 120000
        assert card.aspect_ratio == pytest.approx(0.75, rel=0.01)


class TestCardDetector:
    """Tests for CardDetector."""

    @pytest.fixture
    def detector(self):
        """Create card detector instance."""
        return CardDetector()

    @pytest.fixture
    def card_image(self):
        """Create test image with a card-like rectangle."""
        # Create white background
        img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        img_array = np.array(img)

        # Draw a card-like rectangle (dark border)
        # Standard card proportions: 63.5 x 88.9 mm
        card_width = 200
        card_height = int(200 / 0.714)  # ~280
        x, y = 300, 150

        # Card border
        img_array[y:y+card_height, x:x+card_width] = [50, 50, 50]
        # Card interior
        img_array[y+5:y+card_height-5, x+5:x+card_width-5] = [240, 240, 250]

        return Image.fromarray(img_array)

    @pytest.fixture
    def blank_image(self):
        """Create blank test image."""
        return Image.new("RGB", (800, 600), color=(255, 255, 255))

    def test_detect_no_cards(self, detector, blank_image):
        """Test detection on blank image."""
        cards = detector.detect(blank_image)
        assert len(cards) == 0

    def test_estimate_dpi(self, detector):
        """Test DPI estimation."""
        card = DetectedCard(
            bbox=(0, 0, 1500, 2100),  # 600 DPI card
            corners=[],
            angle=0.0,
            confidence=1.0,
        )

        dpi = detector.estimate_dpi(card)
        assert 550 < dpi < 650  # Should be around 600 DPI

    def test_visualize_detections(self, detector, blank_image):
        """Test detection visualization."""
        cards = [
            DetectedCard(
                bbox=(100, 100, 200, 280),
                corners=[(100, 100), (300, 100), (300, 380), (100, 380)],
                angle=0.0,
                confidence=0.9,
                index=0,
            )
        ]

        result = detector.visualize_detections(blank_image, cards)
        assert result.size == blank_image.size

    def test_auto_crop_single_no_card(self, detector, blank_image):
        """Test auto crop with no card detected."""
        result_image, card = detector.auto_crop_single(blank_image)
        assert result_image.size == blank_image.size
        assert card is None


class TestOrderCorners:
    """Tests for corner ordering."""

    def test_order_corners(self):
        """Test corner ordering logic."""
        detector = CardDetector()

        # Unordered corners
        corners = np.array([
            [100, 400],  # bottom-left
            [400, 100],  # top-right
            [100, 100],  # top-left
            [400, 400],  # bottom-right
        ])

        ordered = detector._order_corners(corners)

        # Should be: top-left, top-right, bottom-right, bottom-left
        assert ordered[0] == (100, 100)  # top-left
        assert ordered[1] == (400, 100)  # top-right
        assert ordered[2] == (400, 400)  # bottom-right
        assert ordered[3] == (100, 400)  # bottom-left
