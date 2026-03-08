#!/bin/bash
# 全能 AI 助手 - 启动脚本
set -e

cd "$(dirname "$0")"

# 检查环境变量
if [ -z "$ANTHROPIC_AUTH_TOKEN" ]; then
    echo "请先设置环境变量："
    echo '  export ANTHROPIC_BASE_URL="http://coding.whup.com/"'
    echo '  export ANTHROPIC_AUTH_TOKEN="your-token"'
    exit 1
fi

# 创建虚拟环境并安装依赖
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "启动全能 AI 助手..."
echo "访问地址: http://localhost:5001/chat"
python app.py
