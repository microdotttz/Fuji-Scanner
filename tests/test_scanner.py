"""Tests for scanner module."""

import pytest
from PIL import Image

from fuji_tcg_scanner.scanner import (
    FujitsuScanner,
    MockScanner,
    PaperSize,
    ScanMode,
    ScannerConfig,
    ScanResult,
    ScanSource,
)


class TestScannerConfig:
    """Tests for ScannerConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ScannerConfig()
        assert config.resolution == 600
        assert config.mode == ScanMode.COLOR
        assert config.source == ScanSource.FLATBED

    def test_for_tcg_cards(self):
        """Test TCG card preset configuration."""
        config = ScannerConfig().for_tcg_cards()
        assert config.resolution == 600
        assert config.mode == ScanMode.COLOR
        assert config.brightness == 5
        assert config.contrast == 10

    def test_for_batch_scanning(self):
        """Test batch scanning configuration."""
        config = ScannerConfig().for_batch_scanning(count=10)
        assert config.source == ScanSource.ADF_FRONT
        assert config.batch_mode is True
        assert config.page_count == 10


class TestMockScanner:
    """Tests for MockScanner."""

    def test_mock_scanner_init(self):
        """Test mock scanner initialization."""
        scanner = MockScanner()
        assert scanner._device_name == "mock:fujitsu:fi-6140Z"

    def test_mock_list_devices(self):
        """Test listing mock devices."""
        scanner = MockScanner()
        devices = scanner.list_devices()
        assert len(devices) == 1
        assert "fujitsu" in devices[0][1].lower()

    def test_mock_scan(self):
        """Test mock scanning."""
        scanner = MockScanner()
        scanner.open()

        config = ScannerConfig(
            resolution=300,
            mode=ScanMode.COLOR,
            bottom_right_x=100.0,
            bottom_right_y=100.0,
        )
        scanner.configure(config)

        result = scanner.scan()

        assert isinstance(result, ScanResult)
        assert isinstance(result.image, Image.Image)
        assert result.resolution == 300
        assert result.mode == "Color"

        scanner.close()

    def test_mock_context_manager(self):
        """Test mock scanner as context manager."""
        with MockScanner() as scanner:
            result = scanner.scan()
            assert result.image is not None


class TestScanResult:
    """Tests for ScanResult."""

    def test_scan_result_properties(self):
        """Test ScanResult properties."""
        image = Image.new("RGB", (100, 100))
        result = ScanResult(
            image=image,
            width=100,
            height=100,
            resolution=600,
            mode="Color",
            source="Flatbed",
        )

        assert result.width == 100
        assert result.height == 100
        assert result.resolution == 600


class TestPaperSize:
    """Tests for PaperSize enum."""

    def test_tcg_standard_size(self):
        """Test standard TCG card size."""
        width, height = PaperSize.TCG_STANDARD.value
        assert width == 63.5  # mm
        assert height == 88.9  # mm

    def test_tcg_japanese_size(self):
        """Test Japanese TCG card size."""
        width, height = PaperSize.TCG_JAPANESE.value
        assert width == 59.0
        assert height == 86.0
