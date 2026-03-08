# 全能 AI 助手

基于 Agent 模式的全能 AI 问答平台。一个入口、一个对话框，AI 自动判断问题领域，自主选择工具搜索和回答。

通过 `knowledge/` 目录下的 YAML 文件配置知识域，新增知识域只需添加 YAML 文件并重启，无需改代码。

## 快速启动

### 本地运行

```bash
export ANTHROPIC_AUTH_TOKEN="your-token"
cd project/example/mdschat
bash start.sh
```

打开 http://localhost:5001/mds/chat

### Docker 运行

```bash
export ANTHROPIC_AUTH_TOKEN="your-token"
cd project/example/mdschat
docker-compose up -d
```

## 配置

所有配置集中在 `config.yaml`：

```yaml
api:
  base_url: "http://coding.whup.com/"   # API 代理地址
  api_key: ""                            # 密钥（环境变量 ANTHROPIC_AUTH_TOKEN 优先）
  model: "claude-sonnet-4-5-20250929"    # 模型名称
  max_tokens: 4096                       # 单次回复最大 token
  max_iterations: 20                     # Agent 最大工具调用轮数

server:
  host: "0.0.0.0"
  port: 5001

tools:
  max_output_length: 15000               # 工具结果最大字符数
  max_display_length: 2000               # 前端展示的工具结果最大字符数
```

### 切换模型

编辑 `config.yaml` 中的 `api.model`，或通过环境变量覆盖：

```bash
export ANTHROPIC_MODEL="claude-haiku-4-5-20251001"
```

| 模型 | 说明 |
|------|------|
| `claude-sonnet-4-5-20250929` | 推荐，性价比高 |
| `claude-sonnet-4-6` | 最新 sonnet |
| `claude-haiku-4-5-20251001` | 最快，适合简单问题 |
| `claude-opus-4-5-20251101` | 最强，适合复杂分析 |

优先级：环境变量 > config.yaml

## 新增知识域

### 手动创建

1. 拷贝 `knowledge/_template/` 目录，重命名为知识域英文名（如 `knowledge/my_domain/`）
2. 将相关资料（源码、文档、配置等）拷贝到 `data/` 下
3. 编辑 `domain.yaml`，填写名称、描述、prompt 等字段
4. 重启服务生效

### 用 AI 自动生成

项目提供了 `AI_GUIDE.md`，这是一份 AI 工作指令。将它加载到任意 AI 助手（如 Claude、Cursor、Kiro 等）的上下文中，然后告诉 AI 你的源码/文档路径，AI 会自动完成：

1. 扫描分析文件内容和结构
2. 将所有资料整理拷贝到 `data/` 目录
3. 生成 `domain.yaml` 配置（包含 prompt 和示例问题）

使用方式：

```
# 在 AI 助手中加载指南后，直接对话即可
"帮我用 /path/to/src 和 /path/to/doc 创建一个 xxx 知识域"
```

AI 会按照指南中的流程自动创建完整的知识域目录，重启服务即可使用。

## 项目结构

```
knowledge-chat/
├── app.py                  # Flask 主应用
├── agent_engine.py         # Agent 引擎（知识域加载 + 工具 + API 调用）
├── config.yaml             # 全局配置
├── AI_GUIDE.md             # AI 生成知识域的工作指南
├── start.sh                # 启动脚本
├── requirements.txt        # Python 依赖
├── Dockerfile
├── docker-compose.yml
├── knowledge/              # 知识域目录
│   ├── _template/          # 模板（不会被引擎加载）
│   │   ├── domain.yaml
│   │   └── data/
│   ├── mds_interface/      # 示例：行情接口知识域
│   │   ├── domain.yaml
│   │   └── data/           # 该域的所有资料（已 gitignore）
│   └── mds_ops/            # 示例：行情运维知识域
│       ├── domain.yaml
│       └── data/
└── templates/
    └── chat.html           # 聊天页面
```

## 工具集

| 工具 | 功能 |
|------|------|
| search | 搜索关键词，返回匹配行及上下文 |
| read_file | 读取文件内容，支持行范围 |
| write_file | 写入/创建文件 |
| list_files | 列出目录文件 |
| glob | 按模式匹配文件路径 |
| bash | 执行 shell 命令 |
| web_fetch | 抓取网页内容 |
| run_python | 执行 Python 代码，可用于数据库查询和数据分析 |

### 扩展工具

工具定义在 `agent_engine.py` 的 `TOOLS` 列表中，执行逻辑在 `exec_tool()` 函数中。添加新工具只需：

1. 在 `TOOLS` 列表中添加工具定义（name、description、input_schema）
2. 在 `exec_tool()` 中添加对应的 `elif` 分支
