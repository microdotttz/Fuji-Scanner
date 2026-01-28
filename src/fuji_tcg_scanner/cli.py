"""
Command-line interface for TCG Scanner application.

Provides a rich terminal interface for scanning and processing TCG cards.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.prompt import Confirm

from fuji_tcg_scanner import __version__
from fuji_tcg_scanner.batch_processor import BatchConfig, BatchProcessor, BatchResult
from fuji_tcg_scanner.config import ConfigManager, Preset, load_config
from fuji_tcg_scanner.image_processor import ColorProfile, OutputFormat, ProcessingConfig
from fuji_tcg_scanner.scanner import FujitsuScanner, MockScanner, ScannerConfig

console = Console()


def setup_logging(level: str = "INFO") -> None:
    """Configure logging with rich handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def print_banner() -> None:
    """Print application banner."""
    banner = """
╔═══════════════════════════════════════════════╗
║     🎴 Fuji TCG Scanner v{version:<10}       ║
║     High-Quality TCG Card Scanning            ║
║     For Fujitsu fi-6140z                      ║
╚═══════════════════════════════════════════════╝
""".format(version=__version__)
    console.print(Panel(banner, style="bold blue"))


def display_result(result: BatchResult) -> None:
    """Display batch processing results."""
    table = Table(title="Scan Results", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Scans", str(result.total_scans))
    table.add_row("Cards Detected", str(result.total_cards))
    table.add_row("Successfully Processed", str(result.successful_cards))
    table.add_row("Failed", str(result.failed_cards))
    table.add_row("Success Rate", f"{result.success_rate:.1f}%")
    table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    table.add_row("Output Files", str(len(result.output_files)))

    console.print(table)

    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for error in result.errors:
            console.print(f"  • {error}")

    if result.output_files:
        console.print(f"\n[green]Output saved to:[/green] {result.output_files[0].parent}")


@click.group()
@click.version_option(version=__version__)
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """
    Fuji TCG Scanner - High-quality TCG card scanning for Fujitsu fi-6140z.

    Scan and process Trading Card Game cards with optimized settings
    for color accuracy, sharpness, and detail preservation.
    """
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    setup_logging("DEBUG" if debug else "INFO")


@main.command()
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=Path("./output"),
    help="Output directory for scanned images",
)
@click.option(
    "--format", "-f",
    type=click.Choice(["png", "jpeg", "tiff", "webp"]),
    default="png",
    help="Output image format",
)
@click.option(
    "--resolution", "-r",
    type=int,
    default=600,
    help="Scan resolution in DPI (300-600 recommended)",
)
@click.option(
    "--preset", "-p",
    type=str,
    default=None,
    help="Use a saved preset (archival, sharing, pokemon, mtg, grading)",
)
@click.option(
    "--no-crop",
    is_flag=True,
    help="Disable automatic card detection and cropping",
)
@click.option(
    "--no-process",
    is_flag=True,
    help="Disable image processing (save raw scan)",
)
@click.option(
    "--mock",
    is_flag=True,
    help="Use mock scanner for testing",
)
@click.pass_context
def scan(
    ctx: click.Context,
    output: Path,
    format: str,
    resolution: int,
    preset: Optional[str],
    no_crop: bool,
    no_process: bool,
    mock: bool,
) -> None:
    """
    Scan a single TCG card from the flatbed.

    Place the card face-down on the scanner and run this command.
    The card will be automatically detected, cropped, and processed.
    """
    print_banner()

    # Load configuration
    config_manager = load_config()

    # Apply preset if specified
    if preset:
        if not config_manager.apply_preset(preset):
            console.print(f"[yellow]Preset '{preset}' not found, using defaults[/yellow]")
            config_manager.create_default_presets()
            config_manager.apply_preset(preset)

    # Create batch config
    batch_config = BatchConfig(
        output_dir=output,
        output_format=OutputFormat(format),
        auto_crop=not no_crop,
        process_images=not no_process,
        mock_mode=mock,
    )

    # Override with CLI options
    scanner_config = config_manager.get_scanner_config()
    scanner_config.resolution = resolution

    console.print(f"[cyan]Resolution:[/cyan] {resolution} DPI")
    console.print(f"[cyan]Output:[/cyan] {output}")
    console.print(f"[cyan]Format:[/cyan] {format.upper()}")

    if mock:
        console.print("[yellow]Running in mock mode (no real scanner)[/yellow]")

    # Confirm scan
    if not mock:
        console.print("\n[bold]Place card face-down on scanner glass.[/bold]")
        if not Confirm.ask("Ready to scan?"):
            console.print("[yellow]Scan cancelled[/yellow]")
            return

    # Perform scan
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=None)

        processor = BatchProcessor(
            batch_config=batch_config,
            scanner_config=scanner_config,
            processing_config=config_manager.get_processing_config(),
        )

        def update_progress(current: int, total: int, message: str) -> None:
            progress.update(task, description=message)

        processor.set_progress_callback(update_progress)
        result = processor.scan_and_process()

    display_result(result)


