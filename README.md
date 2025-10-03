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

### Introduction

```text
Required Argument
IMAGE_DIRECTORY
The directory path containing images to watermark.

Optional Arguments
--font-size, -s
Font size for watermark (default: 80)

--color, -c
Text color for watermark (default: red)

--position, -p
Watermark position on the image
Available values: top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right
Default: bottom-right

--use-file-date
Use file modification date as watermark when EXIF date is not available

--default-date
Use the specified default date (format: YYYY-MM-DD) when neither EXIF nor file date is available
```

### How to run ?

```bash
uv run watermark_cli.py test --font-size 100 --color gray --position center 
```
