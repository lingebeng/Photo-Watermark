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
