#!/usr/bin/env python
"""
MTG Bulk Card Scanner

A dedicated bulk scanning application for MTG cards using the Fujitsu fi-6140z
scanner with TWAIN for full hardware control.

Features:
- Continuous ADF scanning until hopper is empty
- Auto-save each card as individual image
- Sequential filenames
- Multifeed detection disabled (for rigid cards)
"""

import sys
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading

# Add src to path
src_path = os.path.join(os.path.dirname(__file__), 'src')
if os.path.exists(src_path):
    sys.path.insert(0, src_path)

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QSlider, QGroupBox,
    QFileDialog, QLineEdit, QProgressBar, QMessageBox, QFrame,
    QSizePolicy, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPalette, QColor

from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TWAIN constants
CAP_XFERCOUNT = 0x0001
CAP_FEEDERENABLED = 0x1002
CAP_FEEDERLOADED = 0x1003
CAP_AUTOFEED = 0x1007
CAP_DUPLEXENABLED = 0x1019
CAP_DOUBLEFEEDDETECTION = 0x1043
CAP_DOUBLEFEEDDETECTIONSENSITIVITY = 0x1045

ICAP_XRESOLUTION = 0x1118
ICAP_YRESOLUTION = 0x1119
ICAP_PIXELTYPE = 0x0101
ICAP_BITDEPTH = 0x1113

# Pixel types
TWPT_BW = 0
TWPT_GRAY = 1
TWPT_RGB = 2


