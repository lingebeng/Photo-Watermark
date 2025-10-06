# 照片水印工具

<div align="center">

[![English](https://img.shields.io/badge/lang-English-blue)](README.md)
[![中文](https://img.shields.io/badge/lang-中文-red)](README_CN.md)

</div>

## 📸 项目简介

为照片添加水印的工具。

## 🛠 安装步骤

```bash
# 安装依赖
uv sync
source .venv/bin/activate

# 安装 git 钩子脚本
pre-commit install
```

## 📝 开发说明

### dev-00 需求

完成一个命令行程序

用户输入一个图片文件路径。

读取该路径下所有文件的 exif 信息中的拍摄时间信息，选取年月日，作为水印。

用户可以设置字体大小、颜色和在图片上的位置（例如，左上角、居中、右下角）。

程序将文本水印绘制到图片上，并保存为新的图片文件，保存在原目录名_watermark的新目录下，这个目录作为原目录的子目录。

#### 参数解释

```text
必选参数
IMAGE_DIRECTORY
需要加水印的图片所在目录路径。

可选参数
--font-size, -s
水印字体大小（默认：80）

--color, -c
水印文字颜色（默认：red）

--position, -p
水印在图片上的位置
可选值：top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right
默认：bottom-right

--use-file-date
当图片没有EXIF日期时，使用文件的修改时间作为水印日期

--default-date
当没有EXIF和文件日期时，使用指定的默认日期（格式：YYYY-MM-DD）
```

#### 命令行运行

```bash
uv run watermark_cli.py test --font-size 100 --color gray --position center
```

### dev-01 需求

水印文件本地应用（Windows 或 MacOS)：

1. 文件处理
1.1导入图片
支持单张图片拖拽或通过文件选择器导入。
支持批量导入，可一次性选择多张图片或直接导入整个文件夹。
在界面上显示已导入图片的列表（缩略图和文件名）。
1.2支持格式
输入格式：必须支持主流格式，如 JPEG, PNG。强烈建议支持 BMP, TIFF。PNG格式必须支持透明通道。
输出格式：用户可选择输出为 JPEG 或 PNG。
1.3导出图片
用户可指定一个输出文件夹。为防止覆盖原图，默认禁止导出到原文件夹。
提供导出文件命名规则选项：
    保留原文件名。
    添加自定义前缀（如 wm_）。
    添加自定义后缀（如 _watermarked）。
对于 JPEG 格式，提供图片质量（压缩率）调节滑块（0-100）。（可选高级功能）
导出时允许用户调整图片尺寸（如按宽度、高度或百分比缩放）。（可选高级功能）
2. 水印类型
2.1文本水印
内容：用户可自定义输入任意文本。
字体：可选择系统已安装的字体、字号、粗体、斜体。（可选高级功能）
颜色：提供调色板让用户选择字体颜色。（可选高级功能）
透明度：可调节文本的透明度（0-100%）。
样式：可添加阴影或描边效果，以增强在复杂背景下的可读性。（可选高级功能）
2.2图片水印（可选高级功能）
用户可从本地选择一张图片（如Logo）作为水印。
必须支持带透明通道的 PNG 图片。
缩放：可按比例或自由调整图片水印的大小。
透明度：可调节图片水印的整体透明度（0-100%）。
3. 水印布局与样式
3.1实时预览：所有对水印的调整都应在主预览窗口中实时显示效果。用户可以点击图片列表切换预览不同的图片。
3.2位置
    预设位置：提供九宫格布局（四角、正中心），用户可一键将水印放置在这些位置。
    手动拖拽：用户可以直接在预览图上通过鼠标拖拽水印到任意位置。
3.3旋转：提供一个滑块或输入框，允许用户以任意角度旋转水印。（可选高级功能）
4. 配置管理
4.1 水印模板：
用户可以将当前的水印设置（包括水印内容、字体、颜色、位置、大小、透明度等所有参数）保存为一个模板。
用户可以加载、管理和删除已保存的模板。
程序启动时可自动加载上一次关闭时的设置或一个默认模板。
高级功能请尽可能完成，不作为必须内容。

#### 本地 py文件运行说明

```bash
streamlit run watermark_app.py
# 打开：http://localhost:8501
```

#### Windows Pyinstaller 打包说明

```bash
# 允许本地脚本运行
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
# 激活 uv 虚拟环境(首先 uv sync)
.venv\Scripts\activate
# 生成 run.spec文件
pyinstaller --onefile --additional-hooks-dir=./hooks run.py --clean
# 生成 run.exe文件
pyinstaller run.spec --clean
```
