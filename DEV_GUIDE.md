# 二次开发指南

## 架构概览

```
用户浏览器 → Flask (app.py) → Agent 引擎 (agent_engine.py) → Claude API
                                    ↓
                              知识域目录 (knowledge/*/domain.yaml)
                                    ↓
                              合并 system prompt + 工具集
```

启动时，`agent_engine.py` 扫描 `knowledge/` 下每个子目录中的 `domain.yaml`（跳过 `_template` 和以 `.` 开头的目录），合并生成总 system prompt。AI 根据 prompt 中的知识域描述和搜索路径，自主决定用什么工具、搜哪里。

## 知识域目录结构

每个知识域是一个自包含的目录，所有资料（源码、文档、配置等）统一放在 `data/` 下。整个知识域目录可以直接拷贝到部署服务器使用，不依赖外部路径。

```
knowledge/
├── AI_GUIDE.md              # 给 AI 看的知识域生成指南
├── _template/               # 模板（拷贝此目录创建新知识域）
│   ├── domain.yaml
│   └── data/
│       └── README.md
├── mds_interface/           # 行情接口知识域（自包含）
│   ├── domain.yaml          # 知识域配置
│   └── data/                # 该域的所有资料
│       ├── README.md
│       ├── jce/             # 接口定义
│       ├── src/             # 源码
│       └── doc/             # 文档
└── mds_ops/                 # 行情运维知识域（自包含）
    ├── domain.yaml
    └── data/
        ├── README.md
        ├── conf/            # 配置文件
        ├── script/          # 部署脚本
        └── yaml/            # K8s 配置
```

## domain.yaml 字段说明

```yaml
# knowledge/<domain_name>/domain.yaml

# 必填：知识域名称，显示在欢迎页分组标题
name: "示例知识域"

# 必填：知识域描述，帮助 AI 理解该领域范围
description: "这个知识域包含什么内容"

# 数据文件目录（所有资料都放在这里）
# 引擎自动解析为绝对路径，纳入搜索范围
data_path: "data"

# 必填：prompt 片段，合并到总 system prompt
# 告诉 AI data/ 下的文件组织、常见查询类型等
prompt: |
  ## 知识域标题
  - data/src/ 下是什么文件
  - data/doc/ 下是什么文件
  - 常见查询类型

# 可选：示例问题，显示在欢迎页
examples:
  - "示例问题 1"
  - "示例问题 2"
```

## 新增知识域步骤

### 手动创建

1. 拷贝 `knowledge/_template/` 目录，重命名为知识域英文名（如 `trading_system`）
2. 将所有相关资料（源码、文档、配置等）拷贝到 `data/` 下，按类型建子目录
3. 编辑 `domain.yaml`，填写各字段，prompt 中描述 `data/` 下的文件组织
4. 重启服务（`bash start.sh` 或 `docker-compose restart`）
5. 访问页面验证示例问题出现

### 让 AI 自动生成

参考 `knowledge/AI_GUIDE.md`，提供文件/目录路径，AI 会自动：
- 扫描分析文件内容
- 拷贝所有资料到 `data/` 下并分类整理
- 生成 `domain.yaml` 配置
- 创建完整的知识域目录

## 扩展工具

工具定义在 `agent_engine.py` 的 `TOOLS` 列表中，每个工具包含：

- `name`: 工具名称
- `description`: 工具描述（AI 据此决定是否使用）
- `input_schema`: JSON Schema 格式的参数定义

工具执行逻辑在 `exec_tool()` 函数中，添加新工具需要：

1. 在 `TOOLS` 列表中添加工具定义
2. 在 `exec_tool()` 中添加对应的 `elif` 分支

## 关键配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `api.max_tokens` | 单次回复最大 token | 4096 |
| `api.max_iterations` | Agent 最大工具调用轮数 | 20 |
| `tools.max_output_length` | 工具结果最大字符数（传给 AI） | 15000 |
| `tools.max_display_length` | 工具结果最大字符数（前端展示） | 2000 |

## Docker 部署注意

- `knowledge/` 目录通过 volume 挂载，修改后 `docker-compose restart` 即可生效
- 每个知识域自包含，新增知识域只需将目录拷贝到 `knowledge/` 下并重启
- 环境变量通过 `.env` 文件或 `docker-compose.yml` 的 `environment` 设置
