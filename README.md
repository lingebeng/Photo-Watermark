# Photo Watermark

<div align="center">

[![English](https://img.shields.io/badge/lang-English-blue)](README.md)
[![中文](https://img.shields.io/badge/lang-中文-red)](README_CN.md)

</div>

## 📸 Project Overview

A tool for adding watermarks to photos.

## 🛠 Installation

```bash
# Install dependencies
uv sync
source .venv/bin/activate

# Install git hooks
pre-commit install
```

## 📝 Development Notes

### dev-00 Requirements

Complete a command-line program.

Users input an image file path.

Read EXIF information of all files in that path, extract shooting time information, select year, month, and day as watermark.

Users can set font size, color, and position on the image (e.g., top-left, center, bottom-right).

The program draws text watermarks on images and saves them as new image files in a new directory named `<original_directory>_watermark` as a subdirectory of the original directory.