# Dark theme stylesheet
DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', sans-serif;
}
QGroupBox {
    border: 2px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #45475a;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    color: #cdd6f4;
    font-weight: bold;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #585b70;
}
QPushButton:pressed {
    background-color: #313244;
}
QPushButton:disabled {
    background-color: #313244;
    color: #6c7086;
}
QPushButton#startButton {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-size: 16pt;
    padding: 15px 40px;
}
QPushButton#startButton:hover {
    background-color: #b4f0a8;
}
QPushButton#startButton:disabled {
    background-color: #585b70;
    color: #6c7086;
}
QPushButton#stopButton {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-size: 14pt;
    padding: 12px 30px;
}
QPushButton#stopButton:hover {
    background-color: #f5a0b8;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #313244;
    border: 2px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    color: #cdd6f4;
    min-height: 20px;
}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    width: 25px;
}
QComboBox::down-arrow {
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 7px solid #89b4fa;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QSlider::groove:horizontal {
    background: #313244;
    height: 8px;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    width: 18px;
    height: 18px;
    margin: -5px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background: #b4befe;
}
QProgressBar {
    border: none;
    border-radius: 6px;
    background-color: #313244;
    height: 25px;
    text-align: center;
    color: #cdd6f4;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 6px;
}
QLabel#countLabel {
    font-size: 48pt;
    font-weight: bold;
    color: #a6e3a1;
}
QLabel#statusLabel {
    font-size: 12pt;
    color: #a6adc8;
}
QFrame#previewFrame {
    background-color: #313244;
    border: 2px solid #45475a;
    border-radius: 8px;
}
"""


class ScanWorker(QThread):
    """Worker thread for continuous ADF scanning."""

    card_scanned = pyqtSignal(int, str)  # card_number, filepath
    scan_error = pyqtSignal(str)
    status_update = pyqtSignal(str)
    preview_ready = pyqtSignal(object)  # PIL Image
    finished_batch = pyqtSignal(int)  # total cards scanned

    def __init__(
        self,
        output_dir: Path,
        dpi: int = 600,
        color_mode: str = "color",
        output_format: str = "png",
        jpeg_quality: int = 95,
        filename_prefix: str = "scan",
        start_number: int = 1,
    ):
        super().__init__()
        self.output_dir = output_dir
        self.dpi = dpi
        self.color_mode = color_mode
        self.output_format = output_format
        self.jpeg_quality = jpeg_quality
        self.filename_prefix = filename_prefix
        self.start_number = start_number

        self._stop_requested = False
        self._scanner = None
        self._source = None
        self._sm = None

    def stop(self):
        """Request the worker to stop scanning."""
        self._stop_requested = True

    def run(self):
        """Main scanning loop."""
        import twain
        import twain.exceptions
        from twain.lowlevel import constants as twc

        card_count = 0
        current_number = self.start_number

        try:
            self.status_update.emit("Initializing TWAIN...")

            # Initialize TWAIN
            self._sm = twain.SourceManager(0)

            # Find Fujitsu/PaperStream scanner
            sources = self._sm.source_list
            target_source = None

            for src in sources:
                if 'paperstream' in src.lower() or 'fujitsu' in src.lower() or 'fi-6140' in src.lower():
                    target_source = src
                    break

            if not target_source and sources:
                target_source = sources[0]

            if not target_source:
                self.scan_error.emit("No scanner found!")
                return

            self.status_update.emit(f"Connecting to {target_source}...")
            self._source = self._sm.open_source(target_source)

            # Configure scanner
            self.status_update.emit("Configuring scanner...")
            self._configure_scanner(twc)

            self.status_update.emit("Ready - Insert cards into ADF")

            # Start acquisition session (no UI)
            self.status_update.emit("Starting scan session...")
            self._source.RequestAcquire(0, 0)

            # Continuous scanning loop - keep transferring until no more images
            while not self._stop_requested:
                try:
                    self.status_update.emit(f"Scanning card {current_number}...")

                    # Transfer image
                    rv = self._source.XferImageNatively()

                    if rv:
                        handle, more_pending = rv

                        # Convert to PIL Image
                        image = self._dib_to_pil(handle)

                        if image:
                            # Save image
                            filename = f"{self.filename_prefix}_{current_number:03d}.{self.output_format}"
                            filepath = self.output_dir / filename

                            save_kwargs = {}
                            if self.output_format.lower() in ('jpg', 'jpeg'):
                                save_kwargs['quality'] = self.jpeg_quality
                                save_kwargs['optimize'] = True
                            elif self.output_format.lower() == 'png':
                                save_kwargs['optimize'] = True

                            image.save(str(filepath), **save_kwargs)

                            card_count += 1
                            self.card_scanned.emit(card_count, str(filepath))
                            self.preview_ready.emit(image)

                            current_number += 1

                            self.status_update.emit(f"Saved: {filename}")

                        # Check if more images are pending
                        # more_pending: 0 = no more, 1 = more images available
                        if more_pending == 0:
                            self.status_update.emit("No more pages pending, checking feeder...")
                            # Small delay then check if feeder has more
                            time.sleep(0.3)

                            # Try to get another image - if feeder empty, this will raise
                            try:
                                self._source.RequestAcquire(0, 0)
                            except Exception as e:
                                err = str(e).lower()
                                if any(x in err for x in ['no document', 'empty', 'no paper', 'cancel']):
                                    self.status_update.emit("ADF empty - batch complete!")
                                    break
                                raise
                    else:
                        # No image returned
                        self.status_update.emit("ADF empty - batch complete!")
                        break

                except twain.exceptions.CancelAll:
                    self.status_update.emit("ADF empty - batch complete!")
                    break
                except Exception as e:
                    error_str = str(e).lower()

                    # Check for "no paper" or "feeder empty" conditions
                    if any(x in error_str for x in ['no document', 'empty', 'no paper', 'feeder', 'cancel']):
                        self.status_update.emit("ADF empty - batch complete!")
                        break
                    else:
                        logger.warning(f"Scan error: {e}")
                        # Don't break on other errors, might be recoverable
                        time.sleep(0.5)

                        # Try to re-acquire
                        try:
                            self._source.RequestAcquire(0, 0)
                        except:
                            break

            self.finished_batch.emit(card_count)

        except Exception as e:
            logger.exception("Scanner error")
            self.scan_error.emit(str(e))

        finally:
            self._cleanup()

    def _configure_scanner(self, twc):
        """Configure scanner for MTG card scanning."""
        if not self._source:
            return

        try:
            # Set resolution
            self._source.SetCapability(ICAP_XRESOLUTION, twc.TWTY_FIX32, float(self.dpi))
            self._source.SetCapability(ICAP_YRESOLUTION, twc.TWTY_FIX32, float(self.dpi))
            logger.info(f"Resolution set to {self.dpi} DPI")
        except Exception as e:
            logger.warning(f"Could not set resolution: {e}")

        try:
            # Set color mode
            pixel_type = TWPT_RGB if self.color_mode == "color" else TWPT_GRAY
            self._source.SetCapability(ICAP_PIXELTYPE, twc.TWTY_UINT16, pixel_type)
            logger.info(f"Color mode set to {self.color_mode}")
        except Exception as e:
            logger.warning(f"Could not set color mode: {e}")

        try:
            # Enable feeder (ADF)
            self._source.SetCapability(CAP_FEEDERENABLED, twc.TWTY_BOOL, 1)
            logger.info("Feeder enabled")
        except Exception as e:
            logger.warning(f"Could not enable feeder: {e}")

        try:
            # Enable auto-feed for continuous scanning
            self._source.SetCapability(CAP_AUTOFEED, twc.TWTY_BOOL, 1)
            logger.info("Auto-feed enabled")
        except Exception as e:
            logger.warning(f"Could not enable auto-feed: {e}")

        # NOTE: Duplex and multifeed detection must be configured through
        # the native PaperStream settings dialog - not available via TWAIN API
        logger.info("Note: Duplex/multifeed settings must be configured in scanner dialog")

        try:
            # Set transfer count to -1 (scan all available)
            self._source.SetCapability(CAP_XFERCOUNT, twc.TWTY_INT16, -1)
            logger.info("Transfer count set to unlimited")
        except Exception as e:
            logger.debug(f"Could not set transfer count: {e}")

    def _dib_to_pil(self, handle: int) -> Optional[Image.Image]:
        """Convert Windows DIB handle to PIL Image."""
        import ctypes
        from ctypes import wintypes
        import tempfile

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
            return None

        try:
            size = GlobalSize(handle)
            data = ctypes.string_at(ptr, size)

            # Write DIB to temp BMP file
            temp_path = os.path.join(tempfile.gettempdir(), f"mtg_scan_{int(time.time()*1000)}.bmp")

            with open(temp_path, 'wb') as f:
                # BMP file header (14 bytes)
                file_size = len(data) + 14
                f.write(b'BM')
                f.write(file_size.to_bytes(4, 'little'))
                f.write(b'\x00\x00\x00\x00')
                f.write(b'\x36\x00\x00\x00')
                f.write(data)

            # Load with PIL
            image = Image.open(temp_path)
            image = image.copy()  # Copy so we can delete temp file

            if image.mode != "RGB" and self.color_mode == "color":
                image = image.convert("RGB")

            # Clean up temp file
            try:
                os.remove(temp_path)
            except:
                pass

            return image

        finally:
            GlobalUnlock(handle)
            GlobalFree(handle)

    def _cleanup(self):
        """Clean up TWAIN resources."""
        try:
            if self._source:
                self._source.close()
                self._source = None
        except:
            pass

        try:
            if self._sm:
                self._sm.close()
                self._sm = None
        except:
            pass


class PreviewWidget(QLabel):
    """Widget to display last scanned card preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(200, 280)
        self.setMaximumSize(300, 420)
        self.setStyleSheet("""
            background-color: #313244;
            border: 2px solid #45475a;
            border-radius: 8px;
            color: #6c7086;
        """)
        self.setText("No preview")
        self._current_pixmap = None

    def set_image(self, image: Image.Image):
        """Display a PIL Image."""
        try:
            # Convert PIL to QPixmap via buffer
            import io
            buffer = io.BytesIO()

            # Resize for preview
            preview_size = (280, 390)  # Roughly card proportions
            image.thumbnail(preview_size, Image.Resampling.LANCZOS)

            image.save(buffer, format="PNG")
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())

            if not pixmap.isNull():
                self._current_pixmap = pixmap
                self.setPixmap(pixmap)
        except Exception as e:
            logger.error(f"Preview error: {e}")


