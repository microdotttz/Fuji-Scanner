"""
TWAIN scanner backend for Windows.

TWAIN provides more granular control over scanner settings compared to WIA,
especially for document handling, paper feeding, and advanced features.

Note: Requires the 'pytwain' package: pip install pytwain
      (imports as 'twain' module)
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# TWAIN Constants
# Capability IDs
CAP_XFERCOUNT = 0x0001
CAP_FEEDERENABLED = 0x1002
CAP_FEEDERLOADED = 0x1003
CAP_AUTOFEED = 0x1007
CAP_CLEARPAGE = 0x1008
CAP_FEEDPAGE = 0x1009
CAP_REWINDPAGE = 0x100a
CAP_INDICATORS = 0x100b
CAP_PAPERDETECTABLE = 0x100d
CAP_DUPLEX = 0x1018
CAP_DUPLEXENABLED = 0x1019
CAP_ENABLEDSUIONLY = 0x101a
CAP_CUSTOMDSDATA = 0x101b
CAP_ENDORSER = 0x101c
CAP_ALARMS = 0x1022
CAP_ALARMVOLUME = 0x1023
CAP_AUTOMATICCAPTURE = 0x1024
CAP_TIMEBEFOREFIRSTCAPTURE = 0x1025
CAP_TIMEBETWEENCAPTURES = 0x1026
CAP_MAXBATCHBUFFERS = 0x1027
CAP_FEEDERALIGNMENT = 0x1038
CAP_FEEDERORDER = 0x1039
CAP_REACQUIREALLOWED = 0x103b
CAP_DOUBLEFEEDDETECTION = 0x1043
CAP_DOUBLEFEEDDETECTIONLENGTH = 0x1044
CAP_DOUBLEFEEDDETECTIONSENSITIVITY = 0x1045
CAP_DOUBLEFEEDDETECTIONRESPONSE = 0x1046

# Image Capability IDs
ICAP_XRESOLUTION = 0x1118
ICAP_YRESOLUTION = 0x1119
ICAP_XSCALING = 0x111a
ICAP_YSCALING = 0x111b
ICAP_PIXELTYPE = 0x0101
ICAP_UNITS = 0x0102
ICAP_XFERMECH = 0x0103
ICAP_BRIGHTNESS = 0x1101
ICAP_CONTRAST = 0x1103
ICAP_BITDEPTH = 0x1113
ICAP_PHYSICALWIDTH = 0x1151
ICAP_PHYSICALHEIGHT = 0x1152
ICAP_SUPPORTEDSIZES = 0x1122
ICAP_FRAMES = 0x1012
ICAP_AUTOMATICBORDERDETECTION = 0x1150
ICAP_AUTOMATICDESKEW = 0x1153
ICAP_AUTOMATICROTATE = 0x1154
ICAP_UNDEFINEDIMAGESIZE = 0x1147

# Pixel types
TWPT_BW = 0
TWPT_GRAY = 1
TWPT_RGB = 2
TWPT_PALETTE = 3

# Units
TWUN_INCHES = 0
TWUN_CENTIMETERS = 1
TWUN_PICAS = 2
TWUN_POINTS = 3
TWUN_TWIPS = 4
TWUN_PIXELS = 5
TWUN_MILLIMETERS = 6

# Transfer mechanisms
TWSX_NATIVE = 0
TWSX_FILE = 1
TWSX_MEMORY = 2

# Supported page sizes
TWSS_NONE = 0
TWSS_A4 = 1
TWSS_JISB5 = 2
TWSS_USLETTER = 3
TWSS_USLEGAL = 4
TWSS_A5 = 5
TWSS_ISOB4 = 6
TWSS_ISOB6 = 7
TWSS_USLEDGER = 9
TWSS_USEXECUTIVE = 10
TWSS_A3 = 11
TWSS_ISOB3 = 12
TWSS_A6 = 13
TWSS_C4 = 14
TWSS_C5 = 15
TWSS_C6 = 16
TWSS_4A0 = 17
TWSS_2A0 = 18
TWSS_A0 = 19
TWSS_A1 = 20
TWSS_A2 = 21
TWSS_A7 = 22
TWSS_A8 = 23
TWSS_A9 = 24
TWSS_A10 = 25
TWSS_ISOB0 = 26
TWSS_ISOB1 = 27
TWSS_ISOB2 = 28
TWSS_ISOB5 = 29
TWSS_ISOB7 = 30
TWSS_ISOB8 = 31
TWSS_ISOB9 = 32
TWSS_ISOB10 = 33
TWSS_JISB0 = 34
TWSS_JISB1 = 35
TWSS_JISB2 = 36
TWSS_JISB3 = 37
TWSS_JISB4 = 38
TWSS_JISB6 = 39
TWSS_JISB7 = 40
TWSS_JISB8 = 41
TWSS_JISB9 = 42
TWSS_JISB10 = 43
TWSS_C0 = 44
TWSS_C1 = 45
TWSS_C2 = 46
TWSS_C3 = 47
TWSS_C7 = 48
TWSS_C8 = 49
TWSS_C9 = 50
TWSS_C10 = 51
TWSS_USSTATEMENT = 52
TWSS_BUSINESSCARD = 53  # Business card size - good for TCG cards!
TWSS_MAXSIZE = 54

# Capability names for display
CAPABILITY_NAMES = {
    CAP_XFERCOUNT: "Transfer Count",
    CAP_FEEDERENABLED: "Feeder Enabled",
    CAP_FEEDERLOADED: "Feeder Loaded",
    CAP_AUTOFEED: "Auto Feed",
    CAP_CLEARPAGE: "Clear Page",
    CAP_FEEDPAGE: "Feed Page",
    CAP_REWINDPAGE: "Rewind Page",
    CAP_INDICATORS: "Indicators",
    CAP_PAPERDETECTABLE: "Paper Detectable",
    CAP_DUPLEX: "Duplex",
    CAP_DUPLEXENABLED: "Duplex Enabled",
    CAP_FEEDERALIGNMENT: "Feeder Alignment",
    CAP_FEEDERORDER: "Feeder Order",
    CAP_DOUBLEFEEDDETECTION: "Double Feed Detection",
    CAP_DOUBLEFEEDDETECTIONLENGTH: "Double Feed Detection Length",
    CAP_DOUBLEFEEDDETECTIONSENSITIVITY: "Double Feed Detection Sensitivity",
    CAP_DOUBLEFEEDDETECTIONRESPONSE: "Double Feed Detection Response",
    ICAP_XRESOLUTION: "X Resolution",
    ICAP_YRESOLUTION: "Y Resolution",
    ICAP_PIXELTYPE: "Pixel Type",
    ICAP_UNITS: "Units",
    ICAP_XFERMECH: "Transfer Mechanism",
    ICAP_BRIGHTNESS: "Brightness",
    ICAP_CONTRAST: "Contrast",
    ICAP_BITDEPTH: "Bit Depth",
    ICAP_PHYSICALWIDTH: "Physical Width",
    ICAP_PHYSICALHEIGHT: "Physical Height",
    ICAP_SUPPORTEDSIZES: "Supported Sizes",
    ICAP_AUTOMATICBORDERDETECTION: "Auto Border Detection",
    ICAP_AUTOMATICDESKEW: "Auto Deskew",
    ICAP_AUTOMATICROTATE: "Auto Rotate",
    ICAP_UNDEFINEDIMAGESIZE: "Undefined Image Size",
}


@dataclass
class TWAINScanResult:
    """Result from a TWAIN scan operation."""

    image: Image.Image
    width: int
    height: int
    resolution: int
    mode: str
    source: str
    scan_time: float = 0.0
    page_number: int = 1

    def save(self, path: Path, format: str = "PNG", quality: int = 95) -> None:
        """Save the scanned image."""
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


class TWAINScanner:
    """
    TWAIN scanner interface for Fujitsu fi-6140z.

    TWAIN provides more control over scanner settings compared to WIA,
    particularly for document feeding and paper handling.
    """

    FUJITSU_PATTERN = "fujitsu"
    MODEL_NAME = "fi-6140"
    PAPERSTREAM_PATTERN = "paperstream"

    def __init__(self, source_name: Optional[str] = None):
        """
        Initialize TWAIN scanner.

        Args:
            source_name: Specific TWAIN source name. Auto-detects if None.
        """
        self._source_name = source_name
        self._source_manager = None
        self._source = None
        self._resolution = 600
        self._brightness = 0
        self._contrast = 0
        self._use_feeder = False
        self._auto_feed = True
        self._auto_border_detection = True
        self._page_size = TWSS_BUSINESSCARD  # Default to business card for TCG
        self._config = None

    def __enter__(self) -> "TWAINScanner":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _check_twain_available(self) -> bool:
        """Check if TWAIN module is available."""
        try:
            import twain
            return True
        except ImportError:
            return False

    def _init_twain(self) -> None:
        """Initialize TWAIN Source Manager."""
        if self._source_manager is not None:
            return

        if not self._check_twain_available():
            raise RuntimeError(
                "TWAIN module not installed. Install with: pip install pytwain"
            )

        try:
            import twain
            self._source_manager = twain.SourceManager(0)
            logger.info("TWAIN Source Manager initialized")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize TWAIN: {e}")

    def list_devices(self) -> List[Tuple[str, str, str, str]]:
        """
        List available TWAIN sources.

        Returns:
            List of tuples: (source_name, manufacturer, product, type)
        """
        self._init_twain()

        devices = []
        try:
            source_list = self._source_manager.source_list
            if source_list:
                for source_name in source_list:
                    # Try to extract manufacturer/model from name
                    parts = source_name.split()
                    manufacturer = parts[0] if parts else "Unknown"
                    model = " ".join(parts[1:]) if len(parts) > 1 else source_name
                    devices.append((source_name, manufacturer, model, "scanner"))
        except Exception as e:
            logger.error(f"Error listing TWAIN sources: {e}")

        logger.info(f"Found {len(devices)} TWAIN source(s)")
        return devices

    def find_fujitsu_scanner(self) -> Optional[str]:
        """Find Fujitsu fi-6140z scanner."""
        devices = self.list_devices()

        # First try to find PaperStream (Fujitsu's TWAIN driver)
        for source_name, manufacturer, model, _ in devices:
            if self.PAPERSTREAM_PATTERN.lower() in source_name.lower():
                logger.info(f"Found PaperStream scanner: {source_name}")
                return source_name

        # Then look for Fujitsu/fi-6140 in name
        for source_name, manufacturer, model, _ in devices:
            full_name = f"{manufacturer} {model}".lower()
            if self.FUJITSU_PATTERN.lower() in full_name or self.MODEL_NAME.lower() in full_name:
                logger.info(f"Found Fujitsu scanner: {source_name}")
                return source_name

        logger.warning("No Fujitsu scanner found in TWAIN sources")
        return None

    def open(self, source_name: Optional[str] = None) -> None:
        """
        Open connection to TWAIN source.

        Args:
            source_name: Specific source to open.
        """
        self._init_twain()

        target_source = source_name or self._source_name

        if target_source is None:
            target_source = self.find_fujitsu_scanner()
            if target_source is None:
                # Try to use default/first source
                sources = self.list_devices()
                if sources:
                    target_source = sources[0][0]
                else:
                    raise RuntimeError(
                        "No TWAIN scanner found. Please check:\n"
                        "1. Scanner is connected and powered on\n"
                        "2. TWAIN driver is installed"
                    )

        try:
            self._source = self._source_manager.open_source(target_source)
            self._source_name = target_source
            logger.info(f"Opened TWAIN source: {target_source}")
        except Exception as e:
            raise RuntimeError(f"Failed to open TWAIN source: {e}")

    def close(self) -> None:
        """Close TWAIN source."""
        if self._source:
            try:
                self._source.close()
            except:
                pass
            self._source = None

        if self._source_manager:
            try:
                self._source_manager.close()
            except:
                pass
            self._source_manager = None

        logger.info("TWAIN scanner closed")

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get all available capabilities from the scanner.

        Returns:
            Dictionary of capability names to their values/ranges.
        """
        if self._source is None:
            raise RuntimeError("Scanner not opened")

        capabilities = {}

        # List of capabilities to try
        cap_ids = [
            (CAP_XFERCOUNT, "Transfer Count"),
            (CAP_FEEDERENABLED, "Feeder Enabled"),
            (CAP_FEEDERLOADED, "Feeder Loaded"),
            (CAP_AUTOFEED, "Auto Feed"),
            (CAP_CLEARPAGE, "Clear Page"),
            (CAP_FEEDPAGE, "Feed Page"),
            (CAP_PAPERDETECTABLE, "Paper Detectable"),
            (CAP_DUPLEX, "Duplex"),
            (CAP_DUPLEXENABLED, "Duplex Enabled"),
            (ICAP_XRESOLUTION, "X Resolution"),
            (ICAP_YRESOLUTION, "Y Resolution"),
            (ICAP_PIXELTYPE, "Pixel Type"),
            (ICAP_BRIGHTNESS, "Brightness"),
            (ICAP_CONTRAST, "Contrast"),
            (ICAP_SUPPORTEDSIZES, "Supported Sizes"),
            (ICAP_AUTOMATICBORDERDETECTION, "Auto Border Detection"),
            (ICAP_AUTOMATICDESKEW, "Auto Deskew"),
        ]

        for cap_id, cap_name in cap_ids:
            try:
                value = self._source.get_capability(cap_id)
                capabilities[cap_name] = {
                    "id": cap_id,
                    "value": value,
                }
            except Exception as e:
                capabilities[cap_name] = {
                    "id": cap_id,
                    "error": str(e),
                }

        return capabilities

    def configure(self, config) -> None:
        """
        Configure scanner settings.

        Args:
            config: ScannerConfig object.
        """
        from fuji_tcg_scanner.scanner import ScannerConfig, ScanSource

        if isinstance(config, ScannerConfig):
            self._resolution = min(600, max(50, config.resolution))
            self._brightness = max(-127, min(127, config.brightness))
            self._contrast = max(-127, min(127, config.contrast))
            self._use_feeder = config.source in (ScanSource.ADF_FRONT, ScanSource.ADF_BACK, ScanSource.ADF_DUPLEX)
            self._config = config
        else:
            self._resolution = min(600, max(50, config))

        logger.info(f"Configured: {self._resolution} DPI, Feeder: {self._use_feeder}")

    def _apply_settings(self) -> None:
        """Apply configured settings to TWAIN source."""
        if self._source is None:
            return

        # Import TWAIN type constants
        from twain.lowlevel import constants as twc

        try:
            # Set resolution (uses FIX32 type for decimal values)
            logger.info(f"Setting resolution to {self._resolution} DPI...")
            self._source.SetCapability(ICAP_XRESOLUTION, twc.TWTY_FIX32, float(self._resolution))
            self._source.SetCapability(ICAP_YRESOLUTION, twc.TWTY_FIX32, float(self._resolution))

            # Set color mode (RGB = 2, uses UINT16)
            logger.info("Setting color mode to RGB...")
            self._source.SetCapability(ICAP_PIXELTYPE, twc.TWTY_UINT16, TWPT_RGB)

            # Set feeder mode (uses BOOL type)
            if self._use_feeder:
                logger.info("Enabling feeder...")
                try:
                    self._source.SetCapability(CAP_FEEDERENABLED, twc.TWTY_BOOL, 1)
                    self._source.SetCapability(CAP_AUTOFEED, twc.TWTY_BOOL, 1 if self._auto_feed else 0)
                except Exception as e:
                    logger.warning(f"Could not enable feeder mode: {e}")
            else:
                try:
                    self._source.SetCapability(CAP_FEEDERENABLED, twc.TWTY_BOOL, 0)
                except:
                    pass

            # Set brightness/contrast (FIX32 type)
            if self._brightness != 0:
                try:
                    self._source.SetCapability(ICAP_BRIGHTNESS, twc.TWTY_FIX32, float(self._brightness))
                except:
                    pass

            if self._contrast != 0:
                try:
                    self._source.SetCapability(ICAP_CONTRAST, twc.TWTY_FIX32, float(self._contrast))
                except:
                    pass

            # Enable auto border detection for better card scanning (BOOL type)
            if self._auto_border_detection:
                try:
                    logger.info("Enabling auto border detection...")
                    self._source.SetCapability(ICAP_AUTOMATICBORDERDETECTION, twc.TWTY_BOOL, 1)
                except Exception as e:
                    logger.warning(f"Could not enable auto border detection: {e}")

            # Set page size (UINT16 type)
            try:
                logger.info(f"Setting page size to {self._page_size} (Business Card = 53)...")
                self._source.SetCapability(ICAP_SUPPORTEDSIZES, twc.TWTY_UINT16, self._page_size)
            except Exception as e:
                logger.warning(f"Could not set page size: {e}")

        except Exception as e:
            logger.warning(f"Error applying some settings: {e}")

    def scan(self):
        """
        Perform a single scan.

        Returns:
            ScanResult object.
        """
        from fuji_tcg_scanner.scanner import ScanResult

        if self._source is None:
            raise RuntimeError("Scanner not opened")

        start_time = time.time()
        temp_path = None

        try:
            logger.info("Starting TWAIN scan...")

            # Apply settings
            self._apply_settings()

            # Request image acquisition (no UI)
            logger.info("Requesting image acquisition...")
            self._source.request_acquire(show_ui=False, modal_ui=False)

            # Perform transfer to file
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"twain_scan_{int(time.time() * 1000)}.bmp")

            logger.info(f"Transferring image to {temp_path}...")

            # Try native transfer first
            try:
                # Use xfer_image_natively if available
                if hasattr(self._source, 'xfer_image_natively'):
                    rv = self._source.xfer_image_natively()
                    if rv:
                        handle, count = rv
                        # Convert DIB handle to file
                        self._save_dib_to_file(handle, temp_path)
                elif hasattr(self._source, 'xfer_image_by_file'):
                    # File transfer mode
                    self._source.xfer_image_by_file(temp_path)
                else:
                    # Try generic acquire
                    pil_image = self._source.acquire()
                    if pil_image:
                        pil_image.save(temp_path, 'BMP')
            except Exception as e:
                logger.warning(f"Transfer method failed: {e}, trying alternative...")
                # Alternative: use acquire method
                try:
                    images = list(self._source.acquire())
                    if images:
                        images[0].save(temp_path, 'BMP')
                except Exception as e2:
                    raise RuntimeError(f"All transfer methods failed: {e}, {e2}")

            # Load the image
            if os.path.exists(temp_path):
                pil_image = Image.open(temp_path)
                pil_image = pil_image.copy()

                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")
            else:
                raise RuntimeError("No image file created")

            scan_time = time.time() - start_time

            result = ScanResult(
                image=pil_image,
                width=pil_image.width,
                height=pil_image.height,
                resolution=self._resolution,
                mode="Color",
                source="Flatbed" if not self._use_feeder else "ADF",
                scan_time=scan_time,
            )

            logger.info(f"Scan complete: {result.width}x{result.height}, {scan_time:.2f}s")
            return result

        except Exception as e:
            raise RuntimeError(f"TWAIN scan failed: {e}")

        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    def _save_dib_to_file(self, handle: int, filepath: str) -> None:
        """Save a DIB handle to a BMP file."""
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        GlobalLock = kernel32.GlobalLock
        GlobalLock.argtypes = [wintypes.HGLOBAL]
        GlobalLock.restype = ctypes.c_void_p

        GlobalUnlock = kernel32.GlobalUnlock
        GlobalUnlock.argtypes = [wintypes.HGLOBAL]

        GlobalSize = kernel32.GlobalSize
        GlobalSize.argtypes = [wintypes.HGLOBAL]
        GlobalSize.restype = ctypes.c_size_t

        GlobalFree = kernel32.GlobalFree
        GlobalFree.argtypes = [wintypes.HGLOBAL]

        ptr = GlobalLock(handle)
        if not ptr:
            raise RuntimeError("Failed to lock DIB handle")

        try:
            size = GlobalSize(handle)
            data = ctypes.string_at(ptr, size)

            # Write DIB to BMP file (add BMP header)
            with open(filepath, 'wb') as f:
                # BMP file header (14 bytes)
                file_size = len(data) + 14
                bmp_header = b'BM'
                bmp_header += file_size.to_bytes(4, 'little')
                bmp_header += b'\x00\x00\x00\x00'  # Reserved
                bmp_header += b'\x36\x00\x00\x00'  # Offset to pixel data (54 bytes typical)
                f.write(bmp_header)
                f.write(data)

        finally:
            GlobalUnlock(handle)
            GlobalFree(handle)

    def scan_batch(self, max_pages: int = 0) -> List[TWAINScanResult]:
        """Scan multiple pages from ADF."""
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

        return results

    def preview(self, resolution: int = 75):
        """Quick preview scan at low resolution."""
        original_res = self._resolution
        self._resolution = resolution

        try:
            return self.scan()
        finally:
            self._resolution = original_res

    def show_settings_dialog(self) -> bool:
        """
        Show the scanner's native settings dialog.

        Returns:
            True if user confirmed settings, False if cancelled.
        """
        if self._source is None:
            raise RuntimeError("Scanner not opened")

        try:
            # Show the data source's settings UI
            self._source.request_acquire(show_ui=True, modal_ui=True)
            return True
        except Exception as e:
            logger.error(f"Settings dialog error: {e}")
            return False

    def set_manual_feed(self, enabled: bool = True) -> bool:
        """
        Enable/disable manual feed mode.

        When enabled, the scanner waits for manual paper insertion.
        This can help with small cards like TCG cards.

        Returns:
            True if successful.
        """
        if self._source is None:
            return False

        from twain.lowlevel import constants as twc

        self._auto_feed = not enabled

        try:
            # Disable auto feed = manual mode
            self._source.SetCapability(CAP_AUTOFEED, twc.TWTY_BOOL, 0 if enabled else 1)
            logger.info(f"Manual feed {'enabled' if enabled else 'disabled'}")
            return True
        except Exception as e:
            logger.warning(f"Could not set manual feed mode: {e}")
            return False

    def set_auto_border_detection(self, enabled: bool = True) -> bool:
        """
        Enable/disable automatic border detection.

        When enabled, scanner automatically detects card edges.

        Returns:
            True if successful.
        """
        if self._source is None:
            return False

        from twain.lowlevel import constants as twc

        self._auto_border_detection = enabled

        try:
            self._source.SetCapability(ICAP_AUTOMATICBORDERDETECTION, twc.TWTY_BOOL, 1 if enabled else 0)
            logger.info(f"Auto border detection {'enabled' if enabled else 'disabled'}")
            return True
        except Exception as e:
            logger.warning(f"Could not set auto border detection: {e}")
            return False

    def set_page_size(self, size: int = TWSS_BUSINESSCARD) -> bool:
        """
        Set the page size for scanning.

        Args:
            size: TWAIN page size constant. Use TWSS_BUSINESSCARD (53) for TCG cards.

        Returns:
            True if successful.
        """
        if self._source is None:
            return False

        from twain.lowlevel import constants as twc

        self._page_size = size

        try:
            self._source.SetCapability(ICAP_SUPPORTEDSIZES, twc.TWTY_UINT16, size)
            logger.info(f"Page size set to {size}")
            return True
        except Exception as e:
            logger.warning(f"Could not set page size: {e}")
            return False

    def configure_for_tcg_cards(self) -> bool:
        """
        Configure scanner with optimal settings for TCG cards.

        Sets:
        - Page size: Business card (closest to TCG card)
        - Auto border detection: Enabled
        - Resolution: 600 DPI
        - Color mode: RGB

        Returns:
            True if all settings applied successfully.
        """
        from twain.lowlevel import constants as twc

        success = True

        self._resolution = 600
        self._page_size = TWSS_BUSINESSCARD
        self._auto_border_detection = True

        if self._source:
            try:
                self._source.SetCapability(ICAP_SUPPORTEDSIZES, twc.TWTY_UINT16, TWSS_BUSINESSCARD)
            except Exception as e:
                logger.warning(f"Could not set business card size: {e}")
                success = False

            try:
                self._source.SetCapability(ICAP_AUTOMATICBORDERDETECTION, twc.TWTY_BOOL, 1)
            except Exception as e:
                logger.warning(f"Could not enable auto border detection: {e}")
                success = False

            try:
                self._source.SetCapability(ICAP_XRESOLUTION, twc.TWTY_FIX32, 600.0)
                self._source.SetCapability(ICAP_YRESOLUTION, twc.TWTY_FIX32, 600.0)
            except Exception as e:
                logger.warning(f"Could not set resolution: {e}")
                success = False

            try:
                self._source.SetCapability(ICAP_PIXELTYPE, twc.TWTY_UINT16, TWPT_RGB)
            except Exception as e:
                logger.warning(f"Could not set color mode: {e}")
                success = False

        logger.info(f"TCG card configuration applied (success={success})")
        return success

    def feed_page(self) -> bool:
        """
        Manually feed a page from the ADF.

        Returns:
            True if successful.
        """
        if self._source is None:
            return False

        from twain.lowlevel import constants as twc

        try:
            self._source.SetCapability(CAP_FEEDPAGE, twc.TWTY_BOOL, 1)
            logger.info("Page feed triggered")
            return True
        except Exception as e:
            logger.warning(f"Could not feed page: {e}")
            return False

    def clear_page(self) -> bool:
        """
        Clear/eject the current page from the ADF.

        Returns:
            True if successful.
        """
        if self._source is None:
            return False

        from twain.lowlevel import constants as twc

        try:
            self._source.SetCapability(CAP_CLEARPAGE, twc.TWTY_BOOL, 1)
            logger.info("Page cleared/ejected")
            return True
        except Exception as e:
            logger.warning(f"Could not clear page: {e}")
            return False


