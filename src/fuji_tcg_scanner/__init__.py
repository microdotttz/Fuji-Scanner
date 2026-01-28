"""
Fuji TCG Scanner - High-quality TCG card scanner for Fujitsu fi-6140z

This application provides optimized scanning settings and image processing
for Trading Card Game (TCG) cards using the Fujitsu fi-6140z document scanner.
"""

__version__ = "1.0.0"
__author__ = "TCG Scanner Team"

from fuji_tcg_scanner.scanner import FujitsuScanner, ScannerConfig
from fuji_tcg_scanner.image_processor import ImageProcessor, ProcessingConfig
from fuji_tcg_scanner.card_detector import CardDetector, DetectionConfig

__all__ = [
    "FujitsuScanner",
    "ScannerConfig",
    "ImageProcessor",
    "ProcessingConfig",
    "CardDetector",
    "DetectionConfig",
]
