"""
照片水印工具 - Streamlit版本
支持文本和图片水印，配置管理，批量处理等功能
"""

import io
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont


def init_session_state():
    """初始化session state"""
    if "uploaded_images" not in st.session_state:
        st.session_state.uploaded_images = []
    if "current_image_index" not in st.session_state:
        st.session_state.current_image_index = 0
    if "watermark_settings" not in st.session_state:
        st.session_state.watermark_settings = {
            "type": "text",
            "text": "水印文本",
            "font_size": 24,
            "font_color": "#000000",
            "opacity": 80,
            "position": "右下",
            "custom_x": 0,
            "custom_y": 0,
            "rotation": 0,
            "bold": False,
            "italic": False,
            "shadow": False,
            "outline": False,
            "image_path": None,
            "image_scale": 50,
            "image_opacity": 80,
        }


def create_sidebar():
    """创建侧边栏"""
    st.sidebar.title("🖼️ 照片水印工具")
    st.sidebar.markdown("---")

    # 文件上传
    st.sidebar.subheader("📁 图片导入")
    uploaded_files = st.sidebar.file_uploader(
        "选择图片文件",
        type=["png", "jpg", "jpeg", "bmp", "tiff"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    if uploaded_files:
        st.session_state.uploaded_images = uploaded_files
        st.sidebar.success(f"已导入 {len(uploaded_files)} 张图片")

    # 图片列表
    if st.session_state.uploaded_images:
        st.sidebar.subheader("📋 图片列表")
        image_names = [f.name for f in st.session_state.uploaded_images]
        selected_index = st.sidebar.selectbox(
            "选择预览图片",
            range(len(image_names)),
            format_func=lambda x: image_names[x],
            key="image_selector",
        )
        st.session_state.current_image_index = selected_index

        # 图片信息
        current_file = st.session_state.uploaded_images[selected_index]
        current_image = Image.open(current_file)
        st.sidebar.info(
            f"""
        **文件名:** {current_file.name}
        **尺寸:** {current_image.size[0]} × {current_image.size[1]}
        **格式:** {current_image.format}
        **模式:** {current_image.mode}
        """
        )


def create_watermark_settings():
    """创建水印设置区域"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎨 水印设置")

    # 水印类型
    watermark_type = st.sidebar.radio(
        "水印类型", ["文本水印", "图片水印"], key="watermark_type_radio"
    )
    st.session_state.watermark_settings["type"] = (
        "text" if watermark_type == "文本水印" else "image"
    )

    if watermark_type == "文本水印":
        create_text_watermark_settings()
    else:
        create_image_watermark_settings()

    create_position_settings()
    create_export_settings()


def create_text_watermark_settings():
    """创建文本水印设置"""
    st.sidebar.markdown("### 📝 文本设置")

    # 水印文本
    text = st.sidebar.text_input(
        "水印文本",
        value=st.session_state.watermark_settings["text"],
        key="watermark_text",
    )
    st.session_state.watermark_settings["text"] = text

    # 字体大小
    font_size = st.sidebar.slider(
        "字体大小",
        min_value=10,
        max_value=200,
        value=st.session_state.watermark_settings["font_size"],
        key="font_size",
    )
    st.session_state.watermark_settings["font_size"] = font_size

    # 字体颜色
    font_color = st.sidebar.color_picker(
        "字体颜色",
        value=st.session_state.watermark_settings["font_color"],
        key="font_color",
    )
    st.session_state.watermark_settings["font_color"] = font_color

    # 透明度
    opacity = st.sidebar.slider(
        "透明度 (%)",
        min_value=0,
        max_value=100,
        value=st.session_state.watermark_settings["opacity"],
        key="text_opacity",
    )
    st.session_state.watermark_settings["opacity"] = opacity

    # 字体样式
    col1, col2 = st.sidebar.columns(2)
    with col1:
        bold = st.checkbox("粗体", key="font_bold")
        st.session_state.watermark_settings["bold"] = bold
    with col2:
        italic = st.checkbox("斜体", key="font_italic")
        st.session_state.watermark_settings["italic"] = italic

    # 特效
    st.sidebar.markdown("#### 🎭 文字特效")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        shadow = st.checkbox("阴影", key="text_shadow")
        st.session_state.watermark_settings["shadow"] = shadow
    with col2:
        outline = st.checkbox("描边", key="text_outline")
        st.session_state.watermark_settings["outline"] = outline


def create_image_watermark_settings():
    """创建图片水印设置"""
    st.sidebar.markdown("### 🖼️ 图片设置")

    # 水印图片上传
    watermark_image = st.sidebar.file_uploader(
        "选择水印图片", type=["png", "jpg", "jpeg"], key="watermark_image_uploader"
    )

    if watermark_image:
        st.session_state.watermark_settings["image_path"] = watermark_image
        st.sidebar.success("水印图片已选择")

        # 显示水印图片预览
        watermark_img = Image.open(watermark_image)
        st.sidebar.image(watermark_img, caption="水印图片预览", width=200)

        # 缩放比例
        image_scale = st.sidebar.slider(
            "缩放比例 (%)",
            min_value=10,
            max_value=200,
            value=st.session_state.watermark_settings["image_scale"],
            key="image_scale",
        )
        st.session_state.watermark_settings["image_scale"] = image_scale

        # 透明度
        image_opacity = st.sidebar.slider(
            "透明度 (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.watermark_settings["image_opacity"],
            key="image_opacity",
        )
        st.session_state.watermark_settings["image_opacity"] = image_opacity
    else:
        st.sidebar.warning("请选择水印图片")


def create_position_settings():
    """创建位置设置"""
    st.sidebar.markdown("### 📍 位置设置")

    # 预设位置
    position_options = [
        "左上",
        "上中",
        "右上",
        "左中",
        "中心",
        "右中",
        "左下",
        "下中",
        "右下",
    ]

    position = st.sidebar.selectbox(
        "预设位置",
        position_options,
        index=position_options.index(st.session_state.watermark_settings["position"]),
        key="position_select",
    )
    st.session_state.watermark_settings["position"] = position

    # 自定义位置
    st.sidebar.markdown("#### 🎯 自定义位置")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        custom_x = st.number_input(
            "X坐标",
            value=st.session_state.watermark_settings["custom_x"],
            key="custom_x",
        )
        st.session_state.watermark_settings["custom_x"] = custom_x
    with col2:
        custom_y = st.number_input(
            "Y坐标",
            value=st.session_state.watermark_settings["custom_y"],
            key="custom_y",
        )
        st.session_state.watermark_settings["custom_y"] = custom_y

    # 旋转角度
    rotation = st.sidebar.slider(
        "旋转角度 (°)",
        min_value=-180,
        max_value=180,
        value=st.session_state.watermark_settings["rotation"],
        key="rotation",
    )
    st.session_state.watermark_settings["rotation"] = rotation


def create_export_settings():
    """创建导出设置"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 导出设置")

    # 输出格式
    output_format = st.sidebar.radio("输出格式", ["JPEG", "PNG"], key="output_format")

    # JPEG质量
    if output_format == "JPEG":
        st.sidebar.slider(
            "JPEG质量", min_value=1, max_value=100, value=95, key="jpeg_quality"
        )

    # 文件命名
    naming_option = st.sidebar.radio(
        "文件命名", ["保留原名", "添加前缀", "添加后缀"], index=2, key="naming_option"
    )

    if naming_option != "保留原名":
        st.sidebar.text_input(
            "前缀/后缀",
            value="_watermarked" if naming_option == "添加后缀" else "wm_",
            key="affix_text",
        )


def get_watermark_position(
    image_size, watermark_size, position, custom_x=0, custom_y=0
):
    """计算水印位置"""
    img_width, img_height = image_size
    wm_width, wm_height = watermark_size
    margin = 20

    position_map = {
        "左上": (margin, margin),
        "上中": ((img_width - wm_width) // 2, margin),
        "右上": (img_width - wm_width - margin, margin),
        "左中": (margin, (img_height - wm_height) // 2),
        "中心": ((img_width - wm_width) // 2, (img_height - wm_height) // 2),
        "右中": (img_width - wm_width - margin, (img_height - wm_height) // 2),
        "左下": (margin, img_height - wm_height - margin),
        "下中": ((img_width - wm_width) // 2, img_height - wm_height - margin),
        "右下": (img_width - wm_width - margin, img_height - wm_height - margin),
    }

    if position in position_map:
        return position_map[position]
    else:
        return (custom_x, custom_y)


def apply_text_watermark(image, settings):
    """应用文本水印"""
    # 创建一个可以绘制的图像副本
    watermarked = image.copy()

    # 创建绘图对象
    if watermarked.mode != "RGBA":
        watermarked = watermarked.convert("RGBA")

    # 创建透明覆盖层
    overlay = Image.new("RGBA", watermarked.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # 尝试加载字体
    try:
        # 这里可以添加更多字体路径
        font = ImageFont.truetype("arial.ttf", settings["font_size"])
    except Exception:
        font = ImageFont.load_default()

    # 计算文本尺寸
    bbox = draw.textbbox((0, 0), settings["text"], font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # 计算位置
    position = get_watermark_position(
        watermarked.size,
        (text_width, text_height),
        settings["position"],
        settings["custom_x"],
        settings["custom_y"],
    )

    # 转换颜色和透明度
    color = settings["font_color"]
    alpha = int(255 * settings["opacity"] / 100)

    # 将hex颜色转换为RGB
    color_rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
    text_color = color_rgb + (alpha,)

    # 绘制特效
    if settings["shadow"]:
        # 绘制阴影
        shadow_offset = max(2, settings["font_size"] // 12)
        shadow_pos = (position[0] + shadow_offset, position[1] + shadow_offset)
        draw.text(shadow_pos, settings["text"], font=font, fill=(0, 0, 0, alpha // 2))

    if settings["outline"]:
        # 绘制描边
        outline_width = max(1, settings["font_size"] // 20)
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    outline_pos = (position[0] + dx, position[1] + dy)
                    draw.text(
                        outline_pos,
                        settings["text"],
                        font=font,
                        fill=(255, 255, 255, alpha),
                    )

    # 绘制主要文本
    draw.text(position, settings["text"], font=font, fill=text_color)

    # 合并覆盖层
    watermarked = Image.alpha_composite(watermarked, overlay)

    # 如果需要旋转
    if settings["rotation"] != 0:
        watermarked = watermarked.rotate(settings["rotation"], expand=True)

    return watermarked.convert("RGB")


def apply_image_watermark(image, settings):
    """应用图片水印"""
    if not settings["image_path"]:
        return image

    watermarked = image.copy()
    if watermarked.mode != "RGBA":
        watermarked = watermarked.convert("RGBA")

    # 加载水印图片
    watermark_img = Image.open(settings["image_path"])
    if watermark_img.mode != "RGBA":
        watermark_img = watermark_img.convert("RGBA")

    # 调整水印尺寸
    original_size = watermark_img.size
    scale_factor = settings["image_scale"] / 100
    new_size = (
        int(original_size[0] * scale_factor),
        int(original_size[1] * scale_factor),
    )
    watermark_img = watermark_img.resize(new_size, Image.Resampling.LANCZOS)

    # 调整透明度
    alpha = settings["image_opacity"] / 100
    watermark_img = Image.blend(
        Image.new("RGBA", watermark_img.size, (255, 255, 255, 0)), watermark_img, alpha
    )

    # 计算位置
    position = get_watermark_position(
        watermarked.size,
        watermark_img.size,
        settings["position"],
        settings["custom_x"],
        settings["custom_y"],
    )

    # 如果需要旋转
    if settings["rotation"] != 0:
        watermark_img = watermark_img.rotate(settings["rotation"], expand=True)

    # 粘贴水印
    watermarked.paste(watermark_img, position, watermark_img)

    return watermarked.convert("RGB")


def create_main_content():
    """创建主要内容区域"""
    st.title("🖼️ 照片水印工具")
    st.markdown("在左侧上传图片并配置水印设置，实时预览效果")

    if not st.session_state.uploaded_images:
        st.info("👈 请在左侧上传图片开始使用")
        st.markdown(
            """
        ### 功能特色
        - 📁 **批量处理**: 支持同时处理多张图片
        - 📝 **文本水印**: 自定义文字、字体、颜色、透明度
        - 🖼️ **图片水印**: 支持PNG透明水印图片
        - 📍 **灵活定位**: 九宫格预设位置 + 自定义坐标
        - 🎨 **丰富特效**: 阴影、描边、旋转等效果
        - 💾 **多格式导出**: 支持JPEG和PNG格式
        - ⚡ **实时预览**: 所见即所得的预览效果
        """
        )
        return

    # 获取当前图片
    current_file = st.session_state.uploaded_images[
        st.session_state.current_image_index
    ]
    current_image = Image.open(current_file)

    # 应用水印
    settings = st.session_state.watermark_settings
    if settings["type"] == "text":
        watermarked_image = apply_text_watermark(current_image, settings)
    else:
        watermarked_image = apply_image_watermark(current_image, settings)

    # 显示预览
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📷 原图")
        st.image(current_image, width="stretch")

    with col2:
        st.subheader("🎨 预览效果")
        st.image(watermarked_image, width="stretch")

    # 导出按钮
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 下载当前图片", width="stretch"):
            download_single_image(watermarked_image, current_file.name)

    with col2:
        if st.button("📦 批量处理下载", width="stretch"):
            download_batch_images()

    with col3:
        if st.button("🔄 重置设置", width="stretch"):
            reset_settings()


def download_single_image(image, filename):
    """下载单张图片"""
    # 准备下载
    output_format = st.session_state.get("output_format", "JPEG")

    # 生成文件名
    name_base = Path(filename).stem
    extension = ".jpg" if output_format == "JPEG" else ".png"

    naming_option = st.session_state.get("naming_option", "添加后缀")
    affix_text = st.session_state.get("affix_text", "_watermarked")

    if naming_option == "保留原名":
        new_filename = name_base + extension
    elif naming_option == "添加前缀":
        new_filename = affix_text + name_base + extension
    else:  # 添加后缀
        new_filename = name_base + affix_text + extension

    # 转换图片为字节
    img_buffer = io.BytesIO()
    if output_format == "JPEG":
        quality = st.session_state.get("jpeg_quality", 95)
        image.save(img_buffer, format="JPEG", quality=quality)
    else:
        image.save(img_buffer, format="PNG")

    img_buffer.seek(0)

    st.download_button(
        label=f"📥 下载 {new_filename}",
        data=img_buffer.getvalue(),
        file_name=new_filename,
        mime=f"image/{output_format.lower()}",
    )


def download_batch_images():
    """批量下载图片"""
    settings = st.session_state.watermark_settings
    output_format = st.session_state.get("output_format", "JPEG")

    # 创建ZIP文件
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, uploaded_file in enumerate(st.session_state.uploaded_images):
            # 处理图片
            image = Image.open(uploaded_file)
            if settings["type"] == "text":
                watermarked = apply_text_watermark(image, settings)
            else:
                watermarked = apply_image_watermark(image, settings)

            # 生成文件名
            name_base = Path(uploaded_file.name).stem
            extension = ".jpg" if output_format == "JPEG" else ".png"

            naming_option = st.session_state.get("naming_option", "添加后缀")
            affix_text = st.session_state.get("affix_text", "_watermarked")

            if naming_option == "保留原名":
                new_filename = name_base + extension
            elif naming_option == "添加前缀":
                new_filename = affix_text + name_base + extension
            else:  # 添加后缀
                new_filename = name_base + affix_text + extension

            # 保存到ZIP
            img_buffer = io.BytesIO()
            if output_format == "JPEG":
                quality = st.session_state.get("jpeg_quality", 95)
                watermarked.save(img_buffer, format="JPEG", quality=quality)
            else:
                watermarked.save(img_buffer, format="PNG")

            zip_file.writestr(new_filename, img_buffer.getvalue())

    zip_buffer.seek(0)

    st.download_button(
        label="📦 下载批量处理结果.zip",
        data=zip_buffer.getvalue(),
        file_name="watermarked_images.zip",
        mime="application/zip",
    )


def reset_settings():
    """重置设置"""
    st.session_state.watermark_settings = {
        "type": "text",
        "text": "水印文本",
        "font_size": 24,
        "font_color": "#000000",
        "opacity": 80,
        "position": "右下",
        "custom_x": 0,
        "custom_y": 0,
        "rotation": 0,
        "bold": False,
        "italic": False,
        "shadow": False,
        "outline": False,
        "image_path": None,
        "image_scale": 50,
        "image_opacity": 80,
    }
    st.success("✅ 设置已重置")
    st.experimental_rerun()


def main():
    """主函数"""
    st.set_page_config(
        page_title="照片水印工具",
        page_icon="🖼️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 初始化
    init_session_state()

    # 创建界面
    create_sidebar()
    create_watermark_settings()
    create_main_content()

    # 添加页脚
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray;'>
        🖼️ 照片水印工具 | 使用Streamlit构建
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
