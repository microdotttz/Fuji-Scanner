"""Tests for image processor module."""

import numpy as np
import pytest
from PIL import Image

from fuji_tcg_scanner.image_processor import (
    ColorProfile,
    ImageProcessor,
    OutputFormat,
    ProcessingConfig,
)


class TestProcessingConfig:
    """Tests for ProcessingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ProcessingConfig()
        assert config.brightness == 1.0
        assert config.contrast == 1.0
        assert config.saturation == 1.0
        assert config.sharpness == 1.2
        assert config.white_balance is True
        assert config.denoise is True
        assert config.auto_crop is True

    def test_archival_preset(self):
        """Test archival preset configuration."""
        config = ProcessingConfig.for_archival()
        assert config.output_format == OutputFormat.PNG
        assert config.auto_crop is True

    def test_sharing_preset(self):
        """Test sharing preset configuration."""
        config = ProcessingConfig.for_sharing()
        assert config.output_format == OutputFormat.JPEG
        assert config.saturation > 1.0

    def test_grading_preset(self):
        """Test grading preset configuration."""
        config = ProcessingConfig.for_grading()
        assert config.color_profile == ColorProfile.NEUTRAL
        assert config.denoise is False
        assert config.output_format == OutputFormat.TIFF


class TestImageProcessor:
    """Tests for ImageProcessor."""

    @pytest.fixture
    def processor(self):
        """Create image processor instance."""
        return ImageProcessor()

    @pytest.fixture
    def test_image(self):
        """Create test image."""
        return Image.new("RGB", (100, 100), color=(128, 128, 128))

    def test_adjust_brightness(self, processor, test_image):
        """Test brightness adjustment."""
        # No change
        result = processor.adjust_brightness(test_image, 1.0)
        assert result.size == test_image.size

        # Increase brightness
        result = processor.adjust_brightness(test_image, 1.5)
        assert result.size == test_image.size

    def test_adjust_contrast(self, processor, test_image):
        """Test contrast adjustment."""
        result = processor.adjust_contrast(test_image, 1.2)
        assert result.size == test_image.size

    def test_adjust_saturation(self, processor, test_image):
        """Test saturation adjustment."""
        result = processor.adjust_saturation(test_image, 1.1)
        assert result.size == test_image.size

    def test_adjust_sharpness(self, processor, test_image):
        """Test sharpness adjustment."""
        result = processor.adjust_sharpness(test_image, 1.5)
        assert result.size == test_image.size

    def test_apply_gamma(self, processor, test_image):
        """Test gamma correction."""
        result = processor.apply_gamma(test_image, 1.2)
        assert result.size == test_image.size

        # No change when gamma is 1.0
        result = processor.apply_gamma(test_image, 1.0)
        assert result == test_image

    def test_auto_white_balance(self, processor, test_image):
        """Test automatic white balance."""
        result = processor.auto_white_balance(test_image)
        assert result.size == test_image.size

    def test_reduce_noise(self, processor, test_image):
        """Test noise reduction."""
        result = processor.reduce_noise(test_image, strength=5)
        assert result.size == test_image.size

    def test_resize(self, processor, test_image):
        """Test image resizing."""
        # Double size
        result = processor.resize(test_image, 2.0)
        assert result.width == 200
        assert result.height == 200

        # Half size
        result = processor.resize(test_image, 0.5)
        assert result.width == 50
        assert result.height == 50

        # No change
        result = processor.resize(test_image, 1.0)
        assert result == test_image

    def test_rotate(self, processor, test_image):
        """Test image rotation."""
        result = processor.rotate(test_image, 45)
        # Expanded canvas will be larger
        assert result.width >= test_image.width
        assert result.height >= test_image.height

    def test_crop(self, processor, test_image):
        """Test image cropping."""
        result = processor.crop(test_image, (10, 10, 50, 50))
        assert result.width == 40
        assert result.height == 40

    def test_add_border(self, processor, test_image):
        """Test adding border."""
        result = processor.add_border(test_image, width=10)
        assert result.width == 120
        assert result.height == 120

    def test_create_thumbnail(self, processor, test_image):
        """Test thumbnail creation."""
        # Create larger test image
        large_image = Image.new("RGB", (1000, 1000))
        result = processor.create_thumbnail(large_image, max_size=100)
        assert max(result.width, result.height) <= 100

    def test_analyze_image(self, processor, test_image):
        """Test image analysis."""
        analysis = processor.analyze_image(test_image)

        assert "width" in analysis
        assert "height" in analysis
        assert "mean_brightness" in analysis
        assert "sharpness_score" in analysis
        assert analysis["width"] == 100
        assert analysis["height"] == 100

    def test_full_processing_pipeline(self, processor, test_image):
        """Test complete processing pipeline."""
        result = processor.process(test_image)
        assert result.size == test_image.size
        assert result.mode == "RGB"


class TestColorProfile:
    """Tests for ColorProfile enum."""

    def test_all_profiles_exist(self):
        """Test all expected profiles exist."""
        profiles = [
            ColorProfile.STANDARD,
            ColorProfile.POKEMON,
            ColorProfile.MTG,
            ColorProfile.YUGIOH,
            ColorProfile.SPORTS,
            ColorProfile.VIVID,
            ColorProfile.NEUTRAL,
        ]
        assert len(profiles) == 7

    def test_apply_color_profile(self):
        """Test applying different color profiles."""
        processor = ImageProcessor()
        test_image = Image.new("RGB", (100, 100), color=(128, 128, 128))

        for profile in ColorProfile:
            result = processor.apply_color_profile(test_image, profile)
            assert result.size == test_image.size
