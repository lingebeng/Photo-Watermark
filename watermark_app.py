"""Streamlit Photo Watermark Application

Implements:
 - Batch image import (files or folder) with thumbnail list
 - Text & image watermark (all advanced options)
 - Drag & drop positioning (using streamlit-drawable-canvas)
 - 9-grid preset positioning buttons
 - Rotation, opacity, scaling
 - Outline / shadow for text
 - JPEG / PNG export with naming rules, quality, resizing
 - Template save/load/delete with auto-load last session
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from streamlit_drawable_canvas import st_canvas

# ---------------------------- Configuration ---------------------------- #
APP_STORAGE_DIR = Path.home() / ".photo_watermark_app"
TEMPLATE_FILE = APP_STORAGE_DIR / "templates.json"
LAST_STATE_FILE = APP_STORAGE_DIR / "last_state.json"
SUPPORTED_IMPORT_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
DEFAULT_FONT_CANDIDATES = [
    # Common Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    # Windows (best effort typical paths)
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def ensure_storage_dir() -> None:
    APP_STORAGE_DIR.mkdir(exist_ok=True, parents=True)


# ---------------------------- Data Models ---------------------------- #
@dataclass
class TextStyle:
    font_path: str
    size: int
    bold: bool = False
    italic: bool = False  # Placeholder (true italic requires font selection)
    fill_rgba: Tuple[int, int, int, int] = (255, 0, 0, 255)
    outline: bool = False
    outline_width: int = 2
    outline_color_rgba: Tuple[int, int, int, int] = (0, 0, 0, 255)
    shadow: bool = False
    shadow_offset: Tuple[int, int] = (2, 2)
    shadow_color_rgba: Tuple[int, int, int, int] = (0, 0, 0, 128)


@dataclass
class ImageWatermarkConfig:
    enabled: bool = False
    image_b64: Optional[str] = None  # Stored as base64 png for persistence
    scale_percent: int = 50  # relative scaling to original watermark image (used when scale_mode='percent')
    opacity: int = 100  # 0-100
    scale_mode: str = "percent"  # 'percent' | 'width'
    width_px: int = 200  # used when scale_mode='width'


@dataclass
class TextWatermarkConfig:
    enabled: bool = True
    text: str = "Sample Watermark"
    opacity: int = 100
    style: TextStyle = field(
        default_factory=lambda: TextStyle(font_path=find_default_font(), size=48)
    )


@dataclass
class WatermarkTemplate:
    name: str
    text_cfg: TextWatermarkConfig
    image_cfg: ImageWatermarkConfig
    position: Tuple[float, float]  # normalized (0..1)
    rotation_deg: float
    output_format: str
    jpeg_quality: int
    resize_mode: str
    resize_value: int

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "text_cfg": json.loads(json.dumps(asdict(self.text_cfg))),
            "image_cfg": json.loads(json.dumps(asdict(self.image_cfg))),
            "position": self.position,
            "rotation_deg": self.rotation_deg,
            "output_format": self.output_format,
            "jpeg_quality": self.jpeg_quality,
            "resize_mode": self.resize_mode,
            "resize_value": self.resize_value,
        }

    @staticmethod
    def from_dict(d: Dict) -> "WatermarkTemplate":
        text_cfg_raw = d["text_cfg"]
        style_raw = text_cfg_raw.get("style", {})
        style = TextStyle(**style_raw)
        text_cfg = TextWatermarkConfig(
            enabled=text_cfg_raw.get("enabled", True),
            text=text_cfg_raw.get("text", "Sample Watermark"),
            opacity=text_cfg_raw.get("opacity", 100),
            style=style,
        )
        image_cfg_raw = d["image_cfg"]
        image_cfg = ImageWatermarkConfig(**image_cfg_raw)
        return WatermarkTemplate(
            name=d["name"],
            text_cfg=text_cfg,
            image_cfg=image_cfg,
            position=tuple(d.get("position", (0.5, 0.5))),
            rotation_deg=d.get("rotation_deg", 0.0),
            output_format=d.get("output_format", "PNG"),
            jpeg_quality=d.get("jpeg_quality", 90),
            resize_mode=d.get("resize_mode", "none"),
            resize_value=d.get("resize_value", 0),
        )


# ---------------------------- Font Helpers ---------------------------- #
def find_default_font() -> str:
    for p in DEFAULT_FONT_CANDIDATES:
        if Path(p).exists():
            return p
    # Fallback: try to locate any TTF under common dirs
    for root in ["/usr/share/fonts", "/System/Library/Fonts", "C:/Windows/Fonts"]:
        if Path(root).exists():
            for path in Path(root).rglob("*.ttf"):
                return str(path)
    return ""  # PIL will fallback to default


def find_cjk_font(limit_search: int = 200) -> str:
    """Best-effort locate a font that contains common CJK characters.

    We test a small sample of Chinese characters and pick the first font that can render all.
    """
    sample_chars = "测试中文水印示例123"  # Representative sample
    search_dirs = [
        "/usr/share/fonts",
        "/System/Library/Fonts",
        "/Library/Fonts",
        "C:/Windows/Fonts",
    ]
    checked = 0
    for root in search_dirs:
        p = Path(root)
        if not p.exists():
            continue
        for f in p.rglob("*.ttf"):
            if f.name.startswith("."):
                continue
            try:
                font = ImageFont.truetype(str(f), size=32)
                # crude check: getsize each char; if width>0 for all we assume supported
                if all(font.getlength(ch) > 0 for ch in sample_chars):
                    return str(f)
            except Exception:
                pass
            checked += 1
            if checked >= limit_search:
                break
        if checked >= limit_search:
            break
    return ""


def load_font(style: TextStyle) -> ImageFont.FreeTypeFont:
    size = max(4, style.size)
    try:
        if style.font_path and Path(style.font_path).exists():
            return ImageFont.truetype(style.font_path, size=size)
    except Exception:
        pass
    return ImageFont.load_default()


_FONT_CACHE: Optional[Dict[str, str]] = None


def list_system_fonts(limit: int = 120) -> Dict[str, str]:
    """Return a mapping of display name -> path for TTF fonts (cached)."""
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE
    paths = []
    search_dirs = [
        "/usr/share/fonts",
        "/System/Library/Fonts",
        "/Library/Fonts",
        "C:/Windows/Fonts",
    ]
    seen = set()
    for root in search_dirs:
        p = Path(root)
        if not p.exists():
            continue
        for f in p.rglob("*.ttf"):
            if f.name.startswith("."):
                continue
            name = f.stem
            if name not in seen:
                paths.append((name, str(f)))
                seen.add(name)
            if len(paths) >= limit:
                break
        if len(paths) >= limit:
            break
    _FONT_CACHE = {n: p for n, p in sorted(paths, key=lambda x: x[0].lower())}
    return _FONT_CACHE


# ---------------------------- Color Helpers ---------------------------- #
def safe_color_hex(rgb_like) -> str:
    """Return #RRGGBB from a 3-seq; fallback to #FF0000 on error.

    Streamlit color_picker requires a string; ensure ints 0-255.
    """
    try:
        r, g, b = rgb_like[:3]
        r = int(max(0, min(255, r)))
        g = int(max(0, min(255, g)))
        b = int(max(0, min(255, b)))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#ff0000"


# ---------------------------- Image Utilities ---------------------------- #
def load_image_bytes(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


def image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def encode_image_to_b64(img: Image.Image) -> str:
    return base64.b64encode(image_to_bytes(img, "PNG")).decode()


def decode_image_from_b64(b64_str: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))


# ---------------------------- Watermark Rendering ---------------------------- #
def render_text_watermark(cfg: TextWatermarkConfig) -> Image.Image:
    text = cfg.text
    font = load_font(cfg.style)
    # If Chinese chars present but font probably lacks glyphs (fallback default width heuristic)
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        # Detect missing char by measuring a known CJK char
        test_char = "测"
        try:
            missing = font.getlength(test_char) <= 0
        except Exception:
            missing = False
        if missing:
            cjk_font = find_cjk_font()
            if cjk_font:
                cfg.style.font_path = cjk_font
                font = load_font(cfg.style)
                # Record notice for UI once
                st.session_state._cjk_notice = (
                    f"已自动切换中文字体: {Path(cjk_font).name}"
                )
            else:
                st.session_state._cjk_notice = (
                    "未找到中文字体，请安装支持中文的 TTF 字体"
                )
    # measure text box (bbox already includes glyph extents for this font)
    dummy = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(dummy)
    bbox = d.textbbox((0, 0), text, font=font)
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0

    # Directional padding so large outline / shadow / bold 不会裁剪
    base_pad = 6
    ow = cfg.style.outline_width if cfg.style.outline else 0
    sox, soy = cfg.style.shadow_offset if cfg.style.shadow else (0, 0)
    bold_extra = 1 if cfg.style.bold else 0
    # Left/right
    left_pad = base_pad + ow + (abs(sox) if sox < 0 else 0)
    right_pad = base_pad + ow + (sox if sox > 0 else 0) + bold_extra
    top_pad = base_pad + ow + (abs(soy) if soy < 0 else 0)
    bottom_pad = base_pad + ow + (soy if soy > 0 else 0) + bold_extra
    # Add small safety pad to prevent edge clipping after fabric scaling
    safety = 2
    canvas_w = w + left_pad + right_pad + safety
    canvas_h = h + top_pad + bottom_pad + safety
    # Safety clamp to avoid zero/negative
    canvas_w = max(2, canvas_w)
    canvas_h = max(2, canvas_h)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # Shift drawing origin by negative bbox offsets so ascenders / left bearings aren't clipped
    tx, ty = left_pad - x0, top_pad - y0
    # shadow
    if cfg.style.shadow:
        sx, sy = cfg.style.shadow_offset
        draw.text(
            (tx + sx, ty + sy),
            text,
            font=font,
            fill=cfg.style.shadow_color_rgba,
        )
    # outline
    if cfg.style.outline:
        ow_iter = max(1, cfg.style.outline_width)
        for ox in range(-ow_iter, ow_iter + 1):
            for oy in range(-ow_iter, ow_iter + 1):
                if ox == 0 and oy == 0:
                    continue
                draw.text(
                    (tx + ox, ty + oy),
                    text,
                    font=font,
                    fill=cfg.style.outline_color_rgba,
                )
    # main text
    r, g, b, a = cfg.style.fill_rgba
    alpha = int(a * (cfg.opacity / 100.0))
    if cfg.style.bold:
        # draw multiple offsets for pseudo bold
        for ox in (0, 1):
            for oy in (0, 1):
                draw.text((tx + ox, ty + oy), text, font=font, fill=(r, g, b, alpha))
    else:
        draw.text((tx, ty), text, font=font, fill=(r, g, b, alpha))

    if cfg.style.italic:
        # shear transform (italic effect)
        shear = 0.3
        w0, h0 = canvas.size
        new_w = int(w0 + h0 * shear)
        italic_img = Image.new("RGBA", (new_w, h0), (0, 0, 0, 0))
        italic_img.paste(canvas, (0, 0))
        italic_img = italic_img.transform(
            (new_w, h0),
            Image.Transform.AFFINE,
            (1, shear, 0, 0, 1, 0),
            Image.Resampling.BICUBIC,
        )
        canvas = italic_img
    return canvas


def apply_opacity(img: Image.Image, opacity: int) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.split()[3]
    factor = max(0, min(100, opacity)) / 100.0
    alpha = alpha.point(lambda p: int(p * factor))
    img.putalpha(alpha)
    return img


def build_watermark_layer(
    base_image: Image.Image,
    text_cfg: TextWatermarkConfig,
    image_cfg: ImageWatermarkConfig,
    position_norm: Tuple[float, float],
    rotation_deg: float,
) -> Image.Image:
    W, H = base_image.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    composed = compute_composed_watermark(text_cfg, image_cfg)
    if composed is None:
        return layer

    # rotation
    if rotation_deg % 360 != 0:
        composed = composed.rotate(rotation_deg, expand=True)

    cx = int(position_norm[0] * W)
    cy = int(position_norm[1] * H)
    x = cx - composed.width // 2
    y = cy - composed.height // 2
    layer.alpha_composite(composed, (x, y))
    return layer


def composite_preview(base: Image.Image, *layers: Image.Image) -> Image.Image:
    out = base.convert("RGBA").copy()
    for layer_img in layers:
        out.alpha_composite(layer_img)
    return out


def _get_thumbnail(data: bytes, height: int = 100) -> Image.Image:
    """Return a thumbnail with fixed height (default 100px) and proportional width.

    宽度自适应保持比例；使用 LANCZOS。若图片加载失败则返回占位图。若原图高度为 0 则直接返回。
    """
    try:
        img = load_image_bytes(data)
        w, h = img.size
        if w <= 0 or h <= 0:
            return img
        target_h = max(1, height)
        ratio = target_h / h
        target_w = max(1, int(w * ratio))
        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new("RGBA", (height, height), (200, 200, 200, 255))


def compute_composed_watermark(
    text_cfg: TextWatermarkConfig, image_cfg: ImageWatermarkConfig
) -> Optional[Image.Image]:
    """Return watermark image (text + optional image) before rotation & placement."""
    composed: Optional[Image.Image] = None
    if text_cfg.enabled and text_cfg.text.strip():
        composed = render_text_watermark(text_cfg)
    if image_cfg.enabled and image_cfg.image_b64:
        try:
            wm_img = decode_image_from_b64(image_cfg.image_b64).convert("RGBA")
            if image_cfg.scale_mode == "width":
                target_w = max(5, min(4000, image_cfg.width_px))
                ratio = target_w / wm_img.width
                nw = target_w
                nh = max(1, int(wm_img.height * ratio))
            else:
                scale = max(5, min(400, image_cfg.scale_percent)) / 100.0
                nw = max(1, int(wm_img.width * scale))
                nh = max(1, int(wm_img.height * scale))
            wm_img = wm_img.resize((nw, nh), Image.Resampling.LANCZOS)
            wm_img = apply_opacity(wm_img, image_cfg.opacity)
            if composed:
                cw = max(composed.width, wm_img.width)
                ch = max(composed.height, wm_img.height)
                group = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                group.paste(
                    wm_img,
                    ((cw - wm_img.width) // 2, (ch - wm_img.height) // 2),
                    wm_img,
                )
                group.alpha_composite(
                    composed,
                    ((cw - composed.width) // 2, (ch - composed.height) // 2),
                )
                composed = group
            else:
                composed = wm_img
        except Exception:
            pass
    return composed


# ---------------------------- Template Persistence ---------------------------- #
def load_templates() -> Dict[str, Dict]:
    ensure_storage_dir()
    if TEMPLATE_FILE.exists():
        try:
            return json.loads(TEMPLATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_templates(templates: Dict[str, Dict]) -> None:
    ensure_storage_dir()
    TEMPLATE_FILE.write_text(json.dumps(templates, indent=2))


def load_last_state() -> Dict:
    ensure_storage_dir()
    if LAST_STATE_FILE.exists():
        try:
            return json.loads(LAST_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_last_state(state: Dict) -> None:
    ensure_storage_dir()
    LAST_STATE_FILE.write_text(json.dumps(state))


# ---------------------------- Position Helpers ---------------------------- #
GRID_PRESETS = {
    "Top-Left": (0.05, 0.05),
    "Top-Center": (0.5, 0.05),
    "Top-Right": (0.95, 0.05),
    "Center-Left": (0.05, 0.5),
    "Center": (0.5, 0.5),
    "Center-Right": (0.95, 0.5),
    "Bottom-Left": (0.05, 0.95),
    "Bottom-Center": (0.5, 0.95),
    "Bottom-Right": (0.95, 0.95),
}


def clamp_norm(pos: Tuple[float, float]) -> Tuple[float, float]:
    return (min(0.999, max(0.001, pos[0])), min(0.999, max(0.001, pos[1])))


# ---------------------------- Export Logic ---------------------------- #
def export_image(
    base_img: Image.Image,
    wm_layer: Image.Image,
    output_path: Path,
    fmt: str,
    jpeg_quality: int = 90,
    resize_mode: str = "none",
    resize_value: int = 0,
    force_width: Optional[int] = None,
) -> None:
    img = composite_preview(base_img, wm_layer)
    # Resize
    if force_width is not None and force_width > 0:
        if force_width != img.width:
            ratio = force_width / img.width
            img = img.resize(
                (force_width, max(1, int(img.height * ratio))),
                Image.Resampling.LANCZOS,
            )
    elif resize_mode != "none" and resize_value > 0:
        if resize_mode == "width":
            w = resize_value
            ratio = w / img.width
            h = int(img.height * ratio)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
        elif resize_mode == "height":
            h = resize_value
            ratio = h / img.height
            w = int(img.width * ratio)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
        elif resize_mode == "percent":
            scale = resize_value / 100.0
            w = int(img.width * scale)
            h = int(img.height * scale)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
    params = {}
    if fmt.upper() == "JPEG":
        img = img.convert("RGB")
        params["quality"] = max(1, min(100, jpeg_quality))
    img.save(output_path, format=fmt.upper(), **params)


# ---------------------------- Streamlit UI ---------------------------- #
def init_session_state():  # idempotent
    if "images" not in st.session_state:
        st.session_state.images = []  # List[Dict{name, data(bytes)}]
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0
    if "position_norm" not in st.session_state:
        st.session_state.position_norm = (0.5, 0.5)
    # Absolute position in preview canvas pixels (center of watermark). Will be derived from position_norm on first layout pass.
    if "position_abs" not in st.session_state:
        st.session_state.position_abs = None
    if "rotation" not in st.session_state:
        st.session_state.rotation = 0.0
    if "text_cfg" not in st.session_state:
        st.session_state.text_cfg = TextWatermarkConfig()
    if "image_cfg" not in st.session_state:
        st.session_state.image_cfg = ImageWatermarkConfig()
    if "templates" not in st.session_state:
        st.session_state.templates = load_templates()
    if "output_settings" not in st.session_state:
        st.session_state.output_settings = {
            "format": "PNG",
            "jpeg_quality": 90,
            "naming_mode": "original",
            "prefix": "wm_",
            "suffix": "_watermarked",
            "resize_mode": "none",
            "resize_value": 0,
            "output_dir": str(Path.cwd() / "watermarked_output"),
        }
    if "preview_width" not in st.session_state:
        st.session_state.preview_width = 800  # default fixed width
    if "per_image_position" not in st.session_state:
        st.session_state.per_image_position = False
    if "image_positions" not in st.session_state:
        st.session_state.image_positions = {}  # name -> (x,y)
    # Download caches (in-memory) for browser download convenience
    if "_current_download_bytes" not in st.session_state:
        st.session_state._current_download_bytes = None
    if "_current_download_name" not in st.session_state:
        st.session_state._current_download_name = None
    if "_zip_export_bytes" not in st.session_state:
        st.session_state._zip_export_bytes = None
    if "_zip_export_name" not in st.session_state:
        st.session_state._zip_export_name = None


def sidebar_import_panel():
    st.sidebar.header("1. 导入图片 / Import")
    uploaded = st.sidebar.file_uploader(
        "选择或拖拽多张图片",
        type=[e[1:] for e in SUPPORTED_IMPORT_EXTS],
        accept_multiple_files=True,
    )
    added = 0
    if uploaded:
        for uf in uploaded:
            if any(img["name"] == uf.name for img in st.session_state.images):
                continue
            st.session_state.images.append({"name": uf.name, "data": uf.getvalue()})
            added += 1
    folder = st.sidebar.text_input("或输入文件夹路径 (Batch Folder)")
    recursive = st.sidebar.checkbox("递归包含子文件夹 / Recursive", value=False)
    if st.sidebar.button("加载文件夹 / Load Folder") and folder:
        p = Path(folder).expanduser()
        if p.exists() and p.is_dir():
            pattern_iter = (
                p.rglob("*") if recursive else p.iterdir()
            )  # include subfolders optionally
            new_files = 0
            for file in pattern_iter:
                try:
                    if not file.is_file():
                        continue
                    if file.suffix.lower() in SUPPORTED_IMPORT_EXTS:
                        if any(
                            img["name"] == file.name for img in st.session_state.images
                        ):
                            continue
                        st.session_state.images.append(
                            {"name": file.name, "data": file.read_bytes()}
                        )
                        new_files += 1
                except Exception:
                    continue
            if new_files:
                st.sidebar.success(f"已加载 {new_files} 张图片")
            else:
                st.sidebar.warning("未找到新的图片文件")
        else:
            st.sidebar.error("文件夹无效")
    if added:
        st.sidebar.success(f"新增 {added} 张图片")
    # Image list
    if st.session_state.images:
        names = [img["name"] for img in st.session_state.images]
        sel = st.sidebar.selectbox(
            "预览图片 / Preview",
            options=list(range(len(names))),
            format_func=lambda i: names[i],
            index=min(st.session_state.selected_index, len(names) - 1),
        )
        # Detect image change to optionally load per-image position
        if sel != st.session_state.selected_index:
            st.session_state.selected_index = sel
            if st.session_state.per_image_position:
                img_name = names[sel]
                # Prefer absolute position map
                abs_map = st.session_state.get("image_positions_abs", {})
                if img_name in abs_map:
                    st.session_state.position_abs = abs_map[img_name]
                    # derive normalized placeholder; real clamp happens in main_layout
                    # We'll compute canvas dims there.
                elif img_name in st.session_state.image_positions:
                    # legacy normalized
                    st.session_state.position_norm = st.session_state.image_positions[
                        img_name
                    ]
                    st.session_state.position_abs = None  # trigger derive
                else:
                    st.session_state.position_abs = None
                    st.session_state.position_norm = (0.5, 0.5)
        else:
            st.session_state.selected_index = sel
        # Management section: per-image delete & clear all
        with st.sidebar.expander("管理已导入图片 / Manage Imported"):
            to_delete = []
            for i, name in enumerate(names):
                cols = st.columns([6, 1])
                cols[0].markdown(f"`{i + 1}` {name}")
                if cols[1].button("🗑", key=f"del_img_{i}"):
                    to_delete.append(i)
            if to_delete:
                # Delete in reverse order to keep indices valid
                for idx_del in sorted(to_delete, reverse=True):
                    removed = st.session_state.images.pop(idx_del)
                    # Clean any stored per-image position
                    if "image_positions_abs" in st.session_state:
                        st.session_state.image_positions_abs.pop(removed["name"], None)
                    st.session_state.image_positions.pop(removed["name"], None)
                # Adjust selected index
                if st.session_state.images:
                    st.session_state.selected_index = min(
                        st.session_state.selected_index,
                        len(st.session_state.images) - 1,
                    )
                else:
                    st.session_state.selected_index = 0
                    st.session_state.position_abs = None
                # Rerun for UI refresh (Streamlit >=1.32 uses st.rerun)
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    getattr(st, "experimental_rerun", lambda: None)()
            st.markdown("---")
            if st.button("清空全部 / Clear All", key="clear_all_imgs"):
                st.session_state.images.clear()
                if "image_positions_abs" in st.session_state:
                    st.session_state.image_positions_abs.clear()
                st.session_state.image_positions.clear()
                st.session_state.selected_index = 0
                st.session_state.position_abs = None
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    getattr(st, "experimental_rerun", lambda: None)()
    else:
        st.sidebar.info("尚未导入图片")


def sidebar_text_watermark():
    st.sidebar.header("2. 文本水印 / Text")
    cfg: TextWatermarkConfig = st.session_state.text_cfg
    cfg.enabled = st.sidebar.checkbox("启用文本水印", value=cfg.enabled)
    if not cfg.enabled:
        return
    cfg.text = st.sidebar.text_input("文本内容", value=cfg.text)
    cfg.style.size = st.sidebar.slider(
        "字号", 8, 300, cfg.style.size, key="tw_font_size"
    )
    # Normalize style.fill_rgba to tuple of ints (some JSON reload may give list)
    if not isinstance(cfg.style.fill_rgba, tuple):
        try:
            cfg.style.fill_rgba = tuple(cfg.style.fill_rgba)  # type: ignore
        except Exception:
            cfg.style.fill_rgba = (255, 0, 0, 255)
    color = st.sidebar.color_picker("颜色", value=safe_color_hex(cfg.style.fill_rgba))
    # parse color hex
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        cfg.style.fill_rgba = (r, g, b, 255)
    except Exception:
        pass
    cfg.opacity = st.sidebar.slider("透明度 %", 0, 100, cfg.opacity, key="tw_opacity")
    with st.sidebar.expander("高级样式 / Advanced"):
        fonts = list_system_fonts()
        if fonts:
            current_font_name = next(
                (n for n, p in fonts.items() if p == cfg.style.font_path), None
            )
            font_choice = st.selectbox(
                "字体 / Font",
                ["(默认)"] + list(fonts.keys()),
                index=(
                    0
                    if current_font_name is None
                    else (1 + list(fonts.keys()).index(current_font_name))
                ),
            )
            if font_choice != "(默认)":
                cfg.style.font_path = fonts[font_choice]
        bold_val = st.checkbox("加粗 / Bold", value=cfg.style.bold)
        italic_val = st.checkbox("斜体 / Italic", value=cfg.style.italic)
        cfg.style.bold = bold_val
        cfg.style.italic = italic_val
        cfg.style.outline = st.checkbox("描边 / Outline", value=cfg.style.outline)
        if cfg.style.outline:
            cfg.style.outline_width = st.slider(
                "描边宽度", 1, 10, cfg.style.outline_width, key="tw_outline_width"
            )
            oc = st.color_picker(
                "描边颜色",
                value=safe_color_hex(cfg.style.outline_color_rgba),
                key="outline_color",
            )
            try:
                cfg.style.outline_color_rgba = (
                    int(oc[1:3], 16),
                    int(oc[3:5], 16),
                    int(oc[5:7], 16),
                    255,
                )
            except Exception:
                pass
        cfg.style.shadow = st.checkbox("阴影 / Shadow", value=cfg.style.shadow)
        if cfg.style.shadow:
            sx = st.slider(
                "阴影 X", -20, 20, cfg.style.shadow_offset[0], key="tw_shadow_x"
            )
            sy = st.slider(
                "阴影 Y", -20, 20, cfg.style.shadow_offset[1], key="tw_shadow_y"
            )
            cfg.style.shadow_offset = (sx, sy)
            sc = st.color_picker(
                "阴影颜色",
                value=safe_color_hex(cfg.style.shadow_color_rgba),
                key="shadow_color",
            )
            try:
                cfg.style.shadow_color_rgba = (
                    int(sc[1:3], 16),
                    int(sc[3:5], 16),
                    int(sc[5:7], 16),
                    128,
                )
            except Exception:
                pass


def sidebar_image_watermark():
    st.sidebar.header("3. 图片水印 / Image")
    cfg: ImageWatermarkConfig = st.session_state.image_cfg
    cfg.enabled = st.sidebar.checkbox("启用图片水印", value=cfg.enabled)
    if not cfg.enabled:
        return
    uploaded = st.sidebar.file_uploader(
        "选择水印图片 (PNG 推荐)", type=["png", "jpg", "jpeg"], key="wm_img"
    )
    if uploaded:
        try:
            img = load_image_bytes(uploaded.getvalue())
            cfg.image_b64 = encode_image_to_b64(img)
            st.sidebar.image(img, caption="水印预览", use_container_width=True)
        except Exception as e:
            st.sidebar.error(f"载入失败: {e}")
    with st.sidebar.expander("缩放设置 / Scale"):
        mode = st.radio(
            "模式 / Mode",
            ["percent", "width"],
            index=(0 if cfg.scale_mode == "percent" else 1),
            key="iw_scale_mode",
            horizontal=True,
        )
        cfg.scale_mode = mode
        if cfg.scale_mode == "percent":
            cfg.scale_percent = st.slider(
                "缩放 %", 5, 400, cfg.scale_percent, key="iw_scale_percent"
            )
        else:
            cfg.width_px = st.number_input(
                "目标宽度 px", min_value=5, max_value=4000, value=cfg.width_px, step=10
            )
    cfg.opacity = st.sidebar.slider("透明度 %", 0, 100, cfg.opacity, key="iw_opacity")


def sidebar_position_and_rotation():
    st.sidebar.header("4. 位置与旋转 / Position & Rotation")
    # Preview width control
    pw = st.sidebar.number_input(
        "预览固定宽度 (px) / Preview Width",
        min_value=200,
        max_value=2000,
        value=int(st.session_state.preview_width),
        step=20,
        help="固定预览宽度，高度按原图比例自动适配 / Fixed preview width, height auto scales.",
        key="preview_width_input",
    )
    st.session_state.preview_width = pw
    st.sidebar.checkbox(
        "按图片分别记住位置 / Per-Image Position",
        value=st.session_state.per_image_position,
        key="per_image_position",
        help="开启后，每张图片可单独设置水印位置，切换图片自动加载。",
    )
    st.sidebar.checkbox(
        "调试信息 / Debug Info",
        value=st.session_state.get("debug_info", False),
        key="debug_info",
        help="显示水印尺寸与缩放诊断信息。",
    )
    st.sidebar.markdown("**九宫格预设 / 3x3 Presets**")
    # Ordered 3x3 grid
    grid_rows = [
        ("Top-Left", "Top-Center", "Top-Right"),
        ("Center-Left", "Center", "Center-Right"),
        ("Bottom-Left", "Bottom-Center", "Bottom-Right"),
    ]
    # Compute current canvas dims (approx) for absolute positioning in sidebar
    canvas_w = int(st.session_state.preview_width)
    canvas_h = 0
    if st.session_state.images:
        try:
            img_info = st.session_state.images[st.session_state.selected_index]
            base = load_image_bytes(img_info["data"])  # RGBA
            W, H = base.size
            canvas_h = int(H * (canvas_w / W)) if W else 0
        except Exception:
            pass
    for r_idx, row in enumerate(grid_rows):
        c1, c2, c3 = st.sidebar.columns(3)
        for col, name in zip((c1, c2, c3), row):
            label = name.replace("-", "\n") if r_idx != 1 else name.replace("-", "\n")
            if col.button(label, key=f"grid_{name}"):
                gx, gy = GRID_PRESETS[name]
                if canvas_h:
                    # Convert normalized preset to absolute center position
                    st.session_state.position_abs = (gx * canvas_w, gy * canvas_h)
                else:
                    st.session_state.position_norm = GRID_PRESETS[name]
                # Set a skip flag so the next canvas JSON update (old position) is ignored
                st.session_state._skip_next_canvas_update = True
    # Current position
    if st.session_state.get("position_abs") is not None and canvas_h:
        ax, ay = st.session_state.position_abs
        st.sidebar.markdown(
            f"当前位置 (px): `{int(ax)},{int(ay)}`  (画布: {canvas_w}x{canvas_h})"
        )
    else:
        st.sidebar.markdown(
            f"当前位置 (norm): `{st.session_state.position_norm[0]:.3f}, {st.session_state.position_norm[1]:.3f}`"
        )

    # Manual numeric (percent) inputs
    with st.sidebar.expander("手动位置 / Manual Position"):
        if canvas_h:
            colx, coly = st.columns(2)
            # Initialize abs if missing
            if st.session_state.position_abs is None:
                # derive from normalized
                nx, ny = st.session_state.position_norm
                st.session_state.position_abs = (nx * canvas_w, ny * canvas_h)
            ax, ay = st.session_state.position_abs or (canvas_w / 2, canvas_h / 2)
            x_px = colx.number_input(
                "X 像素 / px",
                min_value=0,
                max_value=canvas_w,
                value=int(ax),
                step=5,
                key="pos_x_px",
            )
            y_px = coly.number_input(
                "Y 像素 / px",
                min_value=0,
                max_value=canvas_h,
                value=int(ay),
                step=5,
                key="pos_y_px",
            )
            st.session_state.position_abs = (
                min(canvas_w, max(0, float(x_px))),
                min(canvas_h, max(0, float(y_px))),
            )
        else:
            st.info("当前无法计算画布尺寸，稍后在主视图更新。")

    # Rotation controls
    st.sidebar.markdown("**旋转 / Rotation**")
    rot_col1, rot_col2 = st.sidebar.columns([3, 1])
    rotation_slider_val = rot_col1.slider(
        "角度°", -180, 180, int(st.session_state.rotation), key="rot_slider"
    )
    # Fine rotation input
    rotation_input_val = rot_col2.number_input(
        "°",
        min_value=-180,
        max_value=180,
        value=int(rotation_slider_val),
        key="rot_input",
    )
    # Sync: priority to number input if changed
    if rotation_input_val != rotation_slider_val:
        st.session_state.rotation = rotation_input_val
    else:
        st.session_state.rotation = rotation_slider_val

    # Fine tune nudge controls
    with st.sidebar.expander("微调 / Fine Tune"):
        st.caption("每次移动 10px (可多次点击) / Move 10px per click")
        nc1, nc2, nc3 = st.columns(3)
        # Up row
        if nc2.button("⬆", key="nudge_up"):
            if st.session_state.position_abs is not None and canvas_h:
                x, y = st.session_state.position_abs
                st.session_state.position_abs = (x, max(0, y - 10))
        mid1, mid2, mid3 = st.columns(3)
        if mid1.button("⬅", key="nudge_left"):
            if st.session_state.position_abs is not None and canvas_w:
                x, y = st.session_state.position_abs
                st.session_state.position_abs = (max(0, x - 10), y)
        if mid2.button("居中", key="nudge_center"):
            if canvas_h:
                st.session_state.position_abs = (canvas_w / 2, canvas_h / 2)
        if mid3.button("➡", key="nudge_right"):
            if st.session_state.position_abs is not None and canvas_w:
                x, y = st.session_state.position_abs
                st.session_state.position_abs = (min(canvas_w, x + 10), y)
        lc1, lc2, lc3 = st.columns(3)
        if lc2.button("⬇", key="nudge_down"):
            if st.session_state.position_abs is not None and canvas_h:
                x, y = st.session_state.position_abs
                st.session_state.position_abs = (x, min(canvas_h, y + 10))
        if st.session_state.position_abs is not None and canvas_h:
            ax, ay = st.session_state.position_abs
            st.markdown(
                f"当前(px): `{int(ax)},{int(ay)}`  旋转: `{st.session_state.rotation:.1f}°`"
            )
        else:
            st.markdown(
                f"当前(norm): `{st.session_state.position_norm[0]:.3f},{st.session_state.position_norm[1]:.3f}`  旋转: `{st.session_state.rotation:.1f}°`"
            )
        rcol1, rcol2, rcol3 = st.columns(3)
        if rcol1.button("↺ -5°", key="rot_minus5"):
            st.session_state.rotation = (
                (st.session_state.rotation - 5)
                if st.session_state.rotation - 5 >= -180
                else -180
            )
        if rcol2.button("复位0°", key="rot_reset"):
            st.session_state.rotation = 0
        if rcol3.button("↻ +5°", key="rot_plus5"):
            st.session_state.rotation = (
                (st.session_state.rotation + 5)
                if st.session_state.rotation + 5 <= 180
                else 180
            )


def sidebar_export_settings():
    st.sidebar.header("5. 导出设置 / Export")
    os_cfg = st.session_state.output_settings
    os_cfg["output_dir"] = st.sidebar.text_input(
        "输出文件夹 Output Dir", value=os_cfg["output_dir"]
    )
    # Prevent exporting to same directory as originals? We'll warn if any original path known
    os_cfg["format"] = st.sidebar.selectbox(
        "输出格式 Format", ["PNG", "JPEG"], index=0 if os_cfg["format"] == "PNG" else 1
    )
    if os_cfg["format"] == "JPEG":
        os_cfg["jpeg_quality"] = st.sidebar.slider(
            "JPEG 质量", 1, 100, os_cfg["jpeg_quality"], key="jpeg_quality"
        )
    os_cfg["naming_mode"] = st.sidebar.selectbox(
        "命名规则",
        ["original", "prefix", "suffix"],
        index=["original", "prefix", "suffix"].index(os_cfg["naming_mode"]),
    )
    if os_cfg["naming_mode"] == "prefix":
        os_cfg["prefix"] = st.sidebar.text_input("前缀 Prefix", value=os_cfg["prefix"])
    if os_cfg["naming_mode"] == "suffix":
        os_cfg["suffix"] = st.sidebar.text_input("后缀 Suffix", value=os_cfg["suffix"])
    with st.sidebar.expander("尺寸调整 / Resize"):
        os_cfg["resize_mode"] = st.selectbox(
            "模式",
            ["none", "width", "height", "percent"],
            index=["none", "width", "height", "percent"].index(os_cfg["resize_mode"]),
        )
        if os_cfg["resize_mode"] != "none":
            if os_cfg["resize_mode"] == "percent":
                os_cfg["resize_value"] = st.slider(
                    "百分比 %",
                    1,
                    400,
                    os_cfg["resize_value"] or 100,
                    key="resize_percent",
                )
            else:
                os_cfg["resize_value"] = st.number_input(
                    "像素值", min_value=1, value=os_cfg["resize_value"] or 1024
                )
        os_cfg["resize_to_preview"] = st.checkbox(
            "匹配当前预览宽度 / Match Preview Width",
            value=os_cfg.get("resize_to_preview", False),
            help="忽略上面模式，导出时等比例缩放到当前预览宽度。",
        )

    col_exp1, col_exp2 = st.sidebar.columns(2)
    if col_exp1.button("批量导出到磁盘 / Export To Folder"):
        export_all_images()
    if col_exp2.button("打包ZIP(浏览器下载)"):
        zip_bytes = export_all_images_to_zip_bytes()
        if zip_bytes:
            st.session_state._zip_export_bytes = zip_bytes
            ts_name = "watermarked_images.zip"
            st.session_state._zip_export_name = ts_name
        else:
            st.sidebar.error("没有图片或导出失败")
    if st.session_state.get("_zip_export_bytes"):
        st.sidebar.download_button(
            "下载ZIP",
            data=st.session_state._zip_export_bytes,
            file_name=st.session_state.get(
                "_zip_export_name", "watermarked_images.zip"
            ),
            mime="application/zip",
        )


def sidebar_templates():
    st.sidebar.header("6. 模板管理 / Templates")
    templates = st.session_state.templates
    existing_names = list(templates.keys())
    if existing_names:
        sel = st.sidebar.selectbox("选择模板 / Select", ["(选择)"] + existing_names)
        if sel != "(选择)" and st.sidebar.button("加载模板 / Load"):
            tmpl = WatermarkTemplate.from_dict(templates[sel])
            st.session_state.text_cfg = tmpl.text_cfg
            st.session_state.image_cfg = tmpl.image_cfg
            st.session_state.position_norm = tmpl.position
            st.session_state.rotation = tmpl.rotation_deg
            # Force re-derive absolute position on next layout
            st.session_state.position_abs = None
            os_cfg = st.session_state.output_settings
            os_cfg["format"] = tmpl.output_format
            os_cfg["jpeg_quality"] = tmpl.jpeg_quality
            os_cfg["resize_mode"] = tmpl.resize_mode
            os_cfg["resize_value"] = tmpl.resize_value
            st.sidebar.success("模板已加载")
    new_name = st.sidebar.text_input("新模板名称 / Name")
    if st.sidebar.button("保存模板 / Save") and new_name:
        # Ensure normalized position updated from absolute for template persistence
        if st.session_state.get("position_abs") is not None and st.session_state.images:
            try:
                img_info = st.session_state.images[st.session_state.selected_index]
                base = load_image_bytes(img_info["data"])  # RGBA
                W, H = base.size
                preview_w = st.session_state.preview_width
                preview_h = int(H * (preview_w / W)) if W else 1
                nx = st.session_state.position_abs[0] / preview_w
                ny = st.session_state.position_abs[1] / preview_h if preview_h else 0.5
                st.session_state.position_norm = clamp_norm((nx, ny))
            except Exception:
                pass
        tmpl = WatermarkTemplate(
            name=new_name,
            text_cfg=st.session_state.text_cfg,
            image_cfg=st.session_state.image_cfg,
            position=st.session_state.position_norm,
            rotation_deg=st.session_state.rotation,
            output_format=st.session_state.output_settings["format"],
            jpeg_quality=st.session_state.output_settings["jpeg_quality"],
            resize_mode=st.session_state.output_settings["resize_mode"],
            resize_value=st.session_state.output_settings["resize_value"],
        )
        templates[new_name] = tmpl.to_dict()
        save_templates(templates)
        st.sidebar.success("已保存模板")
    if existing_names:
        del_name = st.sidebar.selectbox(
            "删除模板 / Delete", ["(选择)"] + existing_names, key="del_tmpl"
        )
        if del_name != "(选择)" and st.sidebar.button("确认删除 / Confirm Delete"):
            templates.pop(del_name, None)
            save_templates(templates)
            st.sidebar.warning("已删除模板")
        if st.sidebar.button("删除所有模板 / Delete All", key="del_all_tmpl"):
            templates.clear()
            save_templates(templates)
            st.sidebar.warning("已清空所有模板")


def export_all_images():
    if not st.session_state.images:
        st.sidebar.error("没有图片可导出")
        return
    os_cfg = st.session_state.output_settings
    out_dir = Path(os_cfg["output_dir"]).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = os_cfg["format"].upper()
    total = len(st.session_state.images)
    progress = st.sidebar.progress(0, text="导出中...")
    for idx, img_info in enumerate(st.session_state.images, start=1):
        base = load_image_bytes(img_info["data"])  # RGBA
        # Derive normalized from absolute current preview layout
        W, H = base.size
        preview_w = st.session_state.preview_width
        preview_h = int(H * (preview_w / W)) if W else 1
        # Per-image absolute override
        if (
            st.session_state.per_image_position
            and "image_positions_abs" in st.session_state
        ):
            per_abs = (
                st.session_state.image_positions_abs.get(img_info["name"])
                if st.session_state.image_positions_abs
                else None
            )
        else:
            per_abs = None
        abs_pos = per_abs or st.session_state.get("position_abs")
        if abs_pos is not None:
            ax, ay = abs_pos
            nx = ax / preview_w
            ny = ay / preview_h if preview_h else 0.5
        else:
            nx, ny = st.session_state.position_norm
        pos_norm = clamp_norm((nx, ny))
        wm_layer = build_watermark_layer(
            base,
            st.session_state.text_cfg,
            st.session_state.image_cfg,
            pos_norm,
            st.session_state.rotation,
        )
        name = Path(img_info["name"]).stem
        ext = ".jpg" if fmt == "JPEG" else ".png"
        if os_cfg["naming_mode"] == "original":
            out_name = name + ext
        elif os_cfg["naming_mode"] == "prefix":
            out_name = f"{os_cfg['prefix']}{name}{ext}"
        else:
            out_name = f"{name}{os_cfg['suffix']}{ext}"
        out_path = out_dir / out_name
        export_image(
            base,
            wm_layer,
            out_path,
            fmt=fmt,
            jpeg_quality=os_cfg.get("jpeg_quality", 90),
            resize_mode=os_cfg.get("resize_mode", "none"),
            resize_value=os_cfg.get("resize_value", 0),
            force_width=(
                st.session_state.preview_width
                if os_cfg.get("resize_to_preview")
                else None
            ),
        )
        progress.progress(idx / total, text=f"导出 {idx}/{total}")
    progress.empty()
    st.sidebar.success("全部导出完成")


def export_all_images_to_zip_bytes() -> Optional[bytes]:
    """Return a zip (bytes) containing all exported images using current settings (same logic as export_all_images).

    This does NOT write to disk; it mirrors export settings including resizing & preview-width override.
    """
    if not st.session_state.images:
        return None
    os_cfg = st.session_state.output_settings
    fmt = os_cfg["format"].upper()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for img_info in st.session_state.images:
            base = load_image_bytes(img_info["data"]).convert("RGBA")
            W, H = base.size
            preview_w = st.session_state.preview_width
            preview_h = int(H * (preview_w / W)) if W else 1
            if (
                st.session_state.per_image_position
                and "image_positions_abs" in st.session_state
            ):
                per_abs = (
                    st.session_state.image_positions_abs.get(img_info["name"])
                    if st.session_state.image_positions_abs
                    else None
                )
            else:
                per_abs = None
            abs_pos = per_abs or st.session_state.get("position_abs")
            if abs_pos is not None:
                ax, ay = abs_pos
                nx = ax / preview_w
                ny = ay / preview_h if preview_h else 0.5
            else:
                nx, ny = st.session_state.position_norm
            pos_norm = clamp_norm((nx, ny))
            wm_layer = build_watermark_layer(
                base,
                st.session_state.text_cfg,
                st.session_state.image_cfg,
                pos_norm,
                st.session_state.rotation,
            )
            composite = composite_preview(base, wm_layer)
            # Apply export resizing logic (in-memory)
            force_width = (
                st.session_state.preview_width
                if os_cfg.get("resize_to_preview")
                else None
            )
            if force_width is not None and force_width > 0:
                if force_width != composite.width:
                    ratio = force_width / composite.width
                    composite = composite.resize(
                        (force_width, max(1, int(composite.height * ratio))),
                        Image.Resampling.LANCZOS,
                    )
            elif (
                os_cfg.get("resize_mode") != "none"
                and os_cfg.get("resize_value", 0) > 0
            ):
                rm = os_cfg.get("resize_mode")
                rv = os_cfg.get("resize_value")
                if rm == "width":
                    w = rv
                    ratio = w / composite.width
                    h = int(composite.height * ratio)
                    composite = composite.resize((w, h), Image.Resampling.LANCZOS)
                elif rm == "height":
                    h = rv
                    ratio = h / composite.height
                    w = int(composite.width * ratio)
                    composite = composite.resize((w, h), Image.Resampling.LANCZOS)
                elif rm == "percent":
                    scale = rv / 100.0
                    w = int(composite.width * scale)
                    h = int(composite.height * scale)
                    composite = composite.resize((w, h), Image.Resampling.LANCZOS)
            # Determine filename
            name = Path(img_info["name"]).stem
            ext = ".jpg" if fmt == "JPEG" else ".png"
            if os_cfg["naming_mode"] == "original":
                out_name = name + ext
            elif os_cfg["naming_mode"] == "prefix":
                out_name = f"{os_cfg['prefix']}{name}{ext}"
            else:
                out_name = f"{name}{os_cfg['suffix']}{ext}"
            # Encode to bytes
            img_bytes = io.BytesIO()
            save_img = composite.convert("RGB") if fmt == "JPEG" else composite
            save_kwargs = (
                {"quality": os_cfg.get("jpeg_quality", 90)} if fmt == "JPEG" else {}
            )
            save_img.save(img_bytes, format=fmt, **save_kwargs)
            zf.writestr(out_name, img_bytes.getvalue())
    return buf.getvalue()


def main_layout():
    st.title("📷 Photo Watermark")
    st.caption("批量水印工具 / Batch Watermark Tool (Streamlit)")
    if not st.session_state.images:
        st.info("请在左侧导入图片 / Use the sidebar to import images")
        return
    # Thumbnail gallery of imported images
    with st.expander("已导入图片 / Imported Images", expanded=True):
        imgs = st.session_state.images
        if imgs:
            # Arrange in rows of 6 thumbnails
            per_row = 6
            for row_start in range(0, len(imgs), per_row):
                row_imgs = imgs[row_start : row_start + per_row]
                cols = st.columns(len(row_imgs))
                for c, info in zip(cols, row_imgs):
                    name = info["name"]
                    thumb = _get_thumbnail(info["data"], 100)
                    c.image(thumb, use_container_width=True)
                    # Highlight selected
                    is_sel = (
                        st.session_state.images[st.session_state.selected_index]["name"]
                        == name
                    )
                    style = "✅" if is_sel else "选择"
                    if c.button(style, key=f"thumb_select_{row_start}_{name}"):
                        # update selected index
                        for i_global, item in enumerate(imgs):
                            if item["name"] == name:
                                st.session_state.selected_index = i_global
                                # Force rebuild on next run by resetting sig
                                st.session_state._wm_sig = None
                                if hasattr(st, "rerun"):
                                    st.rerun()
                                else:
                                    getattr(st, "experimental_rerun", lambda: None)()
                        # break not needed, rerun triggered
                    c.caption(name)
        else:
            st.write("(无)")
    # current image
    img_info = st.session_state.images[st.session_state.selected_index]
    base = load_image_bytes(img_info["data"])  # RGBA
    W, H = base.size
    # Single interactive canvas only (no secondary image) with persistent objects
    st.subheader("预览 / Preview (拖动水印保持位置)")
    if hasattr(st.session_state, "_cjk_notice"):
        st.info(st.session_state._cjk_notice)
    # Use user-selected fixed width (height auto)
    canvas_w = int(st.session_state.preview_width)
    if canvas_w <= 0:
        canvas_w = min(800, W)
    ratio = canvas_w / W if W else 1
    canvas_h = int(H * ratio) if H else 0
    display_base = base.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)

    # Build a signature of watermark appearance (changes when config/rotation changes)
    sig_parts = [
        st.session_state.text_cfg.text,
        str(st.session_state.text_cfg.enabled),
        str(st.session_state.text_cfg.style.font_path),
        str(st.session_state.text_cfg.style.size),
        str(st.session_state.text_cfg.style.bold),
        str(st.session_state.text_cfg.style.italic),
        str(st.session_state.text_cfg.style.fill_rgba),
        str(st.session_state.text_cfg.style.outline),
        str(st.session_state.text_cfg.style.outline_width),
        str(st.session_state.text_cfg.style.outline_color_rgba),
        str(st.session_state.text_cfg.style.shadow),
        str(st.session_state.text_cfg.style.shadow_offset),
        str(st.session_state.text_cfg.style.shadow_color_rgba),
        str(st.session_state.text_cfg.opacity),
        str(st.session_state.image_cfg.enabled),
        str(st.session_state.image_cfg.scale_percent),
        str(st.session_state.image_cfg.opacity),
        str(st.session_state.image_cfg.image_b64)[:32],
        str(st.session_state.rotation),
        # Include image identity and canvas dims so switching images forces rebuild
        f"img_idx={st.session_state.selected_index}",
        f"base={W}x{H}",
    ]
    current_sig = hash("|".join(sig_parts))
    if "_wm_sig" not in st.session_state:
        st.session_state._wm_sig = None
    if "_wm_canvas_objects" not in st.session_state:
        st.session_state._wm_canvas_objects = None

    composed = compute_composed_watermark(
        st.session_state.text_cfg, st.session_state.image_cfg
    )
    if composed is not None and (st.session_state.rotation % 360) != 0:
        composed = composed.rotate(st.session_state.rotation, expand=True)

    rebuild_objects = st.session_state._wm_sig != current_sig

    # Prepare absolute position (center) if not yet set or if coming from legacy normalized only
    if st.session_state.get("position_abs") is None:
        nx, ny = st.session_state.position_norm
        st.session_state.position_abs = (nx * canvas_w, ny * canvas_h)
    else:
        # Clamp to new canvas dims when switching images / size changes
        ax, ay = st.session_state.position_abs
        st.session_state.position_abs = (
            min(canvas_w, max(0, ax)),
            min(canvas_h, max(0, ay)),
        )

    if rebuild_objects:
        objs = []
        if composed is not None:
            try:
                buf = io.BytesIO()
                composed.save(buf, format="PNG")
                b64_data = base64.b64encode(buf.getvalue()).decode()
                ww, hh = composed.size
                # Keep intrinsic size (no scaling by base image) + safety 1
                dw = ww + 1
                dh = hh + 1
                ax, ay = st.session_state.position_abs
                # Use center origin to avoid oscillation between two computed centers
                objs.append(
                    {
                        "type": "image",
                        "left": ax,
                        "top": ay,
                        "width": dw,
                        "height": dh,
                        "angle": 0,
                        "scaleX": 1,
                        "scaleY": 1,
                        "originX": "center",
                        "originY": "center",
                        "src": f"data:image/png;base64,{b64_data}",
                    }
                )
            except Exception:
                pass
        else:
            # If no composed watermark (e.g. disabled / empty), clear objects
            st.session_state._wm_canvas_objects = []
        st.session_state._wm_canvas_objects = objs
        st.session_state._wm_sig = current_sig
    else:
        # No rebuild (appearance unchanged). If position changed (e.g., preset click), update object placement.
        if (
            composed is not None
            and st.session_state._wm_canvas_objects
            and st.session_state.position_abs is not None
        ):
            try:
                ax, ay = st.session_state.position_abs
                obj = st.session_state._wm_canvas_objects[-1]
                # If origin is center keep left/top as center
                if obj.get("originX") == "center" and obj.get("originY") == "center":
                    obj["left"] = ax
                    obj["top"] = ay
                else:
                    w_obj = obj.get("width", 0) * obj.get("scaleX", 1)
                    h_obj = obj.get("height", 0) * obj.get("scaleY", 1)
                    obj["left"] = ax - w_obj / 2
                    obj["top"] = ay - h_obj / 2
            except Exception:
                pass

    canvas_key = f"wm_drag_canvas_{current_sig if composed is not None else 'empty'}"
    canvas_result = st_canvas(
        background_image=display_base,
        height=canvas_h,
        width=canvas_w,
        drawing_mode="transform",
        initial_drawing={
            "version": "4.4.0",
            "objects": st.session_state._wm_canvas_objects or [],
        },
        key=canvas_key,
        update_streamlit=True,
    )

    # Update position from moved image (do NOT rebuild objects here to avoid jump)
    if canvas_result.json_data is not None and composed is not None:
        objs = canvas_result.json_data.get("objects", [])
        if objs:
            img_obj = objs[-1]
            # Determine center depending on origin
            if (
                img_obj.get("originX") == "center"
                and img_obj.get("originY") == "center"
            ):
                cx = img_obj.get("left", 0)
                cy = img_obj.get("top", 0)
            else:
                left = img_obj.get("left", 0)
                top = img_obj.get("top", 0)
                w_obj = img_obj.get("width", 1) * img_obj.get("scaleX", 1)
                h_obj = img_obj.get("height", 1) * img_obj.get("scaleY", 1)
                cx = left + w_obj / 2
                cy = top + h_obj / 2
            if st.session_state.get("_skip_next_canvas_update"):
                # Consume the flag without updating (prevent jump back)
                st.session_state._skip_next_canvas_update = False
            else:
                st.session_state.position_abs = (
                    min(canvas_w, max(0, cx)),
                    min(canvas_h, max(0, cy)),
                )
            # Maintain derived normalized for backward compatibility / template save
            nx = st.session_state.position_abs[0] / canvas_w
            ny = st.session_state.position_abs[1] / canvas_h
            st.session_state.position_norm = clamp_norm((nx, ny))
            if st.session_state.per_image_position:
                if "image_positions_abs" not in st.session_state:
                    st.session_state.image_positions_abs = {}
                st.session_state.image_positions_abs[img_info["name"]] = (
                    st.session_state.position_abs
                )

    if composed is None:
        st.warning(
            "当前没有可显示的水印：请确认已勾选 '启用文本水印' 且文本不为空，或启用图片水印。"
        )
    else:
        if st.session_state.get("debug_info"):
            # Display intrinsic (watermark) size and current canvas size; displayed size equals intrinsic + safety.
            disp_w = dw if "dw" in locals() else composed.width
            disp_h = dh if "dh" in locals() else composed.height
            st.info(
                f"Debug: intrinsic={composed.size}, canvas={canvas_w}x{canvas_h}, displayed={disp_w}x{disp_h}"
            )
    if st.session_state.get("position_abs") is not None:
        ax, ay = st.session_state.position_abs
        st.markdown(
            f"**当前绝对位置 / Position(px):** ({int(ax)}, {int(ay)})  (画布: {canvas_w}x{canvas_h})"
        )
    else:
        st.markdown(
            f"**当前归一化位置 / Position:** {st.session_state.position_norm} (拖动即可保持)"
        )

    # Show template save quick
    st.divider()
    if st.button("保存当前状态 / Save Last State"):
        # Convert absolute -> normalized for persistence
        if st.session_state.get("position_abs") is not None:
            nx = st.session_state.position_abs[0] / canvas_w
            ny = st.session_state.position_abs[1] / canvas_h
            st.session_state.position_norm = clamp_norm((nx, ny))
        save_last_state(
            {
                "text_cfg": asdict(st.session_state.text_cfg),
                "image_cfg": asdict(st.session_state.image_cfg),
                "position": st.session_state.position_norm,
                "rotation": st.session_state.rotation,
                "output": st.session_state.output_settings,
            }
        )
        st.success("已保存本次状态 (Auto-load next start)")
    # Single current image composite download (browser)
    if composed is not None:
        try:
            base_current = base
            # Build watermark layer using normalized derived from current absolute
            nx_dl = st.session_state.position_norm[0]
            ny_dl = st.session_state.position_norm[1]
            wm_layer_dl = build_watermark_layer(
                base_current,
                st.session_state.text_cfg,
                st.session_state.image_cfg,
                (nx_dl, ny_dl),
                st.session_state.rotation,
            )
            composite_current = composite_preview(base_current, wm_layer_dl)
            # Apply preview-width forced resize if user selected that option while exporting single image? Provide toggle
            if st.session_state.output_settings.get("resize_to_preview"):
                if composite_current.width != st.session_state.preview_width:
                    ratio = st.session_state.preview_width / composite_current.width
                    composite_current = composite_current.resize(
                        (
                            st.session_state.preview_width,
                            max(1, int(composite_current.height * ratio)),
                        ),
                        Image.Resampling.LANCZOS,
                    )
            fmt_single = st.session_state.output_settings.get("format", "PNG").upper()
            single_bytes = io.BytesIO()
            save_img_single = (
                composite_current.convert("RGB")
                if fmt_single == "JPEG"
                else composite_current
            )
            save_kwargs_single = (
                {"quality": st.session_state.output_settings.get("jpeg_quality", 90)}
                if fmt_single == "JPEG"
                else {}
            )
            save_img_single.save(single_bytes, format=fmt_single, **save_kwargs_single)
            single_bytes_val = single_bytes.getvalue()
            st.download_button(
                "下载当前预览 / Download Current",
                data=single_bytes_val,
                file_name=f"{Path(img_info['name']).stem}_watermarked.{('jpg' if fmt_single == 'JPEG' else 'png')}",
                mime=("image/jpeg" if fmt_single == "JPEG" else "image/png"),
                help="通过浏览器下载，保存位置由浏览器设置决定。",
            )
        except Exception as e:
            st.warning(f"单图下载失败: {e}")


def auto_load_last_state():
    data = load_last_state()
    if not data:
        return
    try:
        # Rebuild text_cfg
        tc_raw = data.get("text_cfg")
        if tc_raw:
            st.session_state.text_cfg = TextWatermarkConfig(
                enabled=tc_raw.get("enabled", True),
                text=tc_raw.get("text", "Sample Watermark"),
                opacity=tc_raw.get("opacity", 100),
                style=TextStyle(**tc_raw.get("style", {})),
            )
        ic_raw = data.get("image_cfg")
        if ic_raw:
            st.session_state.image_cfg = ImageWatermarkConfig(**ic_raw)
        if "position" in data:
            st.session_state.position_norm = tuple(data["position"])
        if "rotation" in data:
            st.session_state.rotation = data["rotation"]
        if "output" in data:
            st.session_state.output_settings.update(data["output"])
    except Exception:
        pass


def run_app():
    init_session_state()
    if st.session_state.get("_first_run") is None:
        auto_load_last_state()
        st.session_state._first_run = False
    # Sidebar
    sidebar_import_panel()
    sidebar_text_watermark()
    sidebar_image_watermark()
    sidebar_position_and_rotation()
    sidebar_export_settings()
    sidebar_templates()
    # Main layout
    main_layout()


if __name__ == "__main__":
    # Allow running via `streamlit run watermark_app.py`
    run_app()