@main.command()
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=Path("./output"),
    help="Output directory",
)
@click.option(
    "--max-pages", "-n",
    type=int,
    default=0,
    help="Maximum pages to scan (0 = until ADF empty)",
)
@click.option(
    "--preset", "-p",
    type=str,
    default=None,
    help="Use a saved preset",
)
@click.option(
    "--mock",
    is_flag=True,
    help="Use mock scanner for testing",
)
@click.pass_context
def batch(
    ctx: click.Context,
    output: Path,
    max_pages: int,
    preset: Optional[str],
    mock: bool,
) -> None:
    """
    Batch scan multiple cards through the ADF.

    Load cards into the Automatic Document Feeder and run this command.
    Each page will be scanned, and cards will be automatically detected.
    """
    print_banner()

    config_manager = load_config()

    if preset:
        config_manager.apply_preset(preset)

    batch_config = BatchConfig(
        output_dir=output,
        use_adf=True,
        max_pages=max_pages,
        mock_mode=mock,
    )

    console.print(f"[cyan]Output:[/cyan] {output}")
    console.print(f"[cyan]Max pages:[/cyan] {'unlimited' if max_pages == 0 else max_pages}")

    if mock:
        console.print("[yellow]Running in mock mode[/yellow]")
    else:
        console.print("\n[bold]Load cards into the ADF.[/bold]")
        if not Confirm.ask("Ready to start batch scan?"):
            console.print("[yellow]Batch scan cancelled[/yellow]")
            return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Batch scanning...", total=max_pages if max_pages > 0 else 100)

        processor = BatchProcessor(
            batch_config=batch_config,
            scanner_config=config_manager.get_scanner_config(),
            processing_config=config_manager.get_processing_config(),
        )

        def update_progress(current: int, total: int, message: str) -> None:
            progress.update(task, completed=current, description=message)

        processor.set_progress_callback(update_progress)
        result = processor.scan_and_process()

    display_result(result)