def run_twain_diagnostic():
    """Run TWAIN diagnostic to enumerate capabilities."""
    print("=" * 70)
    print("TWAIN Scanner Diagnostic")
    print("=" * 70)
    print()

    try:
        scanner = TWAINScanner()
        scanner._init_twain()
    except Exception as e:
        print(f"ERROR: Could not initialize TWAIN: {e}")
        print()
        print("TWAIN troubleshooting:")
        print("1. Install TWAIN module: pip install pytwain")
        print("2. Ensure scanner TWAIN driver is installed")
        return

    # List sources
    print("Scanning for TWAIN sources...")
    devices = scanner.list_devices()

    print(f"\nFound {len(devices)} TWAIN source(s):")
    for name, manufacturer, model, _ in devices:
        print(f"  - {name}")

    if not devices:
        print("No TWAIN sources found!")
        return

    # Try to open scanner
    print("\n" + "-" * 70)
    print("Connecting to scanner...")

    try:
        scanner.open()
        print(f"Connected to: {scanner._source_name}")
    except Exception as e:
        print(f"ERROR: Could not open scanner: {e}")
        return

    # Get capabilities
    print("\n" + "-" * 70)
    print("SCANNER CAPABILITIES")
    print("-" * 70)

    caps = scanner.get_capabilities()
    for name, info in sorted(caps.items()):
        cap_id = info.get('id', 0)
        if 'error' in info:
            print(f"  [{cap_id:#06x}] {name}: NOT SUPPORTED")
        else:
            value = info['value']
            print(f"  [{cap_id:#06x}] {name}: {value}")

    # Test TCG card configuration
    print("\n" + "-" * 70)
    print("TESTING TCG CARD CONFIGURATION")
    print("-" * 70)

    print("Applying TCG card settings...")
    success = scanner.configure_for_tcg_cards()
    print(f"  Result: {'SUCCESS' if success else 'PARTIAL/FAILED'}")

    scanner.close()
    print("\n" + "=" * 70)
    print("TWAIN diagnostic complete!")
    print("=" * 70)


def check_twain_available() -> bool:
    """Check if TWAIN is available."""
    try:
        import twain
        return True
    except ImportError:
        return False


def create_twain_scanner() -> Optional[TWAINScanner]:
    """
    Create a TWAIN scanner instance if available.

    Returns:
        TWAINScanner instance or None if TWAIN not available.
    """
    if not check_twain_available():
        return None
    return TWAINScanner()


if __name__ == "__main__":
    run_twain_diagnostic()
