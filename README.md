# 全能 AI 助手

基于 Agent 模式的全能 AI 问答平台。一个入口、一个对话框，AI 自动判断问题领域，自主选择工具搜索和回答。

通过 `knowledge/` 目录下的 YAML 文件配置知识域，新增知识域只需添加 YAML 文件，服务自动热加载，无需改代码。

## 功能特性

- **Agent 模式多工具调用** — AI 自主选择搜索、读文件、执行代码等工具，多轮迭代直到找到答案
- **知识域热加载** — 新增或修改 `domain.yaml` 后自动生效，无需重启服务
- **AI 学习记忆** — AI 将有价值的结论写入 memory 笔记，后续通过搜索复用，实现自我进化
- **对话分享** — 一键生成固定链接，对方打开即可只读查看完整对话
- **Confluence 自动转换** — 配置 `confluence_zip` 字段后，启动时自动将 Confluence HTML 导出包转为 Markdown
- **多 API 格式兼容** — 同时支持 Anthropic 和 OpenAI API 格式，根据 `base_url` 自动检测或手动指定
- **完整日志** — console + 文件双输出，按天轮转，每条日志携带 request_id 可追踪全链路

## 快速启动

### 使用启动脚本（推荐）

```bash
export ANTHROPIC_AUTH_TOKEN="your-token"
bash start.sh
```

`start.sh` 会自动创建虚拟环境、安装依赖并启动服务。

### 手动安装

要求 Python 3.10+

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_AUTH_TOKEN="your-token"
python app.py
```

打开 http://localhost:5001/chat

### Docker 运行

```bash
docker-compose up -d
```

环境变量说明：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_AUTH_TOKEN` | API 密钥（必填） | — |
| `ANTHROPIC_BASE_URL` | API 代理地址 | `http://coding.whup.com/` |
| `ANTHROPIC_MODEL` | 模型名称（覆盖 config.yaml） | — |

## 配置

所有配置集中在 `config.yaml`：

```yaml
api:
  # 代理地址（含 /v1 自动走 OpenAI 格式，否则走 Anthropic 格式）
  base_url: "http://coding.whup.com/v1"
  api_key: ""                            # 密钥（环境变量 ANTHROPIC_AUTH_TOKEN 优先）
  model: "MiniMax-M2.5"                  # 模型名称
  max_tokens: 4096                       # 单次回复最大 token
  max_iterations: 50                     # Agent 最大工具调用轮数
  # API 格式："anthropic" 或 "openai"，不设置则根据 base_url 是否含 /v1 自动判断
  # 非 Claude 模型建议用 openai 格式
  # api_format: "openai"

server:
  host: "0.0.0.0"
  port: 5001

tools:
  max_output_length: 15000               # 工具结果最大字符数
  max_display_length: 2000               # 前端展示的工具结果最大字符数
  python_timeout: 300                    # run_python 超时时间（秒）

logging:
  level: "INFO"
  file: "logs/app.log"
  backup_days: 30
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

### API 格式

支持两种 API 格式：

- **Anthropic 格式** — 适用于 Claude 系列模型
- **OpenAI 格式** — 适用于 GLM、MiniMax 等第三方模型

自动检测逻辑：`base_url` 包含 `/v1` 时自动使用 OpenAI 格式，否则使用 Anthropic 格式。也可通过 `api_format` 手动指定。

## 新增知识域

### 手动创建

1. 拷贝 `knowledge/_template/` 目录，重命名为知识域英文名（如 `knowledge/my_domain/`）
2. 将相关资料（源码、文档、配置等）拷贝到 `data/` 下
3. 编辑 `domain.yaml`，填写名称、描述、prompt 等字段
4. 服务自动热加载生效

支持 Confluence 导出包：在 `domain.yaml` 中配置 `confluence_zip` 字段指向 ZIP 文件路径，服务启动时自动转换为 Markdown。

支持数据库查询：在 `domain.yaml` 中配置 `databases` 字段，AI 可自动生成 Python 代码查询数据库。

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

AI 会按照指南中的流程自动创建完整的知识域目录，热加载后即可使用。

## 项目结构

```
knowledge-chat/
├── app.py                    # Flask 主应用
├── agent_engine.py           # Agent 引擎（知识域加载 + 工具 + API 调用）
├── confluence_converter.py   # Confluence HTML → Markdown 转换器
├── config.yaml               # 全局配置
├── AI_GUIDE.md               # AI 生成知识域的工作指南
├── CHANGELOG.md              # 变更日志
├── CLAUDE.md                 # Claude Code 项目指令
├── start.sh                  # 启动脚本
├── requirements.txt          # Python 依赖
├── Dockerfile
├── docker-compose.yml
├── knowledge/                # 知识域目录
│   ├── _template/            # 模板（不会被引擎加载）
│   │   ├── domain.yaml
│   │   └── data/
│   ├── _memory/              # AI 全局学习记忆
│   └── <domain>/             # 各知识域
│       ├── domain.yaml
│       └── data/             # 该域的所有资料（已 gitignore）
├── templates/
│   ├── chat.html             # 聊天页面
│   └── share.html            # 分享只读页面
├── shares/                   # 分享数据（运行时生成）
└── logs/                     # 日志文件（运行时生成）
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