@main.command()
@click.argument("images", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=Path("./output"),
    help="Output directory",
)
@click.option(
    "--preset", "-p",
    type=str,
    default=None,
    help="Use a saved preset",
)
@click.pass_context
def process(
    ctx: click.Context,
    images: tuple[Path, ...],
    output: Path,
    preset: Optional[str],
) -> None:
    """
    Process existing image files.

    Detect and extract cards from previously scanned images.

    Example: tcg-scanner process scan1.png scan2.png -o ./processed
    """
    if not images:
        console.print("[red]No images specified[/red]")
        return

    print_banner()

    config_manager = load_config()

    if preset:
        config_manager.apply_preset(preset)

    batch_config = BatchConfig(output_dir=output)

    console.print(f"[cyan]Processing {len(images)} image(s)[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=len(images))

        processor = BatchProcessor(
            batch_config=batch_config,
            processing_config=config_manager.get_processing_config(),
        )

        def update_progress(current: int, total: int, message: str) -> None:
            progress.update(task, completed=current, description=message)

        processor.set_progress_callback(update_progress)
        result = processor.process_existing_images(list(images))

    display_result(result)


@main.command()
@click.pass_context
def devices(ctx: click.Context) -> None:
    """
    List available scanner devices.

    Shows all SANE-compatible scanners detected on the system.
    """
    console.print("[cyan]Searching for scanners...[/cyan]")

    try:
        scanner = FujitsuScanner()
        devices = scanner.list_devices()

        if not devices:
            console.print("[yellow]No scanners found[/yellow]")
            console.print("\nTroubleshooting tips:")
            console.print("  1. Ensure scanner is connected and powered on")
            console.print("  2. Install SANE drivers: sudo apt install sane sane-utils")
            console.print("  3. Check permissions: sudo usermod -a -G scanner $USER")
            return

        table = Table(title="Available Scanners")
        table.add_column("Device", style="cyan")
        table.add_column("Vendor", style="green")
        table.add_column("Model", style="yellow")
        table.add_column("Type")

        for device in devices:
            name, vendor, model, dev_type = device
            table.add_row(name, vendor, model, dev_type)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@main.command()
@click.option("--mock", is_flag=True, help="Use mock scanner")
@click.pass_context
def preview(ctx: click.Context, mock: bool) -> None:
    """
    Perform a quick preview scan.

    Low-resolution scan to verify card placement before full scan.
    """
    console.print("[cyan]Performing preview scan...[/cyan]")

    try:
        scanner: FujitsuScanner
        if mock:
            scanner = MockScanner()
        else:
            scanner = FujitsuScanner()

        with scanner:
            result = scanner.preview(resolution=75)
            output_path = Path("./preview.png")
            result.save(output_path)
            console.print(f"[green]Preview saved to:[/green] {output_path}")
            console.print(f"[cyan]Size:[/cyan] {result.width}x{result.height}")

    except Exception as e:
        console.print(f"[red]Preview failed: {e}[/red]")


@main.group()
def preset() -> None:
    """Manage scanning presets."""
    pass


@preset.command("list")
def preset_list() -> None:
    """List available presets."""
    config_manager = load_config()
    config_manager.create_default_presets()

    table = Table(title="Available Presets")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Resolution")
    table.add_column("Format")

    for name, p in config_manager.config.presets.items():
        active = " [green]*[/green]" if name == config_manager.config.active_preset else ""
        table.add_row(
            f"{name}{active}",
            p.description,
            f"{p.scanner.resolution} DPI",
            p.output.format.upper(),
        )

    console.print(table)


@preset.command("show")
@click.argument("name")
def preset_show(name: str) -> None:
    """Show details of a preset."""
    config_manager = load_config()
    p = config_manager.get_preset(name)

    if p is None:
        console.print(f"[red]Preset '{name}' not found[/red]")
        return

    console.print(Panel(f"[bold]{p.name}[/bold]\n{p.description}", title="Preset Details"))

    # Scanner settings
    table = Table(title="Scanner Settings")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Resolution", f"{p.scanner.resolution} DPI")
    table.add_row("Mode", p.scanner.mode)
    table.add_row("Brightness", str(p.scanner.brightness))
    table.add_row("Contrast", str(p.scanner.contrast))
    console.print(table)

    # Processing settings
    table = Table(title="Processing Settings")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Brightness", f"{p.processing.brightness:.2f}")
    table.add_row("Contrast", f"{p.processing.contrast:.2f}")
    table.add_row("Saturation", f"{p.processing.saturation:.2f}")
    table.add_row("Sharpness", f"{p.processing.sharpness:.2f}")
    table.add_row("Color Profile", p.processing.color_profile)
    table.add_row("White Balance", "Yes" if p.processing.white_balance else "No")
    table.add_row("Denoise", "Yes" if p.processing.denoise else "No")
    console.print(table)


@preset.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Preset description")
@click.option("--resolution", "-r", type=int, default=600)
@click.option("--format", "-f", type=click.Choice(["png", "jpeg", "tiff"]), default="png")
@click.option("--profile", type=click.Choice(["standard", "pokemon", "mtg", "yugioh", "vivid", "neutral"]), default="standard")
def preset_create(
    name: str,
    description: str,
    resolution: int,
    format: str,
    profile: str,
) -> None:
    """Create a new preset."""
    from fuji_tcg_scanner.config import ScannerSettings, ProcessingSettings, OutputSettings

    config_manager = load_config()

    new_preset = Preset(
        name=name,
        description=description,
        scanner=ScannerSettings(resolution=resolution),
        processing=ProcessingSettings(color_profile=profile),
        output=OutputSettings(format=format),
    )

    config_manager.save_preset(new_preset)
    console.print(f"[green]Created preset:[/green] {name}")


@preset.command("delete")
@click.argument("name")
def preset_delete(name: str) -> None:
    """Delete a preset."""
    config_manager = load_config()

    if name in ["archival", "sharing", "pokemon", "mtg", "grading"]:
        console.print(f"[yellow]Cannot delete built-in preset:[/yellow] {name}")
        return

    if config_manager.delete_preset(name):
        console.print(f"[green]Deleted preset:[/green] {name}")
    else:
        console.print(f"[red]Preset not found:[/red] {name}")


@main.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Show current configuration."""
    config_manager = load_config()
    cfg = config_manager.config

    console.print(Panel("[bold]Current Configuration[/bold]"))

    # Scanner
    table = Table(title="Scanner")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Resolution", f"{cfg.scanner.resolution} DPI")
    table.add_row("Mode", cfg.scanner.mode)
    table.add_row("Source", cfg.scanner.source)
    table.add_row("Brightness", str(cfg.scanner.brightness))
    table.add_row("Contrast", str(cfg.scanner.contrast))
    console.print(table)

    # Output
    table = Table(title="Output")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Directory", cfg.output.directory)
    table.add_row("Format", cfg.output.format.upper())
    table.add_row("JPEG Quality", str(cfg.output.jpeg_quality))
    table.add_row("Thumbnails", "Yes" if cfg.output.create_thumbnails else "No")
    console.print(table)

    console.print(f"\n[cyan]Config file:[/cyan] {config_manager.config_path}")


@main.command()
def init() -> None:
    """Initialize configuration with default presets."""
    config_manager = load_config()
    config_manager.create_default_presets()
    console.print("[green]Configuration initialized with default presets[/green]")
    console.print(f"[cyan]Config file:[/cyan] {config_manager.config_path}")


if __name__ == "__main__":
    main()
