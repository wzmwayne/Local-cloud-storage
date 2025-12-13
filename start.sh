#!/bin/bash

# 文件传输应用启动脚本

echo "🚀 启动文件传输应用..."

# 检查Python依赖
echo "📦 检查依赖..."
pip install -r requirements.txt > /dev/null 2>&1

# 启动应用
echo "🌐 启动服务器..."
python app.py