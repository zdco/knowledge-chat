#!/bin/bash
# 全能 AI 助手 - 启动脚本
set -e

cd "$(dirname "$0")"

# 创建虚拟环境并安装依赖
VENV_DIR=".venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    rm -rf "$VENV_DIR"
    # 检查 ensurepip 是否可用（venv 创建依赖它），不可用则自动安装
    if ! python3 -c "import ensurepip" &>/dev/null; then
        echo "检测到缺少 python3-venv，正在自动安装..."
        PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        sudo apt-get update -qq && sudo apt-get install -y -qq "python${PY_VERSION}-venv"
    fi
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

if [ "$1" = "-d" ]; then
    echo "后台启动全能 AI 助手..."
    nohup python app.py > output.log 2>&1 &
    echo "PID: $!, 日志: output.log"
else
    echo "启动全能 AI 助手..."
    python app.py
fi
