"""
Windows WIA (Windows Image Acquisition) scanner backend.

This module provides scanner access on Windows using the WIA COM interface.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, List, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# WIA Constants
WIA_DEVICE_TYPE_SCANNER = 1
WIA_INTENT_IMAGE_TYPE_COLOR = 1
WIA_INTENT_IMAGE_TYPE_GRAYSCALE = 2
WIA_INTENT_IMAGE_TYPE_TEXT = 4

# WIA Property IDs
WIA_IPA_DATATYPE = 4103
WIA_IPA_DEPTH = 4104
WIA_IPS_CUR_INTENT = 6146
WIA_IPS_XRES = 6147
WIA_IPS_YRES = 6148
WIA_IPS_XPOS = 6149
WIA_IPS_YPOS = 6150
WIA_IPS_XEXTENT = 6151
WIA_IPS_YEXTENT = 6152
WIA_IPS_BRIGHTNESS = 6154
WIA_IPS_CONTRAST = 6155
WIA_IPS_DOCUMENT_HANDLING_SELECT = 3088
WIA_IPS_PAGES = 3096

# Document handling flags
FEEDER = 1
FLATBED = 2
DUPLEX = 4
FRONT_FIRST = 8
BACK_FIRST = 16
FRONT_ONLY = 32
BACK_ONLY = 64
NEXT_PAGE = 128
PREFEED = 256
AUTO_ADVANCE = 512

# Feeder control property
WIA_IPS_FEEDER_CONTROL = 6159

# Data types
WIA_DATA_COLOR = 3
WIA_DATA_GRAYSCALE = 2
WIA_DATA_THRESHOLD = 0


@dataclass
class WIAScanResult:
    """Result from a WIA scan operation."""

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


class WIAScanner:
    """
    Windows WIA scanner interface for Fujitsu fi-6140z.

    Uses Windows Image Acquisition (WIA) COM interface for scanner access.
    """

    FUJITSU_PATTERN = "fujitsu"
    MODEL_NAME = "fi-6140"

    def __init__(self, device_id: Optional[str] = None):
        """
        Initialize the WIA scanner interface.

        Args:
            device_id: Specific WIA device ID. If None, auto-detect Fujitsu scanner.
        """
        self._device_id = device_id
        self._device: Any = None
        self._wia_manager: Any = None
        self._resolution = 600
        self._brightness = 0
        self._contrast = 0
        self._use_feeder = False
        self._config: Any = None

    def __enter__(self) -> "WIAScanner":
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def _init_wia(self) -> None:
        """Initialize WIA COM interface."""
        if self._wia_manager is not None:
            return

        try:
            import win32com.client
            self._wia_manager = win32com.client.Dispatch("WIA.DeviceManager")
            logger.info("WIA initialized successfully")
        except ImportError:
            raise RuntimeError(
                "pywin32 is not installed. Install with: pip install pywin32"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize WIA: {e}")

    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        """
        List available WIA scanner devices.

        Returns:
            List of tuples: (device_id, manufacturer, name, type)
        """
        self._init_wia()

        devices = []
        for i in range(1, self._wia_manager.DeviceInfos.Count + 1):
            device_info = self._wia_manager.DeviceInfos.Item(i)
            if device_info.Type == WIA_DEVICE_TYPE_SCANNER:
                devices.append((
                    device_info.DeviceID,
                    device_info.Properties("Manufacturer").Value,
                    device_info.Properties("Name").Value,
                    "scanner",
                ))

        logger.info(f"Found {len(devices)} scanner(s)")
        return devices

    def find_fujitsu_scanner(self) -> Optional[str]:
        """
        Find the Fujitsu fi-6140z scanner.

        Returns:
            Device ID if found, None otherwise.
        """
        devices = self.list_devices()

        for device_id, manufacturer, name, _ in devices:
            if self.FUJITSU_PATTERN.lower() in manufacturer.lower():
                logger.info(f"Found Fujitsu scanner: {name} ({device_id})")
                return device_id
            if self.MODEL_NAME.lower() in name.lower():
                logger.info(f"Found fi-6140: {device_id}")
                return device_id

        logger.warning("No Fujitsu scanner found")
        return None

    def open(self, device_id: Optional[str] = None) -> None:
        """
        Open connection to the scanner.

        Args:
            device_id: Specific device to open. Uses stored or auto-detect if None.
        """
        self._init_wia()

        target_device = device_id or self._device_id

        if target_device is None:
            target_device = self.find_fujitsu_scanner()
            if target_device is None:
                raise RuntimeError(
                    "No Fujitsu scanner found. Please check:\n"
                    "1. Scanner is connected and powered on\n"
                    "2. Scanner drivers are installed\n"
                    "3. Scanner appears in Windows Devices and Printers"
                )

        try:
            # Find the device info
            for i in range(1, self._wia_manager.DeviceInfos.Count + 1):
                device_info = self._wia_manager.DeviceInfos.Item(i)
                if device_info.DeviceID == target_device:
                    self._device = device_info.Connect()
                    self._device_id = target_device
                    logger.info(f"Opened scanner: {target_device}")
                    return

            raise RuntimeError(f"Device not found: {target_device}")

        except Exception as e:
            raise RuntimeError(f"Failed to open scanner: {e}")

    def close(self) -> None:
        """Close the scanner connection."""
        self._device = None
        logger.info("Scanner closed")

    def configure(self, config) -> None:
        """
        Configure scanner settings.

        Args:
            config: ScannerConfig object with scan settings.
        """
        # Import here to avoid circular imports
        from fuji_tcg_scanner.scanner import ScannerConfig, ScanSource

        # Handle both ScannerConfig objects and legacy parameters
        if isinstance(config, ScannerConfig):
            self._resolution = min(600, max(50, config.resolution))
            self._brightness = max(-100, min(100, config.brightness))
            self._contrast = max(-100, min(100, config.contrast))
            self._use_feeder = config.source in (ScanSource.ADF_FRONT, ScanSource.ADF_BACK, ScanSource.ADF_DUPLEX)
            self._config = config
            color_mode = config.mode.value
        else:
            # Legacy: config is actually resolution int
            self._resolution = min(600, max(50, config))
            self._brightness = 0
            self._contrast = 0
            self._use_feeder = False
            color_mode = "Color"

        logger.info(f"Scanner configured: {self._resolution} DPI, {color_mode}")

    def _apply_settings(self, item: Any) -> None:
        """Apply scan settings to WIA item."""
        props = item.Properties

        # Set resolution
        self._set_property(props, WIA_IPS_XRES, self._resolution)
        self._set_property(props, WIA_IPS_YRES, self._resolution)

        # Set color mode
        self._set_property(props, WIA_IPA_DATATYPE, WIA_DATA_COLOR)
        self._set_property(props, WIA_IPA_DEPTH, 24)  # 24-bit color

        # Set brightness/contrast
        if self._brightness != 0:
            self._set_property(props, WIA_IPS_BRIGHTNESS, self._brightness)
        if self._contrast != 0:
            self._set_property(props, WIA_IPS_CONTRAST, self._contrast)

    def _set_property(self, props: Any, prop_id: int, value: Any) -> bool:
        """Safely set a WIA property."""
        try:
            for i in range(1, props.Count + 1):
                prop = props.Item(i)
                if prop.PropertyID == prop_id:
                    prop.Value = value
                    return True
        except Exception as e:
            logger.debug(f"Could not set property {prop_id}: {e}")
        return False

    def scan(self):
        """
        Perform a single scan.

        Returns:
            ScanResult containing the scanned image.
        """
        # Import here to avoid circular imports
        from fuji_tcg_scanner.scanner import ScanResult
        import tempfile
        import os

        if self._device is None:
            raise RuntimeError("Scanner not opened")

        start_time = time.time()
        temp_path = None

        try:
            logger.info("Starting scan...")

            # Get the first item (scanner)
            item = self._device.Items(1)

            # Apply settings
            self._apply_settings(item)

            # Perform scan using WIA CommonDialog for more reliable transfer
            # Use temporary file approach for reliability
            wia_format_bmp = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"

            image_file = item.Transfer(wia_format_bmp)

            # Create a unique temp file path (don't create the file yet for WIA)
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"tcg_scan_{int(time.time() * 1000)}.bmp")

            # Make sure file doesn't exist (WIA won't overwrite)
            if os.path.exists(temp_path):
                os.remove(temp_path)

            # Use WIA's SaveFile method if available, otherwise use binary data
            try:
                # Try to save directly using WIA
                image_file.SaveFile(temp_path)
                logger.info(f"Saved scan to temp file: {temp_path}")
            except (AttributeError, Exception) as save_error:
                logger.warning(f"SaveFile failed: {save_error}, trying binary transfer")
                # Fallback: write binary data to file
                image_data = image_file.FileData.BinaryData
                # Convert from array to bytes if needed
                if hasattr(image_data, 'tobytes'):
                    image_data = image_data.tobytes()
                elif not isinstance(image_data, bytes):
                    image_data = bytes(image_data)

                with open(temp_path, 'wb') as f:
                    f.write(image_data)
                logger.info(f"Wrote {len(image_data)} bytes to temp file")

            # Load the image from temp file
            pil_image = Image.open(temp_path)
            # Make a copy so we can delete the temp file
            pil_image = pil_image.copy()

            # Convert to RGB if necessary
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            scan_time = time.time() - start_time

            # Return standard ScanResult for compatibility
            result = ScanResult(
                image=pil_image,
                width=pil_image.width,
                height=pil_image.height,
                resolution=self._resolution,
                mode="Color",
                source="Flatbed" if not self._use_feeder else "ADF",
                scan_time=scan_time,
            )

            logger.info(
                f"Scan complete: {result.width}x{result.height} px, "
                f"{scan_time:.2f}s"
            )
            return result

        except Exception as e:
            raise RuntimeError(f"Scan failed: {e}")

        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    def scan_batch(self, max_pages: int = 0) -> List[WIAScanResult]:
        """
        Scan multiple pages from the ADF.

        Args:
            max_pages: Maximum pages to scan. 0 = until ADF empty.

        Returns:
            List of WIAScanResult objects.
        """
        self._use_feeder = True
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
                error_str = str(e).lower()
                if "no document" in error_str or "empty" in error_str or "paper" in error_str:
                    logger.info("ADF empty, batch scan complete")
                    break
                raise

        logger.info(f"Batch scan complete: {len(results)} pages")
        return results

    def preview(self, resolution: int = 75) -> WIAScanResult:
        """
        Perform a quick preview scan at low resolution.

        Args:
            resolution: Preview resolution (default 75 DPI).

        Returns:
            WIAScanResult with preview image.
        """
        original_res = self._resolution
        self._resolution = resolution

        try:
            return self.scan()
        finally:
            self._resolution = original_res

    def set_feeder_control(self, mode: str = "auto") -> bool:
        """
        Set feeder control mode for document handling.

        Args:
            mode: One of:
                - "auto": Auto-advance (default scanner behavior)
                - "next_page": Wait for next page
                - "prefeed": Pre-feed next document

        Returns:
            True if successfully set.
        """
        if self._device is None:
            logger.warning("Scanner not open")
            return False

        mode_values = {
            "auto": AUTO_ADVANCE,
            "next_page": NEXT_PAGE,
            "prefeed": PREFEED,
        }

        if mode not in mode_values:
            logger.warning(f"Unknown feeder mode: {mode}")
            return False

        try:
            item = self._device.Items(1)
            props = item.Properties
            value = mode_values[mode]

            for i in range(1, props.Count + 1):
                prop = props.Item(i)
                if prop.PropertyID == WIA_IPS_FEEDER_CONTROL:
                    prop.Value = value
                    logger.info(f"Feeder control set to: {mode} ({value})")
                    return True

            logger.warning("Feeder control property not found")
            return False
        except Exception as e:
            logger.error(f"Failed to set feeder control: {e}")
            return False

    def set_document_handling(self, front_only: bool = True, use_duplex: bool = False) -> bool:
        """
        Set document handling mode.

        Args:
            front_only: Only scan front side (recommended for cards).
            use_duplex: Scan both sides.

        Returns:
            True if successfully set.
        """
        if self._device is None:
            return False

        try:
            props = self._device.Properties

            value = FEEDER
            if front_only:
                value |= FRONT_ONLY
            if use_duplex:
                value |= DUPLEX

            for i in range(1, props.Count + 1):
                prop = props.Item(i)
                if prop.PropertyID == WIA_IPS_DOCUMENT_HANDLING_SELECT:
                    if not prop.IsReadOnly:
                        prop.Value = value
                        logger.info(f"Document handling set to: {value}")
                        return True

            logger.warning("Document handling property is read-only or not found")
            return False
        except Exception as e:
            logger.error(f"Failed to set document handling: {e}")
            return False

    def set_scan_area_for_card(self, card_width_mm: float = 63.5, card_height_mm: float = 88.9) -> bool:
        """
        Set scan area to match TCG card dimensions.

        Standard TCG card: 63.5mm x 88.9mm (2.5" x 3.5")

        Args:
            card_width_mm: Card width in millimeters.
            card_height_mm: Card height in millimeters.

        Returns:
            True if successfully set.
        """
        if self._device is None:
            return False

        try:
            item = self._device.Items(1)
            props = item.Properties

            # Convert mm to pixels at current resolution
            # 1 inch = 25.4 mm
            pixels_per_mm = self._resolution / 25.4
            width_pixels = int(card_width_mm * pixels_per_mm)
            height_pixels = int(card_height_mm * pixels_per_mm)

            # Set extent (scan area size)
            self._set_property(props, WIA_IPS_XEXTENT, width_pixels)
            self._set_property(props, WIA_IPS_YEXTENT, height_pixels)

            # Set start position to 0,0
            self._set_property(props, WIA_IPS_XPOS, 0)
            self._set_property(props, WIA_IPS_YPOS, 0)

            logger.info(f"Scan area set to {width_pixels}x{height_pixels} pixels ({card_width_mm}x{card_height_mm} mm)")
            return True
        except Exception as e:
            logger.error(f"Failed to set scan area: {e}")
            return False

    def get_feeder_status(self) -> dict:
        """
        Get current feeder/document handling status.

        Returns:
            Dictionary with feeder settings and status.
        """
        status = {}

        if self._device is None:
            return {"error": "Scanner not open"}

        try:
            # Device-level properties
            props = self._device.Properties
            for i in range(1, props.Count + 1):
                prop = props.Item(i)
                if prop.PropertyID == 3076:  # Document handling capabilities
                    status["capabilities"] = prop.Value
                elif prop.PropertyID == 3088:  # Document handling select
                    status["document_handling"] = prop.Value

            # Item-level properties
            item = self._device.Items(1)
            props = item.Properties
            for i in range(1, props.Count + 1):
                prop = props.Item(i)
                if prop.PropertyID == WIA_IPS_FEEDER_CONTROL:
                    status["feeder_control"] = prop.Value
                elif prop.PropertyID == WIA_IPS_XEXTENT:
                    status["width_pixels"] = prop.Value
                elif prop.PropertyID == WIA_IPS_YEXTENT:
                    status["height_pixels"] = prop.Value
                elif prop.PropertyID == WIA_IPS_XRES:
                    status["resolution"] = prop.Value

        except Exception as e:
            status["error"] = str(e)

        return status


def get_scanner():
    """
    Get the appropriate scanner class for the current platform.

    Returns:
        WIAScanner on Windows, FujitsuScanner on Linux.
    """
    import sys

    if sys.platform == "win32":
        return WIAScanner
    else:
        from fuji_tcg_scanner.scanner import FujitsuScanner
        return FujitsuScanner