class MTGBulkScanner(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTG Bulk Card Scanner")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        self.setStyleSheet(DARK_STYLE)

        self.worker: Optional[ScanWorker] = None
        self.total_scanned = 0

        self._setup_ui()
        self._check_twain()

    def _setup_ui(self):
        """Set up the user interface."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left panel - Controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(16)

        # Title
        title = QLabel("MTG Bulk Scanner")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet("color: #89b4fa;")
        left_layout.addWidget(title)

        subtitle = QLabel("Fujitsu fi-6140z • TWAIN • ADF Batch Mode")
        subtitle.setStyleSheet("color: #6c7086; font-size: 10pt;")
        left_layout.addWidget(subtitle)

        left_layout.addSpacing(10)

        # Output settings
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout(output_group)

        # Output folder
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Folder:"))
        self.folder_edit = QLineEdit(str(Path.home() / "MTG_Scans"))
        folder_layout.addWidget(self.folder_edit)
        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(40)
        self.browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.browse_btn)
        output_layout.addLayout(folder_layout)

        # Filename prefix
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Prefix:"))
        self.prefix_edit = QLineEdit("scan")
        prefix_layout.addWidget(self.prefix_edit)
        prefix_layout.addWidget(QLabel("Start #:"))
        self.start_num_spin = QSpinBox()
        self.start_num_spin.setRange(1, 9999)
        self.start_num_spin.setValue(1)
        prefix_layout.addWidget(self.start_num_spin)
        output_layout.addLayout(prefix_layout)

        # Format
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPG"])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        format_layout.addWidget(self.format_combo)

        format_layout.addWidget(QLabel("Quality:"))
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(50, 100)
        self.quality_slider.setValue(95)
        self.quality_slider.setEnabled(False)
        format_layout.addWidget(self.quality_slider)
        self.quality_label = QLabel("95%")
        self.quality_label.setFixedWidth(40)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"{v}%"))
        format_layout.addWidget(self.quality_label)
        output_layout.addLayout(format_layout)

        left_layout.addWidget(output_group)

        # Scanner settings
        scanner_group = QGroupBox("Scanner Settings")
        scanner_layout = QVBoxLayout(scanner_group)

        # DPI
        dpi_layout = QHBoxLayout()
        dpi_layout.addWidget(QLabel("Resolution:"))
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["300 DPI", "400 DPI", "600 DPI"])
        self.dpi_combo.setCurrentText("600 DPI")
        dpi_layout.addWidget(self.dpi_combo)
        scanner_layout.addLayout(dpi_layout)

        # Color mode
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color Mode:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["Color", "Grayscale"])
        color_layout.addWidget(self.color_combo)
        scanner_layout.addLayout(color_layout)

        # Scanner settings button - IMPORTANT for duplex/multifeed
        self.scanner_settings_btn = QPushButton("Open Scanner Settings...")
        self.scanner_settings_btn.setToolTip(
            "IMPORTANT: Open PaperStream settings to:\n"
            "• Disable Duplex (set to Simplex/Front)\n"
            "• Disable Multifeed Detection\n"
            "• Adjust feeding settings"
        )
        self.scanner_settings_btn.clicked.connect(self._open_scanner_settings)
        scanner_layout.addWidget(self.scanner_settings_btn)

        # Info label
        info_label = QLabel(
            "IMPORTANT: Click 'Open Scanner Settings' above to:\n"
            "• Set scanning to SIMPLEX (front only)\n"
            "• Disable multifeed detection for rigid cards"
        )
        info_label.setStyleSheet("color: #f9e2af; font-size: 9pt; padding: 5px;")
        scanner_layout.addWidget(info_label)

        left_layout.addWidget(scanner_group)

        # Control buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("START SCANNING")
        self.start_btn.setObjectName("startButton")
        self.start_btn.clicked.connect(self._start_scanning)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_scanning)
        btn_layout.addWidget(self.stop_btn)

        left_layout.addLayout(btn_layout)

        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.status_label)

        left_layout.addStretch()

        main_layout.addWidget(left_panel, 1)

        # Right panel - Counter and preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(20)

        # Counter
        counter_group = QGroupBox("Cards Scanned")
        counter_layout = QVBoxLayout(counter_group)
        counter_layout.setAlignment(Qt.AlignCenter)

        self.count_label = QLabel("0")
        self.count_label.setObjectName("countLabel")
        self.count_label.setAlignment(Qt.AlignCenter)
        counter_layout.addWidget(self.count_label)

        self.session_label = QLabel("This session: 0")
        self.session_label.setStyleSheet("color: #a6adc8;")
        self.session_label.setAlignment(Qt.AlignCenter)
        counter_layout.addWidget(self.session_label)

        right_layout.addWidget(counter_group)

        # Preview
        preview_group = QGroupBox("Last Scanned Card")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setAlignment(Qt.AlignCenter)

        self.preview = PreviewWidget()
        preview_layout.addWidget(self.preview)

        self.last_file_label = QLabel("")
        self.last_file_label.setStyleSheet("color: #a6adc8; font-size: 9pt;")
        self.last_file_label.setAlignment(Qt.AlignCenter)
        self.last_file_label.setWordWrap(True)
        preview_layout.addWidget(self.last_file_label)

        right_layout.addWidget(preview_group, 1)

        main_layout.addWidget(right_panel, 1)

    def _check_twain(self):
        """Check if TWAIN is available."""
        try:
            import twain
            sm = twain.SourceManager(0)
            sources = sm.source_list
            sm.close()

            if sources:
                self.status_label.setText(f"Ready • Found {len(sources)} scanner(s)")
            else:
                self.status_label.setText("Warning: No scanners found")
                self.start_btn.setEnabled(False)
        except ImportError:
            self.status_label.setText("Error: TWAIN not installed (pip install pytwain)")
            self.start_btn.setEnabled(False)
        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    def _browse_folder(self):
        """Browse for output folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder",
            self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    def _open_scanner_settings(self):
        """Open the native scanner settings dialog."""
        self.scanner_settings_btn.setEnabled(False)
        self.scanner_settings_btn.setText("Opening...")
        self.status_label.setText("Opening scanner settings...")

        def open_dialog():
            try:
                import twain

                sm = twain.SourceManager(0)

                # Find PaperStream source
                sources = sm.source_list
                target = None
                for src in sources:
                    if 'paperstream' in src.lower() or 'fujitsu' in src.lower():
                        target = src
                        break
                if not target and sources:
                    target = sources[0]

                if target:
                    source = sm.open_source(target)
                    try:
                        # Show native UI with modal dialog
                        source.RequestAcquire(1, 1)  # ShowUI=True, Modal=True
                    except:
                        pass  # User closed dialog
                    source.close()

                sm.close()

            except Exception as e:
                logger.error(f"Settings error: {e}")

            # Re-enable button in main thread
            QTimer.singleShot(0, self._on_settings_closed)

        thread = threading.Thread(target=open_dialog, daemon=True)
        thread.start()

    def _on_settings_closed(self):
        """Called when scanner settings dialog closes."""
        self.scanner_settings_btn.setEnabled(True)
        self.scanner_settings_btn.setText("Open Scanner Settings...")
        self.status_label.setText("Settings closed - ready to scan")

    def _on_format_changed(self, format_text: str):
        """Handle format change."""
        is_jpg = format_text.upper() == "JPG"
        self.quality_slider.setEnabled(is_jpg)

    def _start_scanning(self):
        """Start the scanning process."""
        # Validate output folder
        output_dir = Path(self.folder_edit.text())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot create output folder: {e}")
            return

        # Get settings
        dpi = int(self.dpi_combo.currentText().split()[0])
        color_mode = "color" if self.color_combo.currentText() == "Color" else "grayscale"
        output_format = self.format_combo.currentText().lower()
        jpeg_quality = self.quality_slider.value()
        prefix = self.prefix_edit.text() or "scan"
        start_num = self.start_num_spin.value()

        # Reset session counter
        self.total_scanned = 0
        self.count_label.setText("0")
        self.session_label.setText("This session: 0")

        # Create and start worker
        self.worker = ScanWorker(
            output_dir=output_dir,
            dpi=dpi,
            color_mode=color_mode,
            output_format=output_format,
            jpeg_quality=jpeg_quality,
            filename_prefix=prefix,
            start_number=start_num,
        )

        self.worker.card_scanned.connect(self._on_card_scanned)
        self.worker.scan_error.connect(self._on_scan_error)
        self.worker.status_update.connect(self._on_status_update)
        self.worker.preview_ready.connect(self._on_preview_ready)
        self.worker.finished_batch.connect(self._on_batch_finished)
        self.worker.finished.connect(self._on_worker_finished)

        # Update UI
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_settings_enabled(False)

        self.worker.start()

    def _stop_scanning(self):
        """Stop the scanning process."""
        if self.worker:
            self.status_label.setText("Stopping...")
            self.worker.stop()

    def _on_card_scanned(self, count: int, filepath: str):
        """Handle card scanned event."""
        self.total_scanned = count
        self.count_label.setText(str(count))
        self.session_label.setText(f"This session: {count}")
        self.last_file_label.setText(Path(filepath).name)

        # Update start number for next batch
        self.start_num_spin.setValue(self.start_num_spin.value() + 1)

    def _on_scan_error(self, error: str):
        """Handle scan error."""
        QMessageBox.warning(self, "Scan Error", error)

    def _on_status_update(self, status: str):
        """Handle status update."""
        self.status_label.setText(status)

    def _on_preview_ready(self, image: Image.Image):
        """Handle preview image ready."""
        self.preview.set_image(image)

    def _on_batch_finished(self, total: int):
        """Handle batch completion."""
        self.status_label.setText(f"Batch complete! Scanned {total} cards.")

    def _on_worker_finished(self):
        """Handle worker thread finished."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_settings_enabled(True)
        self.worker = None

    def _set_settings_enabled(self, enabled: bool):
        """Enable/disable settings controls."""
        self.folder_edit.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)
        self.prefix_edit.setEnabled(enabled)
        self.start_num_spin.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.quality_slider.setEnabled(enabled and self.format_combo.currentText().upper() == "JPG")
        self.dpi_combo.setEnabled(enabled)
        self.color_combo.setEnabled(enabled)

    def closeEvent(self, event):
        """Handle window close."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        event.accept()


def main():
    """Launch the application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MTGBulkScanner()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
