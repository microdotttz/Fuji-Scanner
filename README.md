# Fuji TCG Scanner

High-quality TCG (Trading Card Game) card scanner application optimized for the Fujitsu fi-6140z document scanner.

## Features

- **Optimized Scanning Settings**: Pre-configured for best TCG card quality at 600 DPI
- **Automatic Card Detection**: Detects and extracts individual cards from scans
- **Perspective Correction**: Automatically straightens tilted cards
- **Color Optimization**: Enhances colors for accurate card representation
- **Multiple Card Support**: Scan grids of cards and automatically separate them
- **Batch Scanning**: Process multiple cards through the Automatic Document Feeder (ADF)
- **Preset Profiles**: Built-in presets for Pokemon, MTG, Yu-Gi-Oh!, and more
- **Format Options**: Save as PNG (archival), JPEG (sharing), TIFF, or WebP

## Requirements

### System Requirements

- Linux (tested on Ubuntu 20.04+, Debian 11+)
- Python 3.9 or higher
- SANE scanner drivers
- Fujitsu fi-6140z scanner (other Fujitsu models may work)

### Installing SANE Drivers

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install sane sane-utils libsane-extras

# Add user to scanner group
sudo usermod -a -G scanner $USER

# Verify scanner is detected
scanimage -L
```

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/your-repo/fuji-tcg-scanner.git
cd fuji-tcg-scanner

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install package
pip install -e .
```

### Dependencies

The package will automatically install:
- `python-sane` - Scanner interface
- `Pillow` - Image processing
- `opencv-python` - Card detection and perspective correction
- `numpy` - Numerical operations
- `click` - CLI framework
- `rich` - Terminal UI
- `pydantic` - Configuration management

## Quick Start

### Scan a Single Card

```bash
# Basic scan with automatic card detection
tcg-scanner scan

# Scan with specific output directory
tcg-scanner scan -o ./my_cards

# Use a preset profile
tcg-scanner scan --preset pokemon

# Save as JPEG for sharing
tcg-scanner scan --format jpeg
```

### Batch Scanning (ADF)

```bash
# Scan all cards in ADF
tcg-scanner batch

# Limit to 10 pages
tcg-scanner batch --max-pages 10
```

### Process Existing Images

```bash
# Process scanned images
tcg-scanner process image1.png image2.png -o ./processed
```

### List Available Scanners

```bash
tcg-scanner devices
```

### Preview Scan

```bash
tcg-scanner preview
```

## Commands

| Command | Description |
|---------|-------------|
| `scan` | Scan a single card from flatbed |
| `batch` | Batch scan through ADF |
| `process` | Process existing image files |
| `preview` | Quick low-resolution preview |
| `devices` | List available scanners |
| `preset list` | List available presets |
| `preset show <name>` | Show preset details |
| `preset create <name>` | Create new preset |
| `config` | Show current configuration |
| `init` | Initialize with default presets |

## Presets

Built-in presets optimized for different use cases:

| Preset | Description | Best For |
|--------|-------------|----------|
| `archival` | Highest quality, no processing | Long-term preservation |
| `sharing` | Enhanced colors, JPEG output | Online selling/trading |
| `pokemon` | Vibrant colors for Pokemon cards | Pokemon TCG |
| `mtg` | Rich tones for Magic cards | Magic: The Gathering |
| `grading` | Accurate colors, minimal processing | Card grading evaluation |

### Using Presets

```bash
# List all presets
tcg-scanner preset list

# Use a preset
tcg-scanner scan --preset pokemon

# View preset details
tcg-scanner preset show mtg
```

## Scanning Tips for Best Results

### Card Placement

1. Place card face-down on the scanner glass
2. Align with the top-left corner (leave ~5mm margin)
3. Ensure card is flat and not bent
4. Close the scanner lid gently

### Multi-Card Scanning

For scanning multiple cards at once:
1. Arrange cards in a grid pattern (e.g., 3x3)
2. Leave ~10mm spacing between cards
3. The software will automatically detect and separate them

### ADF Batch Scanning

1. Use card sleeves to protect cards in the ADF
2. Fan the stack before loading to prevent jams
3. Don't overload - the fi-6140z holds up to 50 sheets

### Optimal Settings

- **Resolution**: 600 DPI for archival, 300 DPI for sharing
- **Color Mode**: Always use Color for TCG cards
- **Format**: PNG for quality, JPEG for smaller files

## Configuration

Configuration is stored in `~/.config/fuji-tcg-scanner/config.toml`.

### Example Configuration

```toml
[scanner]
resolution = 600
mode = "Color"
brightness = 5
contrast = 10

[processing]
brightness = 1.0
contrast = 1.05
saturation = 1.0
sharpness = 1.2
color_profile = "standard"
white_balance = true
denoise = true
auto_crop = true

[output]
directory = "./output"
format = "png"
create_thumbnails = true
```

## Python API

```python
from fuji_tcg_scanner import FujitsuScanner, ImageProcessor, CardDetector
from fuji_tcg_scanner.scanner import ScannerConfig

# Initialize scanner
scanner = FujitsuScanner()

# Scan with optimized settings
with scanner:
    config = ScannerConfig().for_tcg_cards()
    result = scanner.scan(config)

    # Detect and extract card
    detector = CardDetector()
    cards = detector.detect(result.image)

    if cards:
        card_image = detector.extract(result.image, cards[0])

        # Process the image
        processor = ImageProcessor()
        processed = processor.process(card_image)

        # Save
        processed.save("my_card.png")
```

## Troubleshooting

### Scanner Not Found

1. Check USB connection
2. Verify scanner is powered on
3. Run `scanimage -L` to check SANE detection
4. Ensure user is in `scanner` group

### Permission Denied

```bash
# Add to scanner group
sudo usermod -a -G scanner $USER

# Logout and login, or run:
newgrp scanner
```

### Poor Scan Quality

- Clean scanner glass with microfiber cloth
- Check brightness/contrast settings
- Ensure card is flat on glass
- Try increasing resolution to 600 DPI

### Cards Not Detected

- Ensure sufficient contrast with scanner background
- Check card is within scan area
- Try adjusting detection sensitivity
- Use `--no-crop` for manual processing

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please submit issues and pull requests on GitHub.

## Acknowledgments

- SANE Project for scanner drivers
- OpenCV for image processing capabilities
- The TCG collecting community for feedback and testing
