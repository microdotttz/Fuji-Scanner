"""
Configuration management for TCG Scanner application.

Provides persistent settings storage, presets, and profile management.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fuji_tcg_scanner.image_processor import ColorProfile, OutputFormat, ProcessingConfig
from fuji_tcg_scanner.scanner import ScanMode, ScannerConfig, ScanSource

logger = logging.getLogger(__name__)


# Default config directory
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "fuji-tcg-scanner"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"


class ScannerSettings(BaseModel):
    """Scanner-specific settings."""

    resolution: int = Field(default=600, ge=50, le=1200)
    mode: str = Field(default="Color")
    source: str = Field(default="Flatbed")
    brightness: int = Field(default=5, ge=-100, le=100)
    contrast: int = Field(default=10, ge=-100, le=100)
    gamma: float = Field(default=1.0, ge=0.1, le=5.0)

    def to_scanner_config(self) -> ScannerConfig:
        """Convert to ScannerConfig object."""
        return ScannerConfig(
            resolution=self.resolution,
            mode=ScanMode(self.mode),
            source=ScanSource(self.source),
            brightness=self.brightness,
            contrast=self.contrast,
            gamma=self.gamma,
        )


class ProcessingSettings(BaseModel):
    """Image processing settings."""

    brightness: float = Field(default=1.0, ge=0.5, le=2.0)
    contrast: float = Field(default=1.05, ge=0.5, le=2.0)
    saturation: float = Field(default=1.0, ge=0.5, le=2.0)
    sharpness: float = Field(default=1.2, ge=0.5, le=3.0)
    color_profile: str = Field(default="standard")
    white_balance: bool = Field(default=True)
    denoise: bool = Field(default=True)
    denoise_strength: int = Field(default=5, ge=1, le=20)
    unsharp_mask: bool = Field(default=True)
    auto_rotate: bool = Field(default=True)
    auto_crop: bool = Field(default=True)

    def to_processing_config(self) -> ProcessingConfig:
        """Convert to ProcessingConfig object."""
        return ProcessingConfig(
            brightness=self.brightness,
            contrast=self.contrast,
            saturation=self.saturation,
            sharpness=self.sharpness,
            color_profile=ColorProfile(self.color_profile),
            white_balance=self.white_balance,
            denoise=self.denoise,
            denoise_strength=self.denoise_strength,
            unsharp_mask=self.unsharp_mask,
            auto_rotate=self.auto_rotate,
            auto_crop=self.auto_crop,
        )


class OutputSettings(BaseModel):
    """Output file settings."""

    directory: str = Field(default="./output")
    format: str = Field(default="png")
    jpeg_quality: int = Field(default=95, ge=1, le=100)
    filename_prefix: str = Field(default="card")
    use_timestamp: bool = Field(default=True)
    create_thumbnails: bool = Field(default=True)
    thumbnail_size: int = Field(default=300, ge=50, le=1000)
    save_originals: bool = Field(default=False)


class Preset(BaseModel):
    """A saved configuration preset."""

    name: str
    description: str = ""
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TCG_SCANNER_",
        env_nested_delimiter="__",
    )

    # Scanner settings
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)

    # Processing settings
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)

    # Output settings
    output: OutputSettings = Field(default_factory=OutputSettings)

    # Application settings
    mock_mode: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    show_preview: bool = Field(default=True)

    # Preset management
    active_preset: Optional[str] = Field(default=None)
    presets: Dict[str, Preset] = Field(default_factory=dict)


class ConfigManager:
    """
    Manages application configuration and presets.

    Handles loading/saving configuration from TOML files,
    preset management, and configuration validation.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration manager.

        Args:
            config_path: Path to configuration file. Uses default if None.
        """
        self.config_path = config_path or DEFAULT_CONFIG_FILE
        self.config = AppConfig()
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppConfig:
        """
        Load configuration from file.

        Returns:
            Loaded configuration.
        """
        if not self.config_path.exists():
            logger.info("No config file found, using defaults")
            return self.config

        try:
            with open(self.config_path, "rb") as f:
                data = tomllib.load(f)

            self.config = AppConfig(**data)
            logger.info(f"Loaded configuration from {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            logger.info("Using default configuration")

        return self.config

    def save(self) -> None:
        """Save current configuration to file."""
        try:
            # Convert to dict for TOML serialization
            data = self.config.model_dump()

            # Write as TOML
            toml_content = self._dict_to_toml(data)

            with open(self.config_path, "w") as f:
                f.write(toml_content)

            logger.info(f"Saved configuration to {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

    def _dict_to_toml(self, data: Dict[str, Any], indent: int = 0) -> str:
        """Convert dictionary to TOML string."""
        lines = []
        prefix = "  " * indent

        # Process simple key-value pairs first
        for key, value in data.items():
            if isinstance(value, dict):
                continue
            elif isinstance(value, bool):
                lines.append(f"{prefix}{key} = {str(value).lower()}")
            elif isinstance(value, str):
                lines.append(f'{prefix}{key} = "{value}"')
            elif value is None:
                continue
            else:
                lines.append(f"{prefix}{key} = {value}")

        # Process nested dictionaries
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append("")
                lines.append(f"{prefix}[{key}]")
                lines.append(self._dict_to_toml(value, indent))

        return "\n".join(lines)

    def get_preset(self, name: str) -> Optional[Preset]:
        """Get a preset by name."""
        return self.config.presets.get(name)

    def save_preset(self, preset: Preset) -> None:
        """Save a new or updated preset."""
        self.config.presets[preset.name] = preset
        self.save()
        logger.info(f"Saved preset: {preset.name}")

    def delete_preset(self, name: str) -> bool:
        """Delete a preset by name."""
        if name in self.config.presets:
            del self.config.presets[name]
            self.save()
            logger.info(f"Deleted preset: {name}")
            return True
        return False

    def list_presets(self) -> List[str]:
        """Get list of preset names."""
        return list(self.config.presets.keys())

    def apply_preset(self, name: str) -> bool:
        """Apply a preset to current configuration."""
        preset = self.get_preset(name)
        if preset is None:
            logger.warning(f"Preset not found: {name}")
            return False

        self.config.scanner = preset.scanner
        self.config.processing = preset.processing
        self.config.output = preset.output
        self.config.active_preset = name
        logger.info(f"Applied preset: {name}")
        return True

    def create_default_presets(self) -> None:
        """Create built-in default presets."""
        # Archival quality preset
        archival = Preset(
            name="archival",
            description="High-quality archival settings for preservation",
            scanner=ScannerSettings(
                resolution=600,
                brightness=0,
                contrast=0,
            ),
            processing=ProcessingSettings(
                brightness=1.0,
                contrast=1.0,
                saturation=1.0,
                sharpness=1.0,
                color_profile="neutral",
                denoise=False,
            ),
            output=OutputSettings(
                format="png",
                create_thumbnails=True,
                save_originals=True,
            ),
        )

        # Quick sharing preset
        sharing = Preset(
            name="sharing",
            description="Optimized for online sharing and selling",
            scanner=ScannerSettings(
                resolution=300,
                brightness=5,
                contrast=10,
            ),
            processing=ProcessingSettings(
                brightness=1.02,
                contrast=1.1,
                saturation=1.05,
                sharpness=1.3,
                color_profile="vivid",
            ),
            output=OutputSettings(
                format="jpeg",
                jpeg_quality=90,
                create_thumbnails=True,
            ),
        )

        # Pokemon optimized preset
        pokemon = Preset(
            name="pokemon",
            description="Optimized for Pokemon TCG cards",
            scanner=ScannerSettings(
                resolution=600,
                brightness=5,
                contrast=10,
            ),
            processing=ProcessingSettings(
                brightness=1.02,
                contrast=1.05,
                saturation=1.08,
                sharpness=1.2,
                color_profile="pokemon",
            ),
            output=OutputSettings(
                format="png",
                filename_prefix="pokemon",
            ),
        )

        # MTG preset
        mtg = Preset(
            name="mtg",
            description="Optimized for Magic: The Gathering cards",
            scanner=ScannerSettings(
                resolution=600,
                brightness=3,
                contrast=12,
            ),
            processing=ProcessingSettings(
                brightness=0.98,
                contrast=1.08,
                saturation=1.05,
                sharpness=1.2,
                color_profile="mtg",
            ),
            output=OutputSettings(
                format="png",
                filename_prefix="mtg",
            ),
        )

        # Grading preset
        grading = Preset(
            name="grading",
            description="Accurate colors for card grading evaluation",
            scanner=ScannerSettings(
                resolution=600,
                brightness=0,
                contrast=0,
            ),
            processing=ProcessingSettings(
                brightness=1.0,
                contrast=1.0,
                saturation=1.0,
                sharpness=1.0,
                color_profile="neutral",
                white_balance=True,
                denoise=False,
                unsharp_mask=False,
            ),
            output=OutputSettings(
                format="png",
                save_originals=True,
            ),
        )

        for preset in [archival, sharing, pokemon, mtg, grading]:
            if preset.name not in self.config.presets:
                self.config.presets[preset.name] = preset

        self.save()
        logger.info("Created default presets")

    def get_scanner_config(self) -> ScannerConfig:
        """Get current scanner configuration."""
        return self.config.scanner.to_scanner_config()

    def get_processing_config(self) -> ProcessingConfig:
        """Get current processing configuration."""
        return self.config.processing.to_processing_config()

    def get_output_path(self) -> Path:
        """Get output directory path."""
        return Path(self.config.output.directory)


def get_default_config() -> AppConfig:
    """Get default application configuration."""
    return AppConfig()


def load_config(path: Optional[Path] = None) -> ConfigManager:
    """
    Load configuration from file.

    Args:
        path: Optional config file path.

    Returns:
        ConfigManager with loaded configuration.
    """
    manager = ConfigManager(path)
    manager.load()
    return manager
