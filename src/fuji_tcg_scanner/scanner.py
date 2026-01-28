"""
Scanner interface module for Fujitsu fi-6140z scanner.

This module provides a high-level interface to the SANE scanner backend,
with optimized settings for TCG card scanning.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from PIL import Image

logger = logging.getLogger(__name__)


class ScanMode(Enum):
    """Scan color modes."""

    COLOR = "Color"
    GRAYSCALE = "Gray"
    LINEART = "Lineart"


class ScanSource(Enum):
    """Scanner paper source."""

    FLATBED = "Flatbed"
    ADF_FRONT = "ADF Front"
    ADF_BACK = "ADF Back"
    ADF_DUPLEX = "ADF Duplex"


class PaperSize(Enum):
    """Predefined paper sizes for scanning."""

    # TCG Card standard sizes (in mm)
    TCG_STANDARD = (63.5, 88.9)  # 2.5" x 3.5" - Pokemon, MTG, Yu-Gi-Oh
    TCG_JAPANESE = (59.0, 86.0)  # Japanese standard size
    TCG_MINI = (44.0, 63.0)  # Mini/small format cards

    # Standard paper sizes
    A4 = (210.0, 297.0)
    LETTER = (215.9, 279.4)
    LEGAL = (215.9, 355.6)

    # Custom - full scanner bed
    FULL_BED = (216.0, 355.6)


@dataclass
class ScannerConfig:
    """
    Configuration for scanner settings optimized for TCG cards.

    The Fujitsu fi-6140z supports:
    - Resolution: 50-600 DPI (optical), up to 1200 DPI interpolated
    - Color depth: 24-bit color, 8-bit grayscale
    - ADF capacity: 50 sheets
    - Scan speed: Up to 60 ppm
    """

    # Resolution settings
    resolution: int = 600  # DPI - 600 is optimal for TCG cards

    # Color mode
    mode: ScanMode = ScanMode.COLOR

    # Paper source
    source: ScanSource = ScanSource.FLATBED

    # Scan area (in mm) - defaults to full scanner bed
    top_left_x: float = 0.0
    top_left_y: float = 0.0
    bottom_right_x: float = 216.0  # ~8.5 inches
    bottom_right_y: float = 355.6  # ~14 inches

    # Image quality settings
    brightness: int = 0  # -100 to 100
    contrast: int = 0  # -100 to 100
    gamma: float = 1.0  # 0.1 to 5.0

    # Advanced settings for fi-6140z
    dropout_color: str = "None"  # None, Red, Green, Blue
    lamp_timeout: int = 15  # minutes

    # Batch scanning
    batch_mode: bool = False
    page_count: int = 0  # 0 = scan until empty

    def for_tcg_cards(self) -> ScannerConfig:
        """Return optimized settings for TCG card scanning."""
        return ScannerConfig(
            resolution=600,
            mode=ScanMode.COLOR,
            source=ScanSource.FLATBED,
            brightness=5,  # Slight boost for card details
            contrast=10,  # Enhanced contrast for text/artwork
            gamma=1.0,
            dropout_color="None",
        )

    def for_batch_scanning(self, count: int = 0) -> ScannerConfig:
        """Return settings for batch scanning through ADF."""
        return ScannerConfig(
            resolution=600,
            mode=ScanMode.COLOR,
            source=ScanSource.ADF_FRONT,
            brightness=5,
            contrast=10,
            gamma=1.0,
            batch_mode=True,
            page_count=count,
        )


@dataclass
class ScanResult:
    """Result of a scan operation."""

    image: Image.Image
    width: int
    height: int
    resolution: int
    mode: str
    source: str
    scan_time: float = 0.0
    page_number: int = 1

    def save(self, path: Path, format: str = "PNG", quality: int = 95) -> None:
        """Save the scanned image to disk."""
        save_kwargs: dict[str, Any] = {}

        if format.upper() == "JPEG":
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        elif format.upper() == "PNG":
            save_kwargs["optimize"] = True
        elif format.upper() == "TIFF":
            save_kwargs["compression"] = "lzw"

        self.image.save(path, format=format, **save_kwargs)
        logger.info(f"Saved scan to {path}")


class FujitsuScanner:
    """
    Interface to the Fujitsu fi-6140z scanner using SANE backend.

    This class provides methods for:
    - Device discovery and initialization
    - Configuring scan parameters
    - Performing single and batch scans
    - Optimized presets for TCG card scanning
    """

    DEVICE_PATTERN = "fujitsu"
    MODEL_NAME = "fi-6140Z"

    def __init__(self, device_name: Optional[str] = None):
        """
        Initialize the scanner interface.

        Args:
            device_name: Specific SANE device name. If None, auto-detect.
        """
        self._device_name = device_name
        self._device: Any = None
        self._sane_initialized = False
        self._config = ScannerConfig()

    def __enter__(self) -> FujitsuScanner:
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def _init_sane(self) -> None:
        """Initialize the SANE library."""
        if self._sane_initialized:
            return

        try:
            import sane
            sane.init()
            self._sane_initialized = True
            logger.info("SANE initialized successfully")
        except ImportError:
            raise RuntimeError(
                "python-sane is not installed. Install with: pip install python-sane\n"
                "Also ensure libsane is installed on your system."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize SANE: {e}")

    def list_devices(self) -> list[tuple[str, str, str, str]]:
        """
        List available SANE scanner devices.

        Returns:
            List of tuples: (device_name, vendor, model, type)
        """
        self._init_sane()
        import sane

        devices = sane.get_devices()
        logger.info(f"Found {len(devices)} scanner(s)")
        return devices

    def find_fujitsu_scanner(self) -> Optional[str]:
        """
        Find the Fujitsu fi-6140z scanner.

        Returns:
            Device name if found, None otherwise.
        """
        devices = self.list_devices()

        for device in devices:
            name, vendor, model, _ = device
            if self.DEVICE_PATTERN.lower() in vendor.lower():
                logger.info(f"Found Fujitsu scanner: {model} ({name})")
                return name
            if self.MODEL_NAME.lower() in model.lower():
                logger.info(f"Found fi-6140Z: {name}")
                return name

        logger.warning("No Fujitsu scanner found")
        return None

    def open(self, device_name: Optional[str] = None) -> None:
        """
        Open connection to the scanner.

        Args:
            device_name: Specific device to open. Uses stored or auto-detect if None.
        """
        self._init_sane()
        import sane

        target_device = device_name or self._device_name

        if target_device is None:
            target_device = self.find_fujitsu_scanner()
            if target_device is None:
                raise RuntimeError(
                    "No Fujitsu scanner found. Please check:\n"
                    "1. Scanner is connected and powered on\n"
                    "2. SANE drivers are installed (libsane-extras, sane-airscan)\n"
                    "3. User has permission to access scanner"
                )

        try:
            self._device = sane.open(target_device)
            self._device_name = target_device
            logger.info(f"Opened scanner: {target_device}")
        except Exception as e:
            raise RuntimeError(f"Failed to open scanner {target_device}: {e}")

    def close(self) -> None:
        """Close the scanner connection."""
        if self._device is not None:
            try:
                self._device.close()
                logger.info("Scanner closed")
            except Exception as e:
                logger.warning(f"Error closing scanner: {e}")
            finally:
                self._device = None

    def get_options(self) -> dict[str, Any]:
        """
        Get available scanner options and their current values.

        Returns:
            Dictionary of option names to their properties.
        """
        if self._device is None:
            raise RuntimeError("Scanner not opened")

        options = {}
        for opt in self._device.get_options():
            if isinstance(opt, tuple) and len(opt) >= 2:
                options[opt[1]] = {
                    "title": opt[2] if len(opt) > 2 else opt[1],
                    "description": opt[3] if len(opt) > 3 else "",
                    "type": opt[4] if len(opt) > 4 else None,
                    "constraint": opt[8] if len(opt) > 8 else None,
                }
        return options

    def configure(self, config: ScannerConfig) -> None:
        """
        Apply scanner configuration.

        Args:
            config: Scanner configuration to apply.
        """
        if self._device is None:
            raise RuntimeError("Scanner not opened")

        self._config = config

        # Apply settings with error handling for unsupported options
        self._safe_set_option("resolution", config.resolution)
        self._safe_set_option("mode", config.mode.value)
        self._safe_set_option("source", config.source.value)

        # Scan area
        self._safe_set_option("tl-x", config.top_left_x)
        self._safe_set_option("tl-y", config.top_left_y)
        self._safe_set_option("br-x", config.bottom_right_x)
        self._safe_set_option("br-y", config.bottom_right_y)

        # Image adjustments
        self._safe_set_option("brightness", config.brightness)
        self._safe_set_option("contrast", config.contrast)

        if config.gamma != 1.0:
            self._safe_set_option("gamma", config.gamma)

        # Fujitsu-specific options
        if config.dropout_color != "None":
            self._safe_set_option("dropout", config.dropout_color)

        logger.info(f"Scanner configured: {config.resolution} DPI, {config.mode.value}")

    def _safe_set_option(self, name: str, value: Any) -> bool:
        """
        Safely set a scanner option, handling unsupported options.

        Args:
            name: Option name.
            value: Value to set.

        Returns:
            True if option was set successfully.
        """
        try:
            setattr(self._device, name.replace("-", "_"), value)
            return True
        except AttributeError:
            logger.debug(f"Option '{name}' not available on this scanner")
            return False
        except Exception as e:
            logger.warning(f"Failed to set option '{name}' to '{value}': {e}")
            return False

    def scan(self, config: Optional[ScannerConfig] = None) -> ScanResult:
        """
        Perform a single scan.

        Args:
            config: Scanner configuration. Uses current config if None.

        Returns:
            ScanResult containing the scanned image.
        """
        import time

        if self._device is None:
            raise RuntimeError("Scanner not opened")

        if config is not None:
            self.configure(config)

        start_time = time.time()

        try:
            logger.info("Starting scan...")
            self._device.start()
            pil_image = self._device.snap()
            scan_time = time.time() - start_time

            result = ScanResult(
                image=pil_image,
                width=pil_image.width,
                height=pil_image.height,
                resolution=self._config.resolution,
                mode=self._config.mode.value,
                source=self._config.source.value,
                scan_time=scan_time,
            )

            logger.info(
                f"Scan complete: {result.width}x{result.height} px, "
                f"{scan_time:.2f}s"
            )
            return result

        except Exception as e:
            raise RuntimeError(f"Scan failed: {e}")

    def scan_batch(
        self,
        config: Optional[ScannerConfig] = None,
        max_pages: int = 0,
    ) -> list[ScanResult]:
        """
        Scan multiple pages from the ADF.

        Args:
            config: Scanner configuration. Uses ADF config if None.
            max_pages: Maximum pages to scan. 0 = until ADF empty.

        Returns:
            List of ScanResult objects.
        """
        if config is None:
            config = ScannerConfig().for_batch_scanning(max_pages)
        else:
            config.source = ScanSource.ADF_FRONT
            config.batch_mode = True

        self.configure(config)

        results = []
        page_num = 0

        while max_pages == 0 or page_num < max_pages:
            try:
                result = self.scan()
                page_num += 1
                result.page_number = page_num
                results.append(result)
                logger.info(f"Scanned page {page_num}")
            except Exception as e:
                if "no document" in str(e).lower() or "empty" in str(e).lower():
                    logger.info("ADF empty, batch scan complete")
                    break
                raise

        logger.info(f"Batch scan complete: {len(results)} pages")
        return results

    def preview(self, resolution: int = 75) -> ScanResult:
        """
        Perform a quick preview scan at low resolution.

        Args:
            resolution: Preview resolution (default 75 DPI).

        Returns:
            ScanResult with preview image.
        """
        preview_config = ScannerConfig(
            resolution=resolution,
            mode=ScanMode.COLOR,
            source=ScanSource.FLATBED,
        )
        return self.scan(preview_config)

    def scan_tcg_card(
        self,
        card_size: PaperSize = PaperSize.TCG_STANDARD,
        position: tuple[float, float] = (0.0, 0.0),
    ) -> ScanResult:
        """
        Scan a single TCG card with optimized settings.

        Args:
            card_size: Size of the card to scan.
            position: Position of the card on the scanner bed (mm).

        Returns:
            ScanResult with the card image.
        """
        width_mm, height_mm = card_size.value
        margin = 5.0  # 5mm margin around card

        config = ScannerConfig(
            resolution=600,
            mode=ScanMode.COLOR,
            source=ScanSource.FLATBED,
            top_left_x=max(0, position[0] - margin),
            top_left_y=max(0, position[1] - margin),
            bottom_right_x=position[0] + width_mm + margin,
            bottom_right_y=position[1] + height_mm + margin,
            brightness=5,
            contrast=10,
        )

        return self.scan(config)


class MockScanner(FujitsuScanner):
    """
    Mock scanner for testing without hardware.

    Generates synthetic test images that simulate scanned TCG cards.
    """

    def __init__(self):
        super().__init__(device_name="mock:fujitsu:fi-6140Z")
        self._is_open = False

    def _init_sane(self) -> None:
        """Mock SANE initialization."""
        self._sane_initialized = True
        logger.info("Mock SANE initialized")

    def list_devices(self) -> list[tuple[str, str, str, str]]:
        """Return mock device list."""
        return [
            ("mock:fujitsu:fi-6140Z", "Fujitsu", "fi-6140Z", "scanner")
        ]

    def find_fujitsu_scanner(self) -> str:
        """Return mock device name."""
        return "mock:fujitsu:fi-6140Z"

    def open(self, device_name: Optional[str] = None) -> None:
        """Mock open."""
        self._is_open = True
        logger.info("Mock scanner opened")

    def close(self) -> None:
        """Mock close."""
        self._is_open = False
        logger.info("Mock scanner closed")

    def configure(self, config: ScannerConfig) -> None:
        """Store configuration."""
        self._config = config
        logger.info(f"Mock scanner configured: {config.resolution} DPI")

    def scan(self, config: Optional[ScannerConfig] = None) -> ScanResult:
        """Generate a mock scan result."""
        import time
        import numpy as np

        if config is not None:
            self._config = config

        # Calculate image size based on config
        width_mm = self._config.bottom_right_x - self._config.top_left_x
        height_mm = self._config.bottom_right_y - self._config.top_left_y

        # Convert mm to pixels at configured DPI
        mm_per_inch = 25.4
        width_px = int(width_mm / mm_per_inch * self._config.resolution)
        height_px = int(height_mm / mm_per_inch * self._config.resolution)

        # Create a test pattern image
        if self._config.mode == ScanMode.COLOR:
            # Create gradient test pattern
            img_array = np.zeros((height_px, width_px, 3), dtype=np.uint8)

            # Background gradient
            for y in range(height_px):
                for x in range(width_px):
                    img_array[y, x] = [
                        min(255, 200 + x % 56),
                        min(255, 200 + y % 56),
                        220,
                    ]

            # Add card-like rectangle in center
            card_width = int(63.5 / mm_per_inch * self._config.resolution)
            card_height = int(88.9 / mm_per_inch * self._config.resolution)

            if card_width < width_px and card_height < height_px:
                cx = (width_px - card_width) // 2
                cy = (height_px - card_height) // 2

                # Card background
                img_array[cy:cy+card_height, cx:cx+card_width] = [240, 240, 250]

                # Card border
                border = 10
                img_array[cy:cy+border, cx:cx+card_width] = [50, 50, 50]
                img_array[cy+card_height-border:cy+card_height, cx:cx+card_width] = [50, 50, 50]
                img_array[cy:cy+card_height, cx:cx+border] = [50, 50, 50]
                img_array[cy:cy+card_height, cx+card_width-border:cx+card_width] = [50, 50, 50]

            pil_image = Image.fromarray(img_array, mode="RGB")
        else:
            # Grayscale
            img_array = np.full((height_px, width_px), 200, dtype=np.uint8)
            pil_image = Image.fromarray(img_array, mode="L")

        return ScanResult(
            image=pil_image,
            width=width_px,
            height=height_px,
            resolution=self._config.resolution,
            mode=self._config.mode.value,
            source=self._config.source.value,
            scan_time=0.5,
        )
