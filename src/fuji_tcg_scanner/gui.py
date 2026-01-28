"""
Modern GUI for Fuji TCG Scanner application.

A polished PyQt6 interface for scanning and processing TCG cards.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import threading

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QCheckBox, QGroupBox,
    QScrollArea, QFrame, QProgressBar, QStatusBar, QFileDialog,
    QMessageBox, QSplitter, QGridLayout, QSlider, QTabWidget,
    QLineEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QImage, QFont, QPalette, QColor, QIcon

from PIL import Image
from PIL.ImageQt import ImageQt

from fuji_tcg_scanner import __version__
from fuji_tcg_scanner.scanner import ScannerConfig, ScanResult, create_scanner, MockScanner
from fuji_tcg_scanner.image_processor import ImageProcessor, ProcessingConfig, ColorProfile, OutputFormat
from fuji_tcg_scanner.card_detector import CardDetector, DetectionConfig
from fuji_tcg_scanner.config import load_config

# Check if TWAIN is available
try:
    from fuji_tcg_scanner.scanner_twain import TWAINScanner, check_twain_available
    TWAIN_AVAILABLE = check_twain_available()
except ImportError:
    TWAIN_AVAILABLE = False

logger = logging.getLogger(__name__)


# Modern dark theme stylesheet
DARK_THEME = """
QMainWindow {
    background-color: #1a1a2e;
}
QWidget {
    background-color: #1a1a2e;
    color: #eaeaea;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
}
QGroupBox {
    border: 2px solid #3d3d5c;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #00d4ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
}
QPushButton {
    background-color: #3d3d5c;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    color: #eaeaea;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4d4d6c;
}
QPushButton:pressed {
    background-color: #2d2d4c;
}
QPushButton:disabled {
    background-color: #2a2a3e;
    color: #666;
}
QPushButton#scanButton {
    background-color: #00d4ff;
    color: #1a1a2e;
    font-size: 14pt;
    padding: 15px 40px;
}
QPushButton#scanButton:hover {
    background-color: #00e5ff;
}
QPushButton#scanButton:pressed {
    background-color: #00b8d4;
}
QPushButton#scanButton:disabled {
    background-color: #3d5c5c;
    color: #888;
}
QComboBox {
    background-color: #2d2d4c;
    border: 2px solid #3d3d5c;
    border-radius: 6px;
    padding: 8px 12px;
    min-width: 120px;
}
QComboBox:hover {
    border-color: #00d4ff;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 8px solid #00d4ff;
    margin-right: 10px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d4c;
    border: 2px solid #3d3d5c;
    selection-background-color: #00d4ff;
    selection-color: #1a1a2e;
}
QSpinBox, QLineEdit {
    background-color: #2d2d4c;
    border: 2px solid #3d3d5c;
    border-radius: 6px;
    padding: 8px;
}
QSpinBox:hover, QLineEdit:hover {
    border-color: #00d4ff;
}
QSpinBox:focus, QLineEdit:focus {
    border-color: #00d4ff;
}
QSlider::groove:horizontal {
    border: none;
    height: 8px;
    background: #2d2d4c;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #00d4ff;
    border: none;
    width: 18px;
    height: 18px;
    margin: -5px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background: #00e5ff;
}
QProgressBar {
    border: none;
    border-radius: 6px;
    background-color: #2d2d4c;
    height: 20px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #00d4ff;
    border-radius: 6px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background: #2d2d4c;
    width: 12px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #3d3d5c;
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #4d4d6c;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QStatusBar {
    background-color: #16162a;
    border-top: 1px solid #3d3d5c;
}
QTabWidget::pane {
    border: 2px solid #3d3d5c;
    border-radius: 8px;
    background-color: #1a1a2e;
}
QTabBar::tab {
    background-color: #2d2d4c;
    border: none;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #00d4ff;
    color: #1a1a2e;
}
QTabBar::tab:hover:!selected {
    background-color: #3d3d5c;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 2px solid #3d3d5c;
    background-color: #2d2d4c;
}
QCheckBox::indicator:checked {
    background-color: #00d4ff;
    border-color: #00d4ff;
}
QCheckBox::indicator:hover {
    border-color: #00d4ff;
}
QLabel#previewLabel {
    background-color: #16162a;
    border: 2px dashed #3d3d5c;
    border-radius: 12px;
}
QLabel#titleLabel {
    font-size: 24pt;
    font-weight: bold;
    color: #00d4ff;
}
QLabel#subtitleLabel {
    font-size: 10pt;
    color: #888;
}
QFrame#cardFrame {
    background-color: #2d2d4c;
    border: 2px solid #3d3d5c;
    border-radius: 8px;
}
QFrame#cardFrame:hover {
    border-color: #00d4ff;
}
"""


class ScanWorker(QThread):
    """Background worker thread for scanning operations."""

    finished = pyqtSignal(object)  # ScanResult or Exception
    progress = pyqtSignal(str)  # Progress message
    image_ready = pyqtSignal(object)  # PIL Image for preview

    def __init__(
        self,
        scanner_config: ScannerConfig,
        processing_config: ProcessingConfig,
        detection_config: DetectionConfig,
        auto_crop: bool = True,
        mock_mode: bool = False,
        backend: str = "wia",  # "wia" or "twain"
    ):
        super().__init__()
        self.scanner_config = scanner_config
        self.processing_config = processing_config
        self.detection_config = detection_config
        self.auto_crop = auto_crop
        self.mock_mode = mock_mode
        self.backend = backend

    def run(self):
        try:
            self.progress.emit(f"Connecting to scanner ({self.backend.upper()})...")

            if self.mock_mode:
                scanner = create_scanner(mock=True)
            elif self.backend == "twain" and TWAIN_AVAILABLE:
                from fuji_tcg_scanner.scanner_twain import TWAINScanner
                scanner = TWAINScanner()
            else:
                scanner = create_scanner(mock=False)

            with scanner:
                self.progress.emit("Configuring scanner...")
                scanner.configure(self.scanner_config)

                # Apply TCG-specific settings for TWAIN
                if self.backend == "twain" and TWAIN_AVAILABLE and hasattr(scanner, 'configure_for_tcg_cards'):
                    self.progress.emit("Applying TCG card settings...")
                    scanner.configure_for_tcg_cards()

                self.progress.emit("Scanning...")
                result = scanner.scan()

                # Emit raw scan for preview
                self.image_ready.emit(result.image)

                self.progress.emit("Processing image...")

                # Card detection
                if self.auto_crop:
                    detector = CardDetector(self.detection_config)
                    cards = detector.detect(result.image)
                    if cards:
                        self.progress.emit(f"Found {len(cards)} card(s)")
                        card_image = detector.extract(result.image, cards[0])
                    else:
                        self.progress.emit("No cards detected, using full image")
                        card_image = result.image
                else:
                    card_image = result.image

                # Image processing
                processor = ImageProcessor(self.processing_config)
                processed = processor.process(card_image)

                # Create result with processed image
                final_result = ScanResult(
                    image=processed,
                    width=processed.width,
                    height=processed.height,
                    resolution=result.resolution,
                    mode=result.mode,
                    source=result.source,
                    scan_time=result.scan_time,
                )

                self.progress.emit("Complete!")
                self.finished.emit(final_result)

        except Exception as e:
            logger.exception("Scan failed")
            self.finished.emit(e)


class ImageCard(QFrame):
    """A clickable card widget displaying a scanned image."""

    clicked = pyqtSignal(object)  # Path to image

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setObjectName("cardFrame")
        self.setFixedSize(160, 220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(144, 180)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet("background-color: #1a1a2e; border-radius: 4px;")

        # Load and display thumbnail
        self._load_thumbnail()

        layout.addWidget(self.thumbnail_label)

        # Filename label
        name_label = QLabel(image_path.stem[:18] + "..." if len(image_path.stem) > 18 else image_path.stem)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("font-size: 8pt; color: #aaa;")
        layout.addWidget(name_label)

    def _load_thumbnail(self):
        try:
            pixmap = QPixmap(str(self.image_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    144, 180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.thumbnail_label.setPixmap(scaled)
        except Exception as e:
            logger.error(f"Failed to load thumbnail: {e}")

    def mousePressEvent(self, event):
        self.clicked.emit(self.image_path)


class PreviewWidget(QLabel):
    """Large preview widget for scanned images."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewLabel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 500)
        self._current_pixmap = None
        self._show_placeholder()

    def _show_placeholder(self):
        self.setText("Place card on scanner\nand click Scan")
        self.setStyleSheet("""
            QLabel {
                background-color: #16162a;
                border: 2px dashed #3d3d5c;
                border-radius: 12px;
                color: #666;
                font-size: 14pt;
            }
        """)

    def set_image(self, image: Image.Image):
        """Display a PIL Image."""
        try:
            self._current_pixmap = self._pil_to_pixmap(image)
            self._update_display()
        except Exception as e:
            logger.error(f"Failed to display image: {e}")
            self._show_placeholder()

    def set_pixmap_from_path(self, path: Path):
        """Display image from file path."""
        try:
            self._current_pixmap = QPixmap(str(path))
            self._update_display()
        except Exception as e:
            logger.error(f"Failed to load image from path: {e}")

    def _pil_to_pixmap(self, image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap."""
        try:
            # Ensure RGB mode
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Use a temporary file for more reliable conversion
            import io
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            return pixmap
        except Exception as e:
            logger.error(f"PIL to QPixmap conversion failed: {e}")
            return QPixmap()

    def _update_display(self):
        if self._current_pixmap and not self._current_pixmap.isNull():
            scaled = self._current_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled)
            self.setStyleSheet("""
                QLabel {
                    background-color: #16162a;
                    border: 2px solid #3d3d5c;
                    border-radius: 12px;
                }
            """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap:
            self._update_display()

    def clear_image(self):
        self._current_pixmap = None
        self._show_placeholder()


class GalleryWidget(QScrollArea):
    """Scrollable gallery of scanned cards."""

    image_selected = pyqtSignal(object)  # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.layout = QGridLayout(self.container)
        self.layout.setSpacing(12)
        self.layout.setContentsMargins(12, 12, 12, 12)

        self.setWidget(self.container)
        self.cards: List[ImageCard] = []
        self._columns = 3

    def add_image(self, image_path: Path):
        """Add a new image to the gallery."""
        card = ImageCard(image_path)
        card.clicked.connect(self.image_selected.emit)

        row = len(self.cards) // self._columns
        col = len(self.cards) % self._columns

        self.layout.addWidget(card, row, col)
        self.cards.append(card)

    def load_directory(self, directory: Path):
        """Load all images from a directory."""
        self.clear()

        if not directory.exists():
            return

        for ext in ["*.png", "*.jpg", "*.jpeg", "*.tiff"]:
            for path in sorted(directory.glob(ext)):
                if "thumb" not in path.stem.lower():
                    self.add_image(path)

    def clear(self):
        """Remove all images from gallery."""
        for card in self.cards:
            self.layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()


class SettingsPanel(QWidget):
    """Settings panel with scan configuration options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Scanner Settings Group
        scanner_group = QGroupBox("Scanner Settings")
        scanner_layout = QVBoxLayout(scanner_group)

        # Backend selector
        backend_layout = QHBoxLayout()
        backend_layout.addWidget(QLabel("Backend:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("WIA (Windows)", "wia")
        if TWAIN_AVAILABLE:
            self.backend_combo.addItem("TWAIN (Advanced)", "twain")
        self.backend_combo.setToolTip(
            "WIA: Standard Windows scanner interface\n"
            "TWAIN: Advanced interface with more control (if available)"
        )
        backend_layout.addWidget(self.backend_combo)
        scanner_layout.addLayout(backend_layout)

        # Resolution
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Resolution:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["300 DPI", "400 DPI", "600 DPI"])
        self.resolution_combo.setCurrentText("600 DPI")
        res_layout.addWidget(self.resolution_combo)
        scanner_layout.addLayout(res_layout)

        # Preset
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Standard",
            "Pokemon",
            "MTG",
            "Yu-Gi-Oh!",
            "Archival",
            "Grading"
        ])
        preset_layout.addWidget(self.preset_combo)
        scanner_layout.addLayout(preset_layout)

        layout.addWidget(scanner_group)

        # Processing Settings Group
        process_group = QGroupBox("Image Processing")
        process_layout = QVBoxLayout(process_group)

        # Auto-crop checkbox
        self.auto_crop_check = QCheckBox("Auto-detect & crop card")
        self.auto_crop_check.setChecked(True)
        process_layout.addWidget(self.auto_crop_check)

        # Auto-rotate checkbox
        self.auto_rotate_check = QCheckBox("Auto-rotate if needed")
        self.auto_rotate_check.setChecked(True)
        process_layout.addWidget(self.auto_rotate_check)

        # Enhance colors checkbox
        self.enhance_check = QCheckBox("Enhance colors")
        self.enhance_check.setChecked(True)
        process_layout.addWidget(self.enhance_check)

        # Denoise checkbox
        self.denoise_check = QCheckBox("Reduce noise")
        self.denoise_check.setChecked(True)
        process_layout.addWidget(self.denoise_check)

        # Sharpen checkbox
        self.sharpen_check = QCheckBox("Sharpen details")
        self.sharpen_check.setChecked(True)
        process_layout.addWidget(self.sharpen_check)

        layout.addWidget(process_group)

        # Output Settings Group
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout(output_group)

        # Format
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPEG", "TIFF"])
        format_layout.addWidget(self.format_combo)
        output_layout.addLayout(format_layout)

        # Output directory
        dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit("./scanned_cards")
        self.output_dir_edit.setPlaceholderText("Output directory")
        dir_layout.addWidget(self.output_dir_edit)

        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(40)
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)
        output_layout.addLayout(dir_layout)

        layout.addWidget(output_group)

        # Advanced scanner settings button (for TWAIN)
        self.scanner_settings_btn = QPushButton("Open Scanner Settings...")
        self.scanner_settings_btn.setToolTip("Open native scanner settings dialog (TWAIN only)")
        self.scanner_settings_btn.clicked.connect(self._open_scanner_settings)
        self.scanner_settings_btn.setEnabled(TWAIN_AVAILABLE)
        layout.addWidget(self.scanner_settings_btn)

        # Update button state when backend changes
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)

        # Mock mode (for testing)
        self.mock_check = QCheckBox("Test mode (no scanner)")
        self.mock_check.setStyleSheet("color: #888; font-size: 9pt;")
        layout.addWidget(self.mock_check)

        # TWAIN status label
        if TWAIN_AVAILABLE:
            twain_label = QLabel("TWAIN: Available")
            twain_label.setStyleSheet("color: #00ff88; font-size: 9pt;")
        else:
            twain_label = QLabel("TWAIN: Not available (pip install pytwain)")
            twain_label.setStyleSheet("color: #ff8800; font-size: 9pt;")
        layout.addWidget(twain_label)

        layout.addStretch()

    def _browse_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.output_dir_edit.text()
        )
        if directory:
            self.output_dir_edit.setText(directory)

    def _on_backend_changed(self, index):
        """Handle backend selection change."""
        backend = self.backend_combo.currentData()
        # Enable scanner settings button only for TWAIN
        self.scanner_settings_btn.setEnabled(backend == "twain" and TWAIN_AVAILABLE)

    def _open_scanner_settings(self):
        """Open the native scanner settings dialog."""
        if not TWAIN_AVAILABLE:
            QMessageBox.warning(
                self, "TWAIN Not Available",
                "TWAIN is not available. Install with: pip install pytwain"
            )
            return

        # Disable the button while dialog is open
        self.scanner_settings_btn.setEnabled(False)
        self.scanner_settings_btn.setText("Opening...")

        # Run in a thread to avoid blocking Qt
        import threading

        def open_dialog():
            try:
                from fuji_tcg_scanner.scanner_twain import TWAINScanner
                import twain

                scanner = TWAINScanner()
                scanner.open()

                try:
                    # RequestAcquire with ShowUI=True, Modal=True
                    scanner._source.RequestAcquire(1, 1)
                except twain.exceptions.CancelAll:
                    pass  # User cancelled
                except Exception:
                    pass  # Dialog closed

                scanner.close()

            except Exception as e:
                logger.error(f"Scanner settings error: {e}")

            # Re-enable button (needs to be done in main thread)
            QTimer.singleShot(0, self._on_settings_dialog_closed)

        thread = threading.Thread(target=open_dialog, daemon=True)
        thread.start()

    def _on_settings_dialog_closed(self):
        """Called when scanner settings dialog closes."""
        self.scanner_settings_btn.setEnabled(True)
        self.scanner_settings_btn.setText("Open Scanner Settings...")

    def get_backend(self) -> str:
        """Get the selected scanner backend."""
        return self.backend_combo.currentData() or "wia"

    def get_resolution(self) -> int:
        text = self.resolution_combo.currentText()
        return int(text.split()[0])

    def get_output_format(self) -> OutputFormat:
        text = self.format_combo.currentText()
        return OutputFormat(text.lower())

    def get_output_directory(self) -> Path:
        return Path(self.output_dir_edit.text())

    def get_color_profile(self) -> ColorProfile:
        preset = self.preset_combo.currentText()
        profiles = {
            "Standard": ColorProfile.STANDARD,
            "Pokemon": ColorProfile.POKEMON,
            "MTG": ColorProfile.MTG,
            "Yu-Gi-Oh!": ColorProfile.YUGIOH,
            "Archival": ColorProfile.NEUTRAL,
            "Grading": ColorProfile.NEUTRAL,
        }
        return profiles.get(preset, ColorProfile.STANDARD)

    def get_scanner_config(self) -> ScannerConfig:
        config = ScannerConfig()
        config.resolution = self.get_resolution()

        preset = self.preset_combo.currentText()
        if preset == "Archival" or preset == "Grading":
            config.brightness = 0
            config.contrast = 0
        else:
            config.brightness = 5
            config.contrast = 10

        return config

    def get_processing_config(self) -> ProcessingConfig:
        preset = self.preset_combo.currentText()

        if preset == "Archival":
            config = ProcessingConfig.for_archival()
        elif preset == "Grading":
            config = ProcessingConfig.for_grading()
        else:
            config = ProcessingConfig()
            config.color_profile = self.get_color_profile()

        # Apply checkbox settings
        config.white_balance = self.enhance_check.isChecked()
        config.denoise = self.denoise_check.isChecked()
        config.auto_rotate = self.auto_rotate_check.isChecked()
        config.auto_crop = self.auto_crop_check.isChecked()

        if self.sharpen_check.isChecked():
            config.sharpness = 1.2
            config.unsharp_mask = True
        else:
            config.sharpness = 1.0
            config.unsharp_mask = False

        config.output_format = self.get_output_format()

        return config


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Fuji TCG Scanner v{__version__}")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Apply dark theme
        self.setStyleSheet(DARK_THEME)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left side - Preview and controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(16)

        # Header
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(4)

        title = QLabel("Fuji TCG Scanner")
        title.setObjectName("titleLabel")
        header_layout.addWidget(title)

        subtitle = QLabel("High-quality scanning for Trading Card Games")
        subtitle.setObjectName("subtitleLabel")
        header_layout.addWidget(subtitle)

        left_layout.addWidget(header)

        # Preview area
        self.preview = PreviewWidget()
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.preview, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - Scanning...")
        left_layout.addWidget(self.progress_bar)

        # Scan button
        self.scan_btn = QPushButton("SCAN")
        self.scan_btn.setObjectName("scanButton")
        self.scan_btn.setFixedHeight(60)
        self.scan_btn.clicked.connect(self._start_scan)
        left_layout.addWidget(self.scan_btn)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #888;")
        left_layout.addWidget(self.status_label)

        main_layout.addWidget(left_panel, 2)

        # Right side - Tabs for settings and gallery
        right_panel = QTabWidget()

        # Settings tab
        self.settings = SettingsPanel()
        right_panel.addTab(self.settings, "Settings")

        # Gallery tab
        self.gallery = GalleryWidget()
        self.gallery.image_selected.connect(self._on_gallery_image_selected)
        right_panel.addTab(self.gallery, "Gallery")

        main_layout.addWidget(right_panel, 1)

        # Status bar
        self.statusBar().showMessage("Fuji TCG Scanner ready")

        # Worker thread
        self.worker: Optional[ScanWorker] = None

        # Load existing scans
        self._refresh_gallery()

    def _start_scan(self):
        """Start a scan operation."""
        if self.worker and self.worker.isRunning():
            return

        # Update UI
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText("Initializing scanner...")

        # Create worker
        backend = self.settings.get_backend()
        self.worker = ScanWorker(
            scanner_config=self.settings.get_scanner_config(),
            processing_config=self.settings.get_processing_config(),
            detection_config=DetectionConfig(),
            auto_crop=self.settings.auto_crop_check.isChecked(),
            mock_mode=self.settings.mock_check.isChecked(),
            backend=backend,
        )

        self.worker.progress.connect(self._on_scan_progress)
        self.worker.image_ready.connect(self._on_image_ready)
        self.worker.finished.connect(self._on_scan_finished)

        self.worker.start()

    def _on_scan_progress(self, message: str):
        """Handle progress updates."""
        self.status_label.setText(message)
        self.statusBar().showMessage(message)

    def _on_image_ready(self, image: Image.Image):
        """Handle raw scan preview."""
        try:
            self.preview.set_image(image)
        except Exception as e:
            logger.error(f"Failed to show preview: {e}")

    def _on_scan_finished(self, result):
        """Handle scan completion."""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("SCAN")
        self.progress_bar.setVisible(False)

        if isinstance(result, Exception):
            self.status_label.setText(f"Error: {result}")
            self.statusBar().showMessage(f"Scan failed: {result}")
            QMessageBox.critical(self, "Scan Error", str(result))
            return

        try:
            # Save the image
            output_dir = self.settings.get_output_directory()
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_format = self.settings.get_output_format()
            filename = f"card_{timestamp}.{output_format.value}"
            output_path = output_dir / filename

            # Save the image directly with PIL
            save_kwargs = {}
            if output_format == OutputFormat.JPEG:
                save_kwargs["quality"] = 95
                save_kwargs["optimize"] = True
            elif output_format == OutputFormat.PNG:
                save_kwargs["optimize"] = True

            result.image.save(str(output_path), **save_kwargs)
            logger.info(f"Saved image to {output_path}")

            # Update preview with final image
            self.preview.set_image(result.image)

            # Update gallery
            self._refresh_gallery()

            # Update status
            self.status_label.setText(f"Saved: {filename}")
            self.statusBar().showMessage(f"Scan saved to {output_path}")

        except Exception as e:
            logger.exception("Failed to save scan result")
            self.status_label.setText(f"Save error: {e}")
            QMessageBox.warning(self, "Save Error", f"Failed to save image: {e}")

    def _on_gallery_image_selected(self, path: Path):
        """Handle gallery image selection."""
        self.preview.set_pixmap_from_path(path)
        self.statusBar().showMessage(f"Viewing: {path.name}")

    def _refresh_gallery(self):
        """Refresh the gallery with current output directory."""
        output_dir = self.settings.get_output_directory()
        self.gallery.load_directory(output_dir)

    def closeEvent(self, event):
        """Handle window close."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        event.accept()


def run_gui():
    """Launch the GUI application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
