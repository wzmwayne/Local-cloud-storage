#!/bin/bash

# 文件传输应用安装和启动脚本

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 1. 输出整个目录结构
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    文件传输应用 - 目录结构${NC}"
echo -e "${BLUE}========================================${NC}"
print_info "当前目录: $(pwd)"
print_info "目录内容:"
tree -a 2>/dev/null || find . -type f -o -type d | sort
echo ""

# 2. apt换源
print_info "开始配置apt源..."
if command -v apt &> /dev/null; then
    # 备份原始源
    if [ -f /data/data/com.termux/files/usr/etc/apt/sources.list ]; then
        cp /data/data/com.termux/files/usr/etc/apt/sources.list /data/data/com.termux/files/usr/etc/apt/sources.list.backup
        print_success "已备份原始源文件"
    fi
    
    # 使用清华源（Termux官方推荐）
    print_info "配置清华大学镜像源..."
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/termux/termux-packages-24 stable main" > /data/data/com.termux/files/usr/etc/apt/sources.list
    
    # 更新包列表
    print_info "更新包列表..."
    apt update && apt upgrade -y
    print_success "apt源配置完成"
else
    print_warning "未找到apt命令，跳过换源步骤"
fi

# 3. 安装Python、pip等依赖
print_info "开始安装Python和依赖..."

# 安装基础工具
print_info "安装基础工具..."
apt install -y curl wget git tree build-essential

# 安装Python
if ! command -v python &> /dev/null; then
    print_info "安装Python..."
    apt install -y python python-dev
else
    print_success "Python已安装: $(python --version)"
fi

# 安装pip
if ! command -v pip &> /dev/null; then
    print_info "安装pip..."
    apt install -y python-pip
else
    print_success "pip已安装: $(pip --version)"
fi

# 升级pip
print_info "升级pip..."
pip install --upgrade pip

# 安装系统级依赖
print_info "安装系统级依赖..."
apt install -y clang make pkg-config libffi-dev openssl-dev libjpeg-turbo-dev

# 安装Python依赖
if [ -f requirements.txt ]; then
    print_info "安装Python依赖包..."
    pip install -r requirements.txt
    print_success "Python依赖安装完成"
else
    print_error "未找到requirements.txt文件"
fi

# 创建必要的目录
print_info "创建必要的目录..."
mkdir -p uploads
mkdir -p certs

# 设置权限
print_info "设置文件权限..."
chmod +x start.sh
chmod 755 uploads
chmod 755 certs

# 检查安装
print_info "检查安装状态..."
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    安装状态检查${NC}"
echo -e "${BLUE}========================================${NC}"

# Python版本
if command -v python &> /dev/null; then
    print_success "Python: $(python --version)"
else
    print_error "Python未安装"
fi

# pip版本
if command -v pip &> /dev/null; then
    print_success "pip: $(pip --version)"
else
    print_error "pip未安装"
fi

# 检查Python模块
print_info "检查Python模块..."
python -c "
import sys
modules = ['flask', 'flask_socketio', 'qrcode', 'pillow']
for module in modules:
    try:
        __import__(module)
        print(f'✓ {module}')
    except ImportError:
        print(f'✗ {module} - 未安装')
"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}    安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
print_info "启动应用..."

# 启动应用
python app.py