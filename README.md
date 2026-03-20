# knowledge-chat

把团队的代码、文档、配置、数据库变成一个能对话的 AI 助手。问一句话，AI 自己搜代码、翻文档、查数据库，拼出完整答案。

不是又一个通用 AI Agent 框架。不做邮件、日历、消息自动化。只做一件事：**让团队知识可搜索、可对话、可沉淀**。

## 为什么需要它

企业内部的知识散落在各处，找答案比解决问题本身还难：

- 文档在 Confluence，代码在 GitLab，配置在运维手册，数据库结构在某个人的脑子里
- 新人一个问题要问三个人，老员工每天被重复问题打断
- 线上出了问题，查日志、查配置、查代码、查数据库，每一步都要切换工具
- 同样的问题上次有人排查过，但结论没有沉淀，下次还得重来

**解决思路：把所有知识喂给 AI，让任何人都能用自然语言直接问。**

## 和 OpenClaw 等通用 Agent 有什么不同

[OpenClaw](https://github.com/openclaw/openclaw) 是通用 AI Agent 框架，连接消息平台（WhatsApp/Telegram/Slack），执行各种自动化任务（发邮件、管日历、操作文件）。它解决的是"让 AI 帮你做事"。

knowledge-chat 解决的是完全不同的问题：**让 AI 帮你找答案**。

| | knowledge-chat | OpenClaw 等通用 Agent |
|---|---|---|
| **定位** | 团队知识问答 + 日志分析 | 通用任务自动化 |
| **数据源** | 你的代码、文档、配置、数据库 | 邮件、日历、消息、网页 |
| **核心能力** | 搜索代码、读文件、查数据库、分析日志 | 发消息、管文件、调 API、操作系统 |
| **部署方式** | 一个 Python 文件，改个 YAML 就能用 | 需要配置消息渠道、Skills、安全策略 |
| **上手成本** | 把资料丢进目录，写几行 YAML | 需要理解 Skills 体系、Channel 配置 |
| **知识沉淀** | AI 自动记忆有价值的结论，越用越聪明 | 无内置知识沉淀机制 |
| **适用场景** | 开发团队内部知识共享、故障排查 | 个人效率工具、跨平台自动化 |

简单说：OpenClaw 是你的私人助理，knowledge-chat 是你团队的技术大脑。

## 两种模式

### 知识域问答（默认）

把源码、文档、配置、数据库连接信息组织成"知识域"，AI 自动判断问题领域，搜索对应资料回答。

```
用户：交易网关的超时重试机制是怎么实现的？
AI：[搜索代码] [读取 RetryHandler.cpp] [搜索配置]
    超时重试在 RetryHandler.cpp:45 实现，采用指数退避策略...
```

### 日志分析

切换 `mode: log-analyzer`，变身故障排查助手。注册微服务信息后，AI 能分析日志、读源码、追踪依赖链，定位问题根因。

```
用户：行情网关今天下午 3 点开始数据延迟 [拖入 gateway.log.zip]
AI：[解压日志] [read_log: 发现 15 条 ERROR，集中在 15:02-15:05]
    [switch_service: 加载行情网关代码 v2.3.1]
    [search: 定位到 Decoder.cpp:234 解码超时]
    [trace_dependency: 行情网关 → data_server]

    初步分析：解码模块在 15:02 开始出现超时，根因是...
    需要确认：data_server 同时间段是否有异常？
```

支持拖拽上传日志、Ctrl+V 粘贴截图、压缩包自动解压。多人并发使用时通过 git worktree 隔离代码版本。

## 功能特性

- **Agent 多工具调用** — AI 自主选择搜索、读文件、执行代码等工具，多轮迭代直到找到答案
- **知识域热加载** — 新增或修改 YAML 后自动生效，无需重启
- **AI 学习记忆** — 有价值的结论自动沉淀到 memory，后续搜索复用，越用越聪明
- **日志分析** — 日志过滤、依赖链追踪、git worktree 代码版本隔离、多模态截图识别
- **文件上传** — 拖拽/粘贴/点击上传日志、压缩包、截图
- **对话分享** — 一键生成链接，对方打开即可查看完整对话
- **Confluence 导入** — 自动将 Confluence 导出包转为可搜索的 Markdown
- **数据库查询** — AI 自动生成 Python 代码查询 MySQL/Oracle
- **多模型兼容** — 支持 Claude、GPT、GLM、MiniMax 等，Anthropic/OpenAI 双格式

## 快速启动

```bash
# 方式一：启动脚本（自动创建虚拟环境、安装依赖）
./start.sh

# 方式二：手动
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AI_CHAT_API_KEY="your-key"
python app.py

# 方式三：Docker
docker-compose up -d
```

打开 http://localhost:5001/kchat/chat

## 配置

所有配置集中在 `config.yaml`：

```yaml
# 运行模式：knowledge（知识域问答，默认）或 log-analyzer（日志分析）
mode: knowledge

api:
  base_url: "https://api.example.com/v1"   # API 地址
  api_key: ""                               # 密钥（环境变量 AI_CHAT_API_KEY 优先）
  model: "claude-sonnet-4-20250514"         # 模型
  max_tokens: 4096
  max_iterations: 50

server:
  host: "0.0.0.0"
  port: 5001
  title: "全能 AI 助手"

tools:
  max_output_length: 15000
  max_display_length: 2000
  python_timeout: 300

logging:
  level: "INFO"
  file: "logs/app.log"
  backup_days: 30

# 日志分析模式专用（仅 mode: log-analyzer 时生效）
analyzer:
  services_config: "services.yaml"
  session_dir: "/data/sessions"
  worktree_base: "/data/worktrees"
  session_ttl: 86400
  max_upload_size: 104857600
```

环境变量（优先于 config.yaml）：

| 变量 | 说明 |
|------|------|
| `AI_CHAT_API_KEY` | API 密钥 |
| `AI_CHAT_BASE_URL` | API 地址 |
| `AI_CHAT_MODEL` | 模型名称 |

## 新增知识域

### 方式一：让 AI 自动生成

项目提供了 `AI_GUIDE.md` 工作指南，在对话中直接告诉 AI 你的资料路径：

```
"帮我用 /data/repos/gateway 创建一个行情网关知识域"
```

AI 会自动扫描代码结构、整理资料、生成配置，热加载后即可使用。

### 方式二：手动创建

1. 拷贝 `knowledge/_template/` 目录，重命名
2. 将资料放入 `data/` 目录
3. 编辑 `domain.yaml` 填写配置
4. 自动热加载生效

支持 Confluence 导出包（配置 `confluence_zip` 字段）和数据库连接（配置 `databases` 字段）。

## 日志分析模式

将 `mode` 改为 `log-analyzer`，注册微服务信息：

```yaml
# services.yaml
services:
  market_gateway:
    name: "行情网关"
    repo: "/data/repos/market_gateway"
    language: "C++"
    depends_on: [data_server]
    description: "接收交易所行情数据并分发"
```

也可以通过对话让 AI 自动注册：`"帮我添加行情网关服务，代码在 /data/repos/market_gateway"`

日志分析模式下的对话框支持拖拽上传日志文件、Ctrl+V 粘贴截图、附件按钮。AI 会自动分析错误、定位代码、追踪依赖链。不同用户的会话通过 git worktree 隔离代码版本。

## 项目结构

```
knowledge-chat/
├── app.py                    # Flask 主应用
├── agent_engine.py           # Agent 引擎（工具 + API 调用 + 知识域加载）
├── log_analyzer.py           # 日志分析模块（Session + worktree + 日志预处理）
├── confluence_converter.py   # Confluence HTML → Markdown 转换
├── config.yaml               # 全局配置
├── services.yaml             # 服务注册表（日志分析模式用）
├── AI_GUIDE.md               # AI 生成知识域的工作指南
├── AI_GUIDE_ANALYZER.md      # AI 生成服务注册的工作指南
├── knowledge/                # 知识域目录
│   ├── _template/            # 模板
│   ├── _memory/              # AI 全局学习记忆
│   └── <domain>/             # 各知识域（domain.yaml + data/）
└── templates/
    ├── chat.html             # 聊天页面（支持文件上传）
    └── share.html            # 分享只读页面
```

## 工具集

### 通用工具（两种模式都可用）

| 工具 | 功能 |
|------|------|
| search | 搜索关键词，返回匹配行及上下文 |
| read_file | 读取文件内容，支持行范围 |
| write_file | 写入/创建文件 |
| list_files | 列出目录文件 |
| glob | 按模式匹配文件路径 |
| bash | 执行 shell 命令 |
| web_fetch | 抓取网页内容 |
| run_python | 执行 Python 代码（数据库查询、数据分析） |

### 日志分析专用工具

| 工具 | 功能 |
|------|------|
| read_log | 过滤日志：按级别、关键词、时间范围筛选 |
| trace_dependency | 查询服务依赖链 |
| switch_service | 加载服务代码（git worktree） |
| list_services | 列出已注册服务 |

### 扩展工具

工具定义在 `agent_engine.py` 的 `TOOLS` 列表中，执行逻辑在 `exec_tool()` 函数中。添加新工具只需：

1. 在 `TOOLS` 列表中添加工具定义（name、description、input_schema）
2. 在 `exec_tool()` 中添加对应的 `elif` 分支
