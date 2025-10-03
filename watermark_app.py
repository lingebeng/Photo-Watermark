"""
照片水印工具 - Streamlit版本
支持文本和图片水印，配置管理，批量处理等功能
"""

import io
import os
import platform
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont


def get_font_with_chinese_support(font_size, font_family="微软雅黑"):
    """获取支持中文的字体"""

    # 中文字体映射表
    font_map = {
        "微软雅黑": ["msyh.ttc", "msyh.ttf", "Microsoft YaHei"],
        "宋体": ["simsun.ttc", "simsun.ttf", "SimSun"],
        "黑体": ["simhei.ttf", "SimHei"],
        "楷体": ["simkai.ttf", "KaiTi"],
        "仿宋": ["simfang.ttf", "FangSong"],
        "Arial": ["arial.ttf", "Arial"],
        "Times New Roman": ["times.ttf", "Times New Roman"],
        "Helvetica": ["helvetica.ttf", "Helvetica"],
    }

    # 不同系统的字体路径
    if platform.system() == "Windows":
        font_dirs = [
            "C:/Windows/Fonts/",
            os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/"),
        ]
    elif platform.system() == "Darwin":  # macOS
        font_dirs = [
            "/System/Library/Fonts/",
            "/Library/Fonts/",
            os.path.expanduser("~/Library/Fonts/"),
        ]
    else:  # Linux
        font_dirs = [
            "/usr/share/fonts/",
            "/usr/local/share/fonts/",
            os.path.expanduser("~/.fonts/"),
            "/usr/share/fonts/truetype/dejavu/",
            "/usr/share/fonts/truetype/liberation/",
            "/usr/share/fonts/opentype/noto/",
            "/usr/share/fonts/truetype/noto/",
        ]

    # 尝试加载指定字体
    font_names = font_map.get(font_family, ["arial.ttf"])

    for font_name in font_names:
        # 首先尝试系统字体路径
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                font_path = os.path.join(font_dir, font_name)
                if os.path.exists(font_path):
                    try:
                        return ImageFont.truetype(font_path, font_size)
                    except Exception:
                        continue

        # 尝试直接使用字体名称（系统可能会自动找到）
        try:
            return ImageFont.truetype(font_name, font_size)
        except Exception:
            continue

    # 如果是中文字体失败，尝试常见的中文字体
    if font_family in ["微软雅黑", "宋体", "黑体", "楷体", "仿宋"]:
        common_chinese_fonts = [
            # Windows中文字体
            "msyh.ttc",
            "msyh.ttf",
            "simsun.ttc",
            "simsun.ttf",
            "simhei.ttf",
            # Linux中文字体
            "NotoSansCJK-Regular.ttc",
            "NotoSerifCJK-Regular.ttc",
            "WenQuanYi Micro Hei",
            "WenQuanYi Zen Hei",
            "DejaVu Sans",
            "Liberation Sans",
        ]

        for font_name in common_chinese_fonts:
            for font_dir in font_dirs:
                if os.path.exists(font_dir):
                    # 在目录中搜索包含字体名的文件
                    try:
                        for file in os.listdir(font_dir):
                            if font_name.lower() in file.lower():
                                font_path = os.path.join(font_dir, file)
                                try:
                                    return ImageFont.truetype(font_path, font_size)
                                except Exception:
                                    continue
                    except Exception:
                        continue

            # 尝试直接加载
            try:
                return ImageFont.truetype(font_name, font_size)
            except Exception:
                continue

    # 最后的备选方案：使用默认字体
    try:
        # 尝试使用DejaVu Sans（通常支持更多字符）
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        pass

    try:
        # 使用PIL默认字体
        return ImageFont.load_default()
    except Exception:
        # 如果连默认字体都加载失败，创建一个基本字体
        return ImageFont.load_default()


