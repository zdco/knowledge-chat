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

1. 在 `knowledge/` 下新建 `xxx.yaml`
2. 填写字段（参考 `knowledge/mds_interface.yaml`）
3. 重启服务
4. 完成 — AI 自动具备该领域的查询能力

## 项目结构

```
mdschat/
├── app.py                  # Flask 主应用
├── agent_engine.py         # Agent 引擎（知识域加载 + 工具 + API 调用）
├── config.yaml             # 全局配置
├── start.sh                # 启动脚本
├── requirements.txt        # Python 依赖
├── Dockerfile
├── docker-compose.yml
├── knowledge/              # 知识域配置目录
│   ├── mds_interface.yaml  # 行情接口查询
│   └── mds_ops.yaml        # 行情运维知识
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
