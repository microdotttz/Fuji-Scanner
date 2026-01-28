"""
Image processing module for TCG card scan optimization.

This module provides image enhancement and processing functions
specifically designed for Trading Card Game card scans.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


class ColorProfile(Enum):
    """Color profiles for different card types."""

    STANDARD = "standard"  # General purpose
    POKEMON = "pokemon"  # Optimized for Pokemon cards
    MTG = "mtg"  # Magic: The Gathering
    YUGIOH = "yugioh"  # Yu-Gi-Oh!
    SPORTS = "sports"  # Sports cards
    VIVID = "vivid"  # Enhanced saturation
    NEUTRAL = "neutral"  # Minimal processing


class OutputFormat(Enum):
    """Output image formats."""

    PNG = "png"  # Lossless, best for archiving
    JPEG = "jpeg"  # Good for sharing, smaller size
    TIFF = "tiff"  # Professional archival format
    WEBP = "webp"  # Modern web format


@dataclass
class ProcessingConfig:
    """Configuration for image processing pipeline."""

    # Color adjustments
    brightness: float = 1.0  # 0.5 - 2.0
    contrast: float = 1.0  # 0.5 - 2.0
    saturation: float = 1.0  # 0.5 - 2.0
    sharpness: float = 1.2  # 0.5 - 3.0

    # Advanced color
    color_profile: ColorProfile = ColorProfile.STANDARD
    white_balance: bool = True
    gamma: float = 1.0  # 0.5 - 2.0

    # Noise reduction
    denoise: bool = True
    denoise_strength: int = 5  # 1 - 20

    # Edge enhancement
    unsharp_mask: bool = True
    unsharp_radius: float = 1.5
    unsharp_amount: float = 1.0

    # Output settings
    output_format: OutputFormat = OutputFormat.PNG
    jpeg_quality: int = 95  # 1 - 100
    resize_factor: float = 1.0  # 0.25 - 4.0

    # Card-specific
    auto_rotate: bool = True
    auto_crop: bool = True
    border_removal: bool = False

    @classmethod
    def for_archival(cls) -> ProcessingConfig:
        """High-quality archival settings."""
        return cls(
            brightness=1.0,
            contrast=1.05,
            saturation=1.0,
            sharpness=1.1,
            color_profile=ColorProfile.STANDARD,
            white_balance=True,
            denoise=True,
            denoise_strength=3,
            unsharp_mask=True,
            output_format=OutputFormat.PNG,
            auto_rotate=True,
            auto_crop=True,
        )

    @classmethod
    def for_sharing(cls) -> ProcessingConfig:
        """Optimized for sharing online."""
        return cls(
            brightness=1.02,
            contrast=1.1,
            saturation=1.05,
            sharpness=1.3,
            color_profile=ColorProfile.VIVID,
            denoise=True,
            denoise_strength=5,
            output_format=OutputFormat.JPEG,
            jpeg_quality=90,
            auto_rotate=True,
            auto_crop=True,
        )

    @classmethod
    def for_grading(cls) -> ProcessingConfig:
        """Accurate colors for grading evaluation."""
        return cls(
            brightness=1.0,
            contrast=1.0,
            saturation=1.0,
            sharpness=1.0,
            color_profile=ColorProfile.NEUTRAL,
            white_balance=True,
            denoise=False,
            unsharp_mask=False,
            output_format=OutputFormat.TIFF,
            auto_rotate=True,
            auto_crop=True,
        )


class ImageProcessor:
    """
    Image processing pipeline for TCG card scans.

    Provides a comprehensive set of image enhancement tools
    optimized for trading card artwork and text clarity.
    """

    # Standard TCG card aspect ratio
    TCG_ASPECT_RATIO = 63.5 / 88.9  # ~0.714

    def __init__(self, config: Optional[ProcessingConfig] = None):
        """
        Initialize the image processor.

        Args:
            config: Processing configuration. Uses defaults if None.
        """
        self.config = config or ProcessingConfig()

    def process(self, image: Image.Image) -> Image.Image:
        """
        Apply full processing pipeline to an image.

        Args:
            image: Input PIL Image.

        Returns:
            Processed PIL Image.
        """
        logger.info(f"Processing image: {image.width}x{image.height}")

        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Apply processing steps
        if self.config.white_balance:
            image = self.auto_white_balance(image)

        if self.config.color_profile != ColorProfile.NEUTRAL:
            image = self.apply_color_profile(image, self.config.color_profile)

        # Basic adjustments
        image = self.adjust_brightness(image, self.config.brightness)
        image = self.adjust_contrast(image, self.config.contrast)
        image = self.adjust_saturation(image, self.config.saturation)

        if self.config.gamma != 1.0:
            image = self.apply_gamma(image, self.config.gamma)

        # Noise reduction (before sharpening)
        if self.config.denoise:
            image = self.reduce_noise(image, self.config.denoise_strength)

        # Sharpening
        if self.config.unsharp_mask:
            image = self.unsharp_mask(
                image,
                self.config.unsharp_radius,
                self.config.unsharp_amount,
            )

        image = self.adjust_sharpness(image, self.config.sharpness)

        # Resize if needed
        if self.config.resize_factor != 1.0:
            image = self.resize(image, self.config.resize_factor)

        logger.info(f"Processing complete: {image.width}x{image.height}")
        return image

    def adjust_brightness(
        self, image: Image.Image, factor: float
    ) -> Image.Image:
        """
        Adjust image brightness.

        Args:
            image: Input image.
            factor: Brightness factor (1.0 = no change).

        Returns:
            Adjusted image.
        """
        if factor == 1.0:
            return image
        enhancer = ImageEnhance.Brightness(image)
        return enhancer.enhance(factor)

    def adjust_contrast(
        self, image: Image.Image, factor: float
    ) -> Image.Image:
        """
        Adjust image contrast.

        Args:
            image: Input image.
            factor: Contrast factor (1.0 = no change).

        Returns:
            Adjusted image.
        """
        if factor == 1.0:
            return image
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)

    def adjust_saturation(
        self, image: Image.Image, factor: float
    ) -> Image.Image:
        """
        Adjust color saturation.

        Args:
            image: Input image.
            factor: Saturation factor (1.0 = no change).

        Returns:
            Adjusted image.
        """
        if factor == 1.0:
            return image
        enhancer = ImageEnhance.Color(image)
        return enhancer.enhance(factor)

    def adjust_sharpness(
        self, image: Image.Image, factor: float
    ) -> Image.Image:
        """
        Adjust image sharpness.

        Args:
            image: Input image.
            factor: Sharpness factor (1.0 = no change).

        Returns:
            Adjusted image.
        """
        if factor == 1.0:
            return image
        enhancer = ImageEnhance.Sharpness(image)
        return enhancer.enhance(factor)

    def apply_gamma(self, image: Image.Image, gamma: float) -> Image.Image:
        """
        Apply gamma correction.

        Args:
            image: Input image.
            gamma: Gamma value (1.0 = no change).

        Returns:
            Gamma-corrected image.
        """
        if gamma == 1.0:
            return image

        # Create lookup table
        inv_gamma = 1.0 / gamma
        lut = np.array([
            ((i / 255.0) ** inv_gamma) * 255
            for i in range(256)
        ]).astype(np.uint8)

        # Apply to each channel
        img_array = np.array(image)
        corrected = cv2.LUT(img_array, lut)
        return Image.fromarray(corrected)

    def auto_white_balance(self, image: Image.Image) -> Image.Image:
        """
        Automatically adjust white balance using gray world assumption.

        Args:
            image: Input image.

        Returns:
            White-balanced image.
        """
        img_array = np.array(image).astype(np.float32)

        # Calculate average for each channel
        avg_r = np.mean(img_array[:, :, 0])
        avg_g = np.mean(img_array[:, :, 1])
        avg_b = np.mean(img_array[:, :, 2])

        # Calculate gray average
        avg_gray = (avg_r + avg_g + avg_b) / 3

        # Calculate scaling factors
        if avg_r > 0:
            scale_r = avg_gray / avg_r
        else:
            scale_r = 1.0
        if avg_g > 0:
            scale_g = avg_gray / avg_g
        else:
            scale_g = 1.0
        if avg_b > 0:
            scale_b = avg_gray / avg_b
        else:
            scale_b = 1.0

        # Apply scaling with limits to prevent over-correction
        max_scale = 1.5
        min_scale = 0.7
        scale_r = np.clip(scale_r, min_scale, max_scale)
        scale_g = np.clip(scale_g, min_scale, max_scale)
        scale_b = np.clip(scale_b, min_scale, max_scale)

        img_array[:, :, 0] = np.clip(img_array[:, :, 0] * scale_r, 0, 255)
        img_array[:, :, 1] = np.clip(img_array[:, :, 1] * scale_g, 0, 255)
        img_array[:, :, 2] = np.clip(img_array[:, :, 2] * scale_b, 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    def apply_color_profile(
        self, image: Image.Image, profile: ColorProfile
    ) -> Image.Image:
        """
        Apply a color profile for specific card types.

        Args:
            image: Input image.
            profile: Color profile to apply.

        Returns:
            Color-adjusted image.
        """
        if profile == ColorProfile.NEUTRAL:
            return image

        # Profile-specific adjustments
        adjustments = {
            ColorProfile.STANDARD: {
                "saturation": 1.0,
                "contrast": 1.02,
                "brightness": 1.0,
            },
            ColorProfile.POKEMON: {
                "saturation": 1.08,  # Vibrant colors
                "contrast": 1.05,
                "brightness": 1.02,
            },
            ColorProfile.MTG: {
                "saturation": 1.05,  # Rich, dark tones
                "contrast": 1.08,
                "brightness": 0.98,
            },
            ColorProfile.YUGIOH: {
                "saturation": 1.1,  # High saturation
                "contrast": 1.05,
                "brightness": 1.0,
            },
            ColorProfile.SPORTS: {
                "saturation": 1.02,  # Natural colors
                "contrast": 1.05,
                "brightness": 1.02,
            },
            ColorProfile.VIVID: {
                "saturation": 1.15,
                "contrast": 1.1,
                "brightness": 1.02,
            },
        }

        adj = adjustments.get(profile, adjustments[ColorProfile.STANDARD])

        image = self.adjust_saturation(image, adj["saturation"])
        image = self.adjust_contrast(image, adj["contrast"])
        image = self.adjust_brightness(image, adj["brightness"])

        return image

    def reduce_noise(
        self, image: Image.Image, strength: int = 5
    ) -> Image.Image:
        """
        Reduce image noise while preserving edges.

        Uses bilateral filtering for edge-preserving noise reduction.

        Args:
            image: Input image.
            strength: Denoising strength (1-20).

        Returns:
            Denoised image.
        """
        img_array = np.array(image)

        # Bilateral filter preserves edges better than Gaussian
        # d = diameter, sigmaColor, sigmaSpace
        d = min(9, max(5, strength))
        sigma = strength * 10

        denoised = cv2.bilateralFilter(img_array, d, sigma, sigma)

        return Image.fromarray(denoised)

    def unsharp_mask(
        self,
        image: Image.Image,
        radius: float = 1.5,
        amount: float = 1.0,
        threshold: int = 0,
    ) -> Image.Image:
        """
        Apply unsharp mask sharpening.

        Args:
            image: Input image.
            radius: Blur radius for the mask.
            amount: Strength of the sharpening effect.
            threshold: Threshold to prevent sharpening noise.

        Returns:
            Sharpened image.
        """
        if amount == 0:
            return image

        img_array = np.array(image).astype(np.float32)

        # Create blurred version
        kernel_size = int(radius * 2) * 2 + 1  # Ensure odd
        blurred = cv2.GaussianBlur(img_array, (kernel_size, kernel_size), radius)

        # Calculate the unsharp mask
        mask = img_array - blurred

        # Apply threshold
        if threshold > 0:
            mask = np.where(np.abs(mask) < threshold, 0, mask)

        # Apply the mask
        sharpened = img_array + mask * amount

        # Clip values
        sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

        return Image.fromarray(sharpened)

    def resize(
        self, image: Image.Image, factor: float
    ) -> Image.Image:
        """
        Resize image by a scale factor.

        Args:
            image: Input image.
            factor: Scale factor (1.0 = no change).

        Returns:
            Resized image.
        """
        if factor == 1.0:
            return image

        new_width = int(image.width * factor)
        new_height = int(image.height * factor)

        # Use high-quality resampling
        return image.resize(
            (new_width, new_height),
            resample=Image.Resampling.LANCZOS,
        )

    def rotate(
        self, image: Image.Image, angle: float, expand: bool = True
    ) -> Image.Image:
        """
        Rotate image by specified angle.

        Args:
            image: Input image.
            angle: Rotation angle in degrees (counter-clockwise).
            expand: If True, expand canvas to fit rotated image.

        Returns:
            Rotated image.
        """
        if angle == 0:
            return image

        return image.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            expand=expand,
            fillcolor=(255, 255, 255),
        )

    def crop(
        self,
        image: Image.Image,
        box: Tuple[int, int, int, int],
    ) -> Image.Image:
        """
        Crop image to specified region.

        Args:
            image: Input image.
            box: (left, top, right, bottom) pixel coordinates.

        Returns:
            Cropped image.
        """
        return image.crop(box)

    def add_border(
        self,
        image: Image.Image,
        width: int = 10,
        color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Image.Image:
        """
        Add a border around the image.

        Args:
            image: Input image.
            width: Border width in pixels.
            color: Border color (RGB).

        Returns:
            Image with border.
        """
        new_width = image.width + 2 * width
        new_height = image.height + 2 * width

        bordered = Image.new("RGB", (new_width, new_height), color)
        bordered.paste(image, (width, width))

        return bordered

    def save(
        self,
        image: Image.Image,
        path: Path,
        format: Optional[OutputFormat] = None,
        quality: Optional[int] = None,
    ) -> None:
        """
        Save processed image to disk.

        Args:
            image: Image to save.
            path: Output file path.
            format: Output format. Uses config if None.
            quality: JPEG quality. Uses config if None.
        """
        fmt = format or self.config.output_format
        qual = quality or self.config.jpeg_quality

        save_kwargs = {}

        if fmt == OutputFormat.JPEG:
            save_kwargs["quality"] = qual
            save_kwargs["optimize"] = True
            # Ensure RGB mode for JPEG
            if image.mode != "RGB":
                image = image.convert("RGB")
        elif fmt == OutputFormat.PNG:
            save_kwargs["optimize"] = True
        elif fmt == OutputFormat.TIFF:
            save_kwargs["compression"] = "lzw"
        elif fmt == OutputFormat.WEBP:
            save_kwargs["quality"] = qual
            save_kwargs["method"] = 6  # Best compression

        # Ensure path has correct extension
        path = path.with_suffix(f".{fmt.value}")

        image.save(path, format=fmt.value.upper(), **save_kwargs)
        logger.info(f"Saved image to {path}")

    def create_thumbnail(
        self,
        image: Image.Image,
        max_size: int = 300,
    ) -> Image.Image:
        """
        Create a thumbnail of the image.

        Args:
            image: Input image.
            max_size: Maximum dimension (width or height).

        Returns:
            Thumbnail image.
        """
        thumbnail = image.copy()
        thumbnail.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return thumbnail

    def analyze_image(self, image: Image.Image) -> dict:
        """
        Analyze image properties and quality metrics.

        Args:
            image: Input image.

        Returns:
            Dictionary of image analysis metrics.
        """
        img_array = np.array(image)

        # Basic properties
        analysis = {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "aspect_ratio": image.width / image.height,
        }

        # Color statistics
        if len(img_array.shape) == 3:
            analysis["mean_r"] = float(np.mean(img_array[:, :, 0]))
            analysis["mean_g"] = float(np.mean(img_array[:, :, 1]))
            analysis["mean_b"] = float(np.mean(img_array[:, :, 2]))
            analysis["mean_brightness"] = float(np.mean(img_array))

            # Color variance (indication of image content)
            analysis["color_variance"] = float(np.var(img_array))
        else:
            analysis["mean_brightness"] = float(np.mean(img_array))

        # Sharpness estimate using Laplacian variance
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if len(img_array.shape) == 3 else img_array
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        analysis["sharpness_score"] = float(laplacian.var())

        # Is it likely a TCG card? (aspect ratio check)
        expected_ratio = self.TCG_ASPECT_RATIO
        actual_ratio = min(image.width, image.height) / max(image.width, image.height)
        analysis["tcg_card_match"] = abs(actual_ratio - expected_ratio) < 0.05

        return analysis
