#!/usr/bin/env python3
"""
Photo Watermark Tool - Add date watermarks to photos based on EXIF data
"""

import os
from pathlib import Path
from typing import Optional, Tuple

import piexif
import typer
from PIL import Image, ImageDraw, ImageFont


def extract_date_from_exif(
    image_path: Path, use_file_date: bool = False, default_date: str = None
) -> Optional[str]:
    """Extract date from EXIF data and return as YYYY-MM-DD format."""
    try:
        image = Image.open(image_path)

        # Only try to read EXIF for JPEG files
        if image_path.suffix.lower() in [".jpg", ".jpeg"]:
            try:
                exif_dict = piexif.load(image.info.get("exif", b""))

                # Try to get the date from EXIF
                date_taken = None
                if piexif.ExifIFD.DateTimeOriginal in exif_dict.get("Exif", {}):
                    date_taken = exif_dict["Exif"][
                        piexif.ExifIFD.DateTimeOriginal
                    ].decode("utf-8")
                elif piexif.ImageIFD.DateTime in exif_dict.get("0th", {}):
                    date_taken = exif_dict["0th"][piexif.ImageIFD.DateTime].decode(
                        "utf-8"
                    )

                if date_taken:
                    # Convert from "YYYY:MM:DD HH:MM:SS" to "YYYY-MM-DD"
                    date_part = date_taken.split(" ")[0]
                    return date_part.replace(":", "-")
            except Exception:
                pass  # Fall through to alternative methods

        # If EXIF fails or not available, try alternative methods
        if use_file_date:
            # Use file modification time
            import datetime

            mtime = image_path.stat().st_mtime
            date_obj = datetime.datetime.fromtimestamp(mtime)
            return date_obj.strftime("%Y-%m-%d")

        if default_date:
            return default_date

    except Exception as e:
        typer.echo(f"Error reading image {image_path}: {e}", err=True)

    return None


def get_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Get a font for watermark text."""
    try:
        # Try to use a system font
        font_paths = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, font_size)

        # Fallback to default font
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def get_watermark_position(
    image_size: Tuple[int, int], text_size: Tuple[int, int], position: str
) -> Tuple[int, int]:
    """Calculate watermark position based on image size and position preference."""
    img_width, img_height = image_size
    text_width, text_height = text_size
    margin = 20

    positions = {
        "top-left": (margin, margin),
        "top-center": ((img_width - text_width) // 2, margin),
        "top-right": (img_width - text_width - margin, margin),
        "center-left": (margin, (img_height - text_height) // 2),
        "center": ((img_width - text_width) // 2, (img_height - text_height) // 2),
        "center-right": (
            img_width - text_width - margin,
            (img_height - text_height) // 2,
        ),
        "bottom-left": (margin, img_height - text_height - margin),
        "bottom-center": (
            (img_width - text_width) // 2,
            img_height - text_height - margin,
        ),
        "bottom-right": (
            img_width - text_width - margin,
            img_height - text_height - margin,
        ),
    }

    return positions.get(position, positions["bottom-right"])


def add_watermark_to_image(
    image_path: Path,
    output_path: Path,
    watermark_text: str,
    font_size: int,
    color: str,
    position: str,
) -> bool:
    """Add watermark to a single image."""
    try:
        # Open the image
        image = Image.open(image_path)

        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Create a drawing context
        draw = ImageDraw.Draw(image)

        # Get font
        font = get_font(font_size)

        # Calculate text size
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_size = (bbox[2] - bbox[0], bbox[3] - bbox[1])

        # Get position
        pos = get_watermark_position(image.size, text_size, position)

        # Add semi-transparent background for better readability
        bg_margin = 100
        bg_bbox = (
            pos[0] - bg_margin,
            pos[1] - bg_margin,
            pos[0] + text_size[0] + bg_margin,
            pos[1] + text_size[1] + bg_margin,
        )

        # Create a semi-transparent overlay
        overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Draw background rectangle
        overlay_draw.rectangle(bg_bbox, fill=(0, 0, 0, 128))

        # Draw text
        overlay_draw.text(pos, watermark_text, font=font, fill=color)

        # Composite the overlay onto the original image
        image = Image.alpha_composite(image.convert("RGBA"), overlay)
        image = image.convert("RGB")

        # Save the result
        image.save(output_path, quality=95)
        return True

    except Exception as e:
        typer.echo(f"Error processing {image_path}: {e}", err=True)
        return False


def main(
    image_directory: str = typer.Argument(
        ..., help="Directory containing images to watermark"
    ),
    font_size: int = typer.Option(
        80, "--font-size", "-s", help="Font size for watermark"
    ),
    color: str = typer.Option("red", "--color", "-c", help="Text color for watermark"),
    position: str = typer.Option(
        "bottom-right",
        "--position",
        "-p",
        help="Watermark position (top-left, center, bottom-right, etc.)",
    ),
    use_file_date: bool = typer.Option(
        False,
        "--use-file-date",
        help="Use file modification date when EXIF is not available",
    ),
    default_date: str = typer.Option(
        None,
        "--default-date",
        help="Default date to use when no EXIF or file date (YYYY-MM-DD format)",
    ),
):
    """
    Add date watermarks to photos based on EXIF information.

    Reads all images in the specified directory, extracts date from EXIF data,
    and adds it as a watermark. Processed images are saved in a '_watermark' subdirectory.
    """

    # Validate input directory
    input_path = Path(image_directory)
    if not input_path.exists():
        typer.echo(f"Error: Directory '{image_directory}' does not exist.", err=True)
        raise typer.Exit(1)

    if not input_path.is_dir():
        typer.echo(f"Error: '{image_directory}' is not a directory.", err=True)
        raise typer.Exit(1)

    # Create output directory
    output_dir = input_path / f"{input_path.name}_watermark"
    output_dir.mkdir(exist_ok=True)

    # Supported image extensions
    image_extensions = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}

    # Find all image files
    image_files = []
    for ext in image_extensions:
        image_files.extend(input_path.glob(f"*{ext}"))
        image_files.extend(input_path.glob(f"*{ext.upper()}"))

    if not image_files:
        typer.echo(f"No image files found in '{image_directory}'.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(image_files)} image(s) to process...")
    typer.echo(f"Output directory: {output_dir}")

    processed_count = 0
    skipped_count = 0

    for image_file in image_files:
        typer.echo(f"Processing: {image_file.name}")

        # Extract date from EXIF, file date, or use default
        date_text = extract_date_from_exif(image_file, use_file_date, default_date)

        if not date_text:
            typer.echo(f"  ⚠️  No date available, skipping {image_file.name}")
            typer.echo("      Try using --use-file-date or --default-date options")
            skipped_count += 1
            continue

        # Create output filename
        output_file = output_dir / image_file.name

        # Add watermark
        if add_watermark_to_image(
            image_file, output_file, date_text, font_size, color, position
        ):
            typer.echo(f"  ✅ Watermarked with date: {date_text}")
            processed_count += 1
        else:
            typer.echo(f"  ❌ Failed to process {image_file.name}")
            skipped_count += 1

    # Summary
    typer.echo("\n" + "=" * 50)
    typer.echo("Processing complete!")
    typer.echo(f"Successfully processed: {processed_count} images")
    typer.echo(f"Skipped: {skipped_count} images")
    typer.echo(f"Output saved to: {output_dir}")


if __name__ == "__main__":
    typer.run(main)
