"""
Batch processing module for scanning and processing multiple TCG cards.

This module provides functionality for:
- Batch scanning through the ADF
- Processing multiple cards from a single scan
- Organized output file management
- Progress tracking and reporting
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from PIL import Image

from fuji_tcg_scanner.card_detector import CardDetector, DetectedCard, DetectionConfig
from fuji_tcg_scanner.image_processor import (
    ImageProcessor,
    OutputFormat,
    ProcessingConfig,
)
from fuji_tcg_scanner.scanner import (
    FujitsuScanner,
    MockScanner,
    PaperSize,
    ScannerConfig,
    ScanResult,
    ScanSource,
)

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    # Output settings
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    output_format: OutputFormat = OutputFormat.PNG
    jpeg_quality: int = 95

    # Naming convention
    filename_prefix: str = "card"
    use_timestamp: bool = True
    sequential_numbering: bool = True

    # Processing options
    auto_crop: bool = True
    process_images: bool = True
    save_originals: bool = False
    create_thumbnails: bool = True
    thumbnail_size: int = 300

    # Multi-card scan settings
    cards_per_scan: int = 1  # Expected cards per scan page
    grid_rows: int = 1
    grid_cols: int = 1

    # Scanner settings
    use_adf: bool = False
    max_pages: int = 0  # 0 = unlimited (until ADF empty)

    # Mock mode for testing
    mock_mode: bool = False


@dataclass
class BatchResult:
    """Results from a batch processing operation."""

    total_scans: int = 0
    total_cards: int = 0
    successful_cards: int = 0
    failed_cards: int = 0
    output_files: List[Path] = field(default_factory=list)
    thumbnail_files: List[Path] = field(default_factory=list)
    original_files: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def success_rate(self) -> float:
        if self.total_cards == 0:
            return 0.0
        return self.successful_cards / self.total_cards * 100

    def summary(self) -> str:
        """Generate a summary string."""
        return (
            f"Batch Processing Complete\n"
            f"========================\n"
            f"Total scans: {self.total_scans}\n"
            f"Total cards: {self.total_cards}\n"
            f"Successful: {self.successful_cards}\n"
            f"Failed: {self.failed_cards}\n"
            f"Success rate: {self.success_rate:.1f}%\n"
            f"Duration: {self.duration_seconds:.1f}s\n"
            f"Output files: {len(self.output_files)}"
        )


# Type for progress callback
ProgressCallback = Callable[[int, int, str], None]


class BatchProcessor:
    """
    Batch processor for TCG card scanning.

    Handles the complete workflow of scanning, detecting, processing,
    and saving multiple TCG cards.
    """

    def __init__(
        self,
        batch_config: Optional[BatchConfig] = None,
        scanner_config: Optional[ScannerConfig] = None,
        processing_config: Optional[ProcessingConfig] = None,
        detection_config: Optional[DetectionConfig] = None,
    ):
        """
        Initialize the batch processor.

        Args:
            batch_config: Batch processing configuration.
            scanner_config: Scanner settings.
            processing_config: Image processing settings.
            detection_config: Card detection settings.
        """
        self.batch_config = batch_config or BatchConfig()
        self.scanner_config = scanner_config or ScannerConfig().for_tcg_cards()
        self.processing_config = processing_config or ProcessingConfig.for_archival()
        self.detection_config = detection_config or DetectionConfig()

        self.image_processor = ImageProcessor(self.processing_config)
        self.card_detector = CardDetector(self.detection_config)

        self._progress_callback: Optional[ProgressCallback] = None
        self._card_counter = 0

    def set_progress_callback(self, callback: ProgressCallback) -> None:
        """Set callback function for progress updates."""
        self._progress_callback = callback

    def _report_progress(self, current: int, total: int, message: str) -> None:
        """Report progress to callback if set."""
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.batch_config.output_dir.mkdir(parents=True, exist_ok=True)

        if self.batch_config.save_originals:
            (self.batch_config.output_dir / "originals").mkdir(exist_ok=True)

        if self.batch_config.create_thumbnails:
            (self.batch_config.output_dir / "thumbnails").mkdir(exist_ok=True)

    def _generate_filename(self, card_index: int, suffix: str = "") -> str:
        """Generate output filename for a card."""
        parts = [self.batch_config.filename_prefix]

        if self.batch_config.use_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            parts.append(timestamp)

        if self.batch_config.sequential_numbering:
            parts.append(f"{card_index:04d}")

        if suffix:
            parts.append(suffix)

        return "_".join(parts)

    def _save_card(
        self,
        image: Image.Image,
        card_index: int,
        result: BatchResult,
    ) -> None:
        """Save a processed card image."""
        base_name = self._generate_filename(card_index)
        ext = self.batch_config.output_format.value

        # Save main image
        output_path = self.batch_config.output_dir / f"{base_name}.{ext}"
        self.image_processor.save(
            image,
            output_path,
            format=self.batch_config.output_format,
            quality=self.batch_config.jpeg_quality,
        )
        result.output_files.append(output_path)

        # Save thumbnail
        if self.batch_config.create_thumbnails:
            thumb = self.image_processor.create_thumbnail(
                image, self.batch_config.thumbnail_size
            )
            thumb_path = (
                self.batch_config.output_dir / "thumbnails" / f"{base_name}_thumb.{ext}"
            )
            self.image_processor.save(
                thumb, thumb_path, format=self.batch_config.output_format
            )
            result.thumbnail_files.append(thumb_path)

    def _save_original(
        self,
        scan_result: ScanResult,
        scan_index: int,
        result: BatchResult,
    ) -> None:
        """Save original scan image."""
        if not self.batch_config.save_originals:
            return

        base_name = f"scan_{scan_index:04d}"
        if self.batch_config.use_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"scan_{timestamp}_{scan_index:04d}"

        path = self.batch_config.output_dir / "originals" / f"{base_name}.png"
        scan_result.save(path, format="PNG")
        result.original_files.append(path)

    def process_image(
        self,
        image: Image.Image,
        result: BatchResult,
    ) -> List[Image.Image]:
        """
        Process a single scanned image and extract cards.

        Args:
            image: Scanned image.
            result: BatchResult to update.

        Returns:
            List of processed card images.
        """
        processed_cards = []

        # Detect cards
        if self.batch_config.auto_crop:
            if self.batch_config.cards_per_scan > 1:
                # Multi-card detection
                cards = self.card_detector.detect_grid(
                    image,
                    rows=self.batch_config.grid_rows,
                    cols=self.batch_config.grid_cols,
                )
            else:
                # Single card detection
                cards = self.card_detector.detect(image)

            for card in cards:
                result.total_cards += 1
                try:
                    # Extract card
                    card_image = self.card_detector.extract(image, card)

                    # Process card
                    if self.batch_config.process_images:
                        card_image = self.image_processor.process(card_image)

                    processed_cards.append(card_image)
                    result.successful_cards += 1

                except Exception as e:
                    logger.error(f"Failed to process card {card.index}: {e}")
                    result.failed_cards += 1
                    result.errors.append(f"Card {card.index}: {str(e)}")
        else:
            # No auto-crop, treat whole image as card
            result.total_cards += 1
            try:
                if self.batch_config.process_images:
                    image = self.image_processor.process(image)
                processed_cards.append(image)
                result.successful_cards += 1
            except Exception as e:
                logger.error(f"Failed to process image: {e}")
                result.failed_cards += 1
                result.errors.append(str(e))

        return processed_cards

    def scan_and_process(
        self,
        scanner: Optional[FujitsuScanner] = None,
    ) -> BatchResult:
        """
        Perform batch scanning and processing.

        Args:
            scanner: Scanner to use. Creates new one if None.

        Returns:
            BatchResult with processing statistics.
        """
        result = BatchResult()
        result.start_time = datetime.now()

        self._ensure_output_dir()
        self._card_counter = 0

        # Create or use scanner
        if scanner is None:
            if self.batch_config.mock_mode:
                scanner = MockScanner()
            else:
                scanner = FujitsuScanner()

        try:
            scanner.open()

            # Configure for TCG scanning
            scan_config = self.scanner_config
            if self.batch_config.use_adf:
                scan_config.source = ScanSource.ADF_FRONT
                scan_config.batch_mode = True

            scanner.configure(scan_config)

            # Perform scans
            scan_index = 0
            while True:
                # Check page limit
                if (
                    self.batch_config.max_pages > 0
                    and scan_index >= self.batch_config.max_pages
                ):
                    break

                try:
                    self._report_progress(
                        scan_index,
                        self.batch_config.max_pages,
                        f"Scanning page {scan_index + 1}...",
                    )

                    # Perform scan
                    scan_result = scanner.scan()
                    result.total_scans += 1

                    # Save original if requested
                    self._save_original(scan_result, scan_index, result)

                    # Process and extract cards
                    self._report_progress(
                        scan_index,
                        self.batch_config.max_pages,
                        "Processing cards...",
                    )

                    processed_cards = self.process_image(scan_result.image, result)

                    # Save processed cards
                    for card_image in processed_cards:
                        self._card_counter += 1
                        self._save_card(card_image, self._card_counter, result)

                    scan_index += 1

                    # If not using ADF, only scan once
                    if not self.batch_config.use_adf:
                        break

                except Exception as e:
                    error_msg = str(e).lower()
                    if "no document" in error_msg or "empty" in error_msg:
                        logger.info("ADF empty, batch complete")
                        break
                    elif "paper jam" in error_msg:
                        result.errors.append(f"Paper jam at scan {scan_index}")
                        logger.error(f"Paper jam at scan {scan_index}")
                        break
                    else:
                        logger.error(f"Scan error: {e}")
                        result.errors.append(f"Scan {scan_index}: {str(e)}")
                        break

        finally:
            scanner.close()

        result.end_time = datetime.now()
        logger.info(result.summary())

        return result

    def process_existing_images(
        self,
        image_paths: List[Path],
    ) -> BatchResult:
        """
        Process existing image files instead of scanning.

        Args:
            image_paths: List of image file paths.

        Returns:
            BatchResult with processing statistics.
        """
        result = BatchResult()
        result.start_time = datetime.now()

        self._ensure_output_dir()
        self._card_counter = 0

        for i, path in enumerate(image_paths):
            self._report_progress(
                i, len(image_paths), f"Processing {path.name}..."
            )

            try:
                image = Image.open(path)
                result.total_scans += 1

                processed_cards = self.process_image(image, result)

                for card_image in processed_cards:
                    self._card_counter += 1
                    self._save_card(card_image, self._card_counter, result)

            except Exception as e:
                logger.error(f"Failed to process {path}: {e}")
                result.errors.append(f"{path.name}: {str(e)}")

        result.end_time = datetime.now()
        logger.info(result.summary())

        return result

    def preview_detection(
        self,
        image: Image.Image,
    ) -> Image.Image:
        """
        Create a preview showing detected cards.

        Args:
            image: Source image.

        Returns:
            Image with detection overlays.
        """
        cards = self.card_detector.detect(image)
        return self.card_detector.visualize_detections(image, cards)


def quick_scan(
    output_dir: Optional[Path] = None,
    mock: bool = False,
) -> BatchResult:
    """
    Convenience function for quick single-card scanning.

    Args:
        output_dir: Output directory. Defaults to ./output.
        mock: Use mock scanner for testing.

    Returns:
        BatchResult from the scan.
    """
    config = BatchConfig(
        output_dir=output_dir or Path("./output"),
        cards_per_scan=1,
        auto_crop=True,
        process_images=True,
        mock_mode=mock,
    )

    processor = BatchProcessor(batch_config=config)
    return processor.scan_and_process()


def batch_scan_adf(
    output_dir: Optional[Path] = None,
    max_pages: int = 0,
    mock: bool = False,
) -> BatchResult:
    """
    Convenience function for batch scanning through ADF.

    Args:
        output_dir: Output directory. Defaults to ./output.
        max_pages: Maximum pages to scan. 0 = until empty.
        mock: Use mock scanner for testing.

    Returns:
        BatchResult from the batch scan.
    """
    config = BatchConfig(
        output_dir=output_dir or Path("./output"),
        use_adf=True,
        max_pages=max_pages,
        cards_per_scan=1,
        auto_crop=True,
        process_images=True,
        mock_mode=mock,
    )

    processor = BatchProcessor(batch_config=config)
    return processor.scan_and_process()