def init_session_state():
    """初始化session state"""
    if "uploaded_images" not in st.session_state:
        st.session_state.uploaded_images = (
            []
        )  # 存储格式: [{'name': str, 'content': bytes, 'type': str}, ...]
    if "current_image_index" not in st.session_state:
        st.session_state.current_image_index = 0

    # 确保当前图片索引在有效范围内
    if (
        st.session_state.uploaded_images
        and st.session_state.current_image_index
        >= len(st.session_state.uploaded_images)
    ):
        st.session_state.current_image_index = 0
    if "watermark_settings" not in st.session_state:
        st.session_state.watermark_settings = {
            "type": "text",
            "text": "水印文本",
            "font_size": 24,
            "font_family": "微软雅黑",
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
        "� 选择或拖拽图片文件",
        type=["png", "jpg", "jpeg", "bmp", "tiff"],
        accept_multiple_files=True,
        key="file_uploader",
        help="支持拖拽上传",
    )

    if uploaded_files:
        # 将文件内容转换为字节存储，避免Streamlit文件对象失效问题
        file_data_list = []
        for file in uploaded_files:
            file_data = {
                "name": file.name,
                "content": file.getvalue(),
                "type": file.type,
            }
            file_data_list.append(file_data)

        st.session_state.uploaded_images = file_data_list
        st.sidebar.success(f"✅ 已导入 {len(uploaded_files)} 张图片")

        # 添加清空按钮
        if st.sidebar.button("🗑️ 清空所有图片", type="secondary"):
            st.session_state.uploaded_images = []
            st.session_state.current_image_index = 0
            st.rerun()

    # 图片列表
    if st.session_state.uploaded_images:
        st.sidebar.markdown("---")
        st.sidebar.subheader(f"📋 图片列表 ({len(st.session_state.uploaded_images)}张)")

        # 图片选择器 - 与主界面按钮状态同步
        image_names = [f["name"] for f in st.session_state.uploaded_images]

        # 确保当前选择的索引在有效范围内
        if st.session_state.current_image_index >= len(
            st.session_state.uploaded_images
        ):
            st.session_state.current_image_index = 0

        selected_index = st.sidebar.selectbox(
            "选择当前预览图片",
            range(len(image_names)),
            format_func=lambda x: f"{x+1}. {image_names[x]}",
            index=st.session_state.current_image_index,  # 使用当前索引作为默认值
            key="image_selector",
        )

        # 只有当选择器的值发生变化时才更新状态
        if selected_index != st.session_state.current_image_index:
            st.session_state.current_image_index = selected_index
            st.rerun()

        # 当前图片信息
        current_file_data = st.session_state.uploaded_images[selected_index]
        try:
            # 从存储的字节数据创建图片
            current_image = Image.open(io.BytesIO(current_file_data["content"]))

            # 显示缩略图
            thumbnail = current_image.copy()
            thumbnail.thumbnail((150, 150), Image.Resampling.LANCZOS)
            st.sidebar.image(thumbnail, caption=f"预览: {current_file_data['name']}")

            # 图片详细信息
            file_size = len(current_file_data["content"]) / 1024  # KB
            st.sidebar.info(
                f"""
            📁 **文件信息:**
            • 文件名: {current_file_data['name']}
            • 尺寸: {current_image.size[0]} × {current_image.size[1]} 像素
            • 格式: {current_image.format}
            • 颜色模式: {current_image.mode}
            • 文件大小: {file_size:.1f} KB
            """
            )

        except Exception as e:
            st.sidebar.error(f"❌ 无法加载图片: {current_file_data['name']}")
            st.sidebar.caption(f"错误: {str(e)}")


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

    # 字体选择
    font_options = [
        "微软雅黑",
        "宋体",
        "Arial",
        "Times New Roman",
        "Helvetica",
        "黑体",
        "楷体",
        "仿宋",
    ]

    font_family = st.sidebar.selectbox(
        "字体",
        font_options,
        index=(
            0
            if st.session_state.watermark_settings.get("font_family", "微软雅黑")
            not in font_options
            else font_options.index(
                st.session_state.watermark_settings.get("font_family", "微软雅黑")
            )
        ),
        key="font_family",
    )
    st.session_state.watermark_settings["font_family"] = font_family

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
        # 将水印图片也转换为字节存储
        watermark_data = {
            "name": watermark_image.name,
            "content": watermark_image.getvalue(),
            "type": watermark_image.type,
        }
        st.session_state.watermark_settings["image_path"] = watermark_data
        st.sidebar.success("水印图片已选择")

        # 显示水印图片预览
        try:
            watermark_img = Image.open(io.BytesIO(watermark_data["content"]))
            st.sidebar.image(watermark_img, caption="水印图片预览", width=200)
        except Exception as e:
            st.sidebar.error(f"❌ 无法加载水印图片: {str(e)}")

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
        "自定义",
    ]

    position = st.sidebar.selectbox(
        "预设位置",
        position_options,
        index=position_options.index(st.session_state.watermark_settings["position"]),
        key="position_select",
    )
    st.session_state.watermark_settings["position"] = position

    # 自定义位置（只在选择自定义时显示）
    if position == "自定义":
        st.sidebar.markdown("#### 🎯 自定义位置")
        st.sidebar.caption("左上角为原点 (0,0)")

        col1, col2 = st.sidebar.columns(2)
        with col1:
            custom_x = st.number_input(
                "X坐标",
                min_value=0,
                value=st.session_state.watermark_settings["custom_x"],
                key="custom_x",
            )
            st.session_state.watermark_settings["custom_x"] = custom_x
        with col2:
            custom_y = st.number_input(
                "Y坐标",
                min_value=0,
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

    # 如果选择自定义位置，直接使用自定义坐标
    if position == "自定义":
        return (custom_x, custom_y)

    # 预设位置映射
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

    return position_map.get(position, (margin, margin))


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

    # 加载支持中文的字体
    font = get_font_with_chinese_support(
        settings["font_size"], settings.get("font_family", "微软雅黑")
    )

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

    # 如果需要旋转，创建单独的文本图像
    if settings["rotation"] != 0:
        # 创建适当大小的文本图像
        text_img_size = (text_width + 40, text_height + 40)  # 留出边距
        text_img = Image.new("RGBA", text_img_size, (255, 255, 255, 0))
        text_draw = ImageDraw.Draw(text_img)
        text_pos = (20, 20)  # 居中放置

        # 在文本图像上绘制特效和文本
        if settings["shadow"]:
            shadow_offset = max(2, settings["font_size"] // 12)
            shadow_pos = (text_pos[0] + shadow_offset, text_pos[1] + shadow_offset)
            text_draw.text(
                shadow_pos, settings["text"], font=font, fill=(0, 0, 0, alpha // 2)
            )

        if settings["outline"]:
            outline_width = max(1, settings["font_size"] // 20)
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        outline_pos = (text_pos[0] + dx, text_pos[1] + dy)
                        text_draw.text(
                            outline_pos,
                            settings["text"],
                            font=font,
                            fill=(255, 255, 255, alpha),
                        )

        # 绘制主要文本
        text_draw.text(text_pos, settings["text"], font=font, fill=text_color)

        # 旋转文本图像
        text_img = text_img.rotate(
            settings["rotation"], expand=True, fillcolor=(255, 255, 255, 0)
        )

        # 计算旋转后的位置调整
        rotated_size = text_img.size
        adjusted_position = (
            position[0] - (rotated_size[0] - text_width) // 2,
            position[1] - (rotated_size[1] - text_height) // 2,
        )

        # 将旋转后的文本粘贴到主图像
        watermarked.paste(text_img, adjusted_position, text_img)
    else:
        # 直接在覆盖层上绘制（无旋转）
        if settings["shadow"]:
            shadow_offset = max(2, settings["font_size"] // 12)
            shadow_pos = (position[0] + shadow_offset, position[1] + shadow_offset)
            draw.text(
                shadow_pos, settings["text"], font=font, fill=(0, 0, 0, alpha // 2)
            )

        if settings["outline"]:
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

    return watermarked.convert("RGB")


def apply_image_watermark(image, settings):
    """应用图片水印"""
    if not settings["image_path"]:
        return image

    watermarked = image.copy()
    if watermarked.mode != "RGBA":
        watermarked = watermarked.convert("RGBA")

    # 加载水印图片
    watermark_data = settings["image_path"]
    if isinstance(watermark_data, dict):
        # 新格式：从字节数据加载
        watermark_img = Image.open(io.BytesIO(watermark_data["content"]))
    else:
        # 旧格式兼容：直接从文件对象加载
        if hasattr(watermark_data, "getvalue"):
            watermark_data.seek(0)
        watermark_img = Image.open(watermark_data)
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
        # 创建主界面的拖拽区域
        st.markdown(
            """
            <style>
            .main-upload-area {
                border: 3px dashed #ff4b4b;
                border-radius: 15px;
                padding: 40px;
                text-align: center;
                background: linear-gradient(135deg, #f0f2f6 0%, #e8eaf6 100%);
                margin: 20px 0;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                transition: all 0.3s ease;
            }
            .main-upload-area:hover {
                border-color: #ff6b6b;
                box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
                transform: translateY(-2px);
            }
            .main-upload-icon {
                font-size: 72px;
                color: #ff4b4b;
                margin-bottom: 20px;
                animation: bounce 2s infinite;
            }
            @keyframes bounce {
                0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
                40% { transform: translateY(-10px); }
                60% { transform: translateY(-5px); }
            }
            .main-upload-title {
                color: #262730;
                font-size: 28px;
                font-weight: bold;
                margin-bottom: 15px;
            }
            .main-upload-text {
                color: #666;
                font-size: 18px;
                margin-bottom: 20px;
            }
            .main-upload-hint {
                color: #888;
                font-size: 14px;
                font-style: italic;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # 使用步骤
        st.markdown("### 📋 使用步骤")
        step_col1, step_col2, step_col3, step_col4 = st.columns(4)

        with step_col1:
            st.markdown("**1️⃣ 导入图片**\n上传一张或多张图片")
        with step_col2:
            st.markdown("**2️⃣ 配置水印**\n设置文本或图片水印")
        with step_col3:
            st.markdown("**3️⃣ 调整位置**\n选择水印位置和效果")
        with step_col4:
            st.markdown("**4️⃣ 导出结果**\n下载处理后的图片")

        return

    # 显示已导入图片的网格缩略图
    st.subheader(f"📸 已导入图片 ({len(st.session_state.uploaded_images)}张)")

    # 添加固定高度的网格样式
    st.markdown(
        """
        <style>
        /* 设置列容器固定高度 */
        .stColumn {
            height: 300px !important;
        }
        
        /* 图片容器样式 */
        div[data-testid="column"] {
            display: flex !important;
            flex-direction: column !important;
            height: 300px !important;
            padding: 8px !important;
            border: 1px solid #e0e6ed !important;
            border-radius: 12px !important;
            background: #f8f9fa !important;
            margin: 4px !important;
        }
        
        div[data-testid="column"].selected {
            border-color: #2196f3 !important;
            background: #e3f2fd !important;
            box-shadow: 0 4px 12px rgba(33, 150, 243, 0.2) !important;
        }
        
        /* 图片区域固定高度 */
        .stImage {
            flex: 1 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            margin: 0 !important;
            padding: 8px 0 !important;
            max-height: 180px !important;
            overflow: hidden !important;
        }
        
        .stImage img {
            border-radius: 8px !important;
            transition: all 0.3s ease !important;
            max-width: 100% !important;
            max-height: 160px !important;
            object-fit: contain !important;
        }
        
        .stImage:hover img {
            transform: scale(1.05) !important;
        }
        
        /* 标题文字区域 */
        .stImage figcaption {
            font-size: 12px !important;
            font-weight: 500 !important;
            text-align: center !important;
            margin-top: 8px !important;
            height: 30px !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
        }
        
        /* 按钮区域固定高度 */
        .stButton {
            margin-top: auto !important;
            margin-bottom: 0 !important;
            height: 40px !important;
        }
        
        .stButton > button {
            width: 100% !important;
            height: 36px !important;
            border-radius: 8px !important;
            font-size: 12px !important;
            font-weight: 600 !important;
        }
        
        /* 错误状态样式 */
        .stAlert {
            margin: 8px 0 !important;
            padding: 8px !important;
            font-size: 12px !important;
        }
        </style>
    """,
        unsafe_allow_html=True,
    )

    # 创建简洁的图片网格
    cols_per_row = 4
    rows = (len(st.session_state.uploaded_images) + cols_per_row - 1) // cols_per_row

    for row in range(rows):
        cols = st.columns(cols_per_row, gap="medium")
        for col_idx in range(cols_per_row):
            img_idx = row * cols_per_row + col_idx
            if img_idx < len(st.session_state.uploaded_images):
                with cols[col_idx]:
                    file_data = st.session_state.uploaded_images[img_idx]
                    try:
                        # 从字节数据创建图片
                        img = Image.open(io.BytesIO(file_data["content"]))
                        # 创建统一高度的缩略图
                        original_width, original_height = img.size
                        target_height = 150
                        # 计算保持宽高比的新宽度
                        aspect_ratio = original_width / original_height
                        new_width = int(target_height * aspect_ratio)

                        # 调整图片尺寸到统一高度
                        thumbnail = img.resize(
                            (new_width, target_height), Image.Resampling.LANCZOS
                        )

                        # 判断是否为当前选中的图片
                        is_current = img_idx == st.session_state.current_image_index

                        # 文件名显示在头部并居中
                        file_name = file_data["name"][:18] + (
                            "..." if len(file_data["name"]) > 18 else ""
                        )

                        # 图片居中显示区域
                        st.markdown(
                            '<div style="text-align: center; margin-bottom: 8px;">',
                            unsafe_allow_html=True,
                        )

                        # 显示缩略图（无caption，caption已在头部）
                        with st.container():
                            st.image(thumbnail, use_container_width=False)

                        st.markdown("</div>", unsafe_allow_html=True)
                        status_icon = "✅" if is_current else "⚪"

                        st.markdown(
                            f"""
                            <div style="
                                text-align: center;
                                margin-bottom: 8px;
                                padding: 6px 4px;
                                background: {'#e3f2fd' if is_current else '#f8f9fa'};
                                border-radius: 6px;
                                font-size: 13px;
                                color: {'#1976d2' if is_current else '#555'};
                                font-weight: {'700' if is_current else '600'};
                                border: 1px solid {'#2196f3' if is_current else '#e0e0e0'};
                                box-shadow: {'0 2px 4px rgba(33,150,243,0.2)' if is_current else '0 1px 2px rgba(0,0,0,0.1)'};
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                            ">
                                {status_icon} {file_name}
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )

                    except Exception as e:
                        # 简化的错误显示
                        st.error(f"❌ 加载失败{e}")
                        st.caption(
                            f"{file_data['name'][:20]}{'...' if len(file_data['name']) > 20 else ''}"
                        )

    st.markdown("---")

    # 获取当前图片
    try:
        current_file_data = st.session_state.uploaded_images[
            st.session_state.current_image_index
        ]

        # 从存储的字节数据创建图片
        current_image = Image.open(io.BytesIO(current_file_data["content"]))

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

    except Exception as e:
        st.error(
            f"❌ 无法加载当前图片: {current_file_data['name'] if 'current_file_data' in locals() else '未知文件'}"
        )
        st.error(f"错误详情: {str(e)}")

        # 提供解决建议
        st.info("💡 **解决建议:**")

        # 添加重新上传按钮
        if st.button("🔄 清空并重新上传", type="primary"):
            st.session_state.uploaded_images = []
            st.session_state.current_image_index = 0
            st.rerun()
        return

    # 导出按钮
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 下载当前图片", width="stretch"):
            download_single_image(watermarked_image, current_file_data["name"])

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
        for i, file_data in enumerate(st.session_state.uploaded_images):
            try:
                # 处理图片
                image = Image.open(io.BytesIO(file_data["content"]))
                if settings["type"] == "text":
                    watermarked = apply_text_watermark(image, settings)
                else:
                    watermarked = apply_image_watermark(image, settings)
            except Exception as e:
                st.error(f"❌ 处理图片 {file_data['name']} 时出错: {str(e)}")
                continue

            # 生成文件名
            name_base = Path(file_data["name"]).stem
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
        "font_family": "微软雅黑",
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
    st.rerun()


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
