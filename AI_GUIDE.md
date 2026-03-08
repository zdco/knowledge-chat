# 知识域生成指南（AI 专用）

本文档是 AI 的工作指令。当用户要求创建知识域时，按照以下流程自动完成。

## 核心原则：自包含

每个知识域目录必须是自包含的。所有源码、文档、配置等资料统一拷贝到 `data/` 目录下，不依赖外部路径。这样整个知识域目录可以直接拷贝到部署服务器使用。

## 触发条件

用户提供了一组文件或目录，要求创建/生成知识域。

## 自动化工作流程

### 第一步：扫描分析

对用户提供的每个文件/目录：

1. 列出所有文件，统计文件类型分布（`.jce`, `.cpp`, `.h`, `.conf`, `.md`, `.xml` 等）
2. 抽样读取关键文件（接口定义、头文件、README、配置文件），理解该领域的内容
3. 识别出：
   - 领域主题（接口定义？运维配置？数据处理？）
   - 关键概念和术语
   - 文件组织方式
   - 用户可能会问的典型问题

### 第二步：拷贝所有资料到 data/

将用户提供的所有文件和目录统一拷贝到 `data/` 下，按来源建子目录保持结构清晰：

```
data/
├── README.md          # 说明各子目录来源
├── src/               # 源码（从源码目录拷贝）
├── jce/               # 接口定义（从 JCE 目录拷贝）
├── doc/               # 文档（从文档目录拷贝）
├── conf/              # 配置文件（从配置目录拷贝）
└── ...                # 其他资料
```

整理原则：
- 所有文件都拷贝到 `data/` 下，不依赖任何外部路径
- 按来源或类型建子目录，保持结构清晰
- 子目录命名简洁直观（`src`, `jce`, `doc`, `conf` 等）
- 如果用户只提供了一个目录，可以直接拷贝其内容到 `data/` 下，保留原有子目录结构

### 第三步：生成 domain.yaml

基于扫描结果，自动生成完整配置：

```yaml
# knowledge/<domain_name>/domain.yaml
# <domain_name> 用英文小写+下划线命名，如 trading_system

# 从文件内容中提炼的中文名称
name: "知识域中文名"

# 从文件内容中总结的一句话描述
description: "该领域包含的内容概述"

# 指向本域数据文件目录（所有资料都在这里）
data_path: "data"

# 基于文件分析自动生成的 prompt 片段
# 要求：
#   - 用 ## 标题开头
#   - 列出 data/ 下的子目录结构和文件类型
#   - 列出常见查询类型
#   - 如果有特殊的命名规则或约定，也要写出来
prompt: |
  ## 知识域标题
  - data/src/ 下是源码实现（*.cpp, *.h）
  - data/jce/ 下是接口定义（*.jce）
  - data/doc/ 下是文档（*.md）
  - 常见查询类型有哪些
  - 特殊约定或注意事项

# 基于文件内容生成 3-5 个典型问题
# 要求：问题要具体，包含该领域的真实术语和概念
examples:
  - "具体问题 1？"
  - "具体问题 2？"
```

注意：不需要 `search_paths` 字段。`data_path: "data"` 会让引擎自动将 `data/` 目录纳入搜索范围。

### 第四步：创建目录结构

执行以下操作：

1. 创建 `knowledge/<domain_name>/` 目录
2. 创建 `data/` 及其子目录
3. 创建 `memory/` 目录（用于 AI 学习笔记，无需放任何文件）
4. 拷贝所有文件到 `data/` 对应子目录下
5. 写入 `data/README.md`，说明各子目录的来源和内容
6. 写入 `domain.yaml`

### 第五步：输出总结

向用户报告：
- 创建了哪些文件和目录
- `data/` 下整理了哪些文件（列出子目录和文件数量）
- 生成的示例问题列表
- 提示：整个 `knowledge/<domain_name>/` 目录可直接拷贝到部署服务器
- 提示：重启服务生效

## 目录结构规范

```
knowledge/
├── _template/               # 模板目录（不会被引擎加载）
│   ├── domain.yaml
│   └── data/
│       └── README.md
├── <domain_name>/           # 知识域目录（自包含，可整体拷贝部署）
│   ├── domain.yaml          # 知识域配置（必须叫这个名字）
│   ├── data/                # 该域的所有资料（源码、文档、配置等）
│   │   ├── README.md
│   │   ├── src/
│   │   ├── jce/
│   │   └── ...
│   └── memory/              # AI 学习笔记（自动创建，通过 search 检索）
```

引擎扫描规则：`knowledge/*/domain.yaml`，跳过 `_` 和 `.` 开头的目录。

## domain.yaml 字段参考

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 中文名称，显示在欢迎页 |
| `description` | 是 | 一句话描述，帮助 AI 理解领域范围 |
| `data_path` | 否 | 数据文件目录，相对 domain.yaml 所在目录，默认 `"data"` |
| `search_paths` | 否 | 额外搜索路径（一般不需要，data_path 已覆盖） |
| `prompt` | 是 | prompt 片段，合并到总 system prompt |
| `examples` | 否 | 示例问题列表，显示在欢迎页 |
| `databases` | 否 | 数据库连接配置列表，AI 可通过 run_python 工具查询 |

## 数据库知识域

如果知识域涉及数据库查询和分析，可以在 domain.yaml 中配置 `databases` 字段，AI 会自动使用 `run_python` 工具生成 Python 代码连接数据库。

### 支持的数据库类型

| 类型 | 驱动 | 必填参数 |
|------|------|----------|
| mysql | pymysql | host, port, database, user, password |
| oracle | oracledb | host, port, service_name, user, password |

### 配置示例

```yaml
name: "业务数据分析"
description: "业务数据库查询与数据分析"
data_path: "data"

databases:
  - name: 生产库
    type: oracle
    host: 10.0.0.1
    port: 1521
    service_name: orcl
    user: readonly
    password: xxx
  - name: 业务库
    type: mysql
    host: 10.0.0.2
    port: 3306
    database: biz_db
    user: readonly
    password: xxx

prompt: |
  ## 业务数据分析
  - 可查询生产库（Oracle）和业务库（MySQL）中的数据
  - 常见查询：业务指标统计、数据质量检查、趋势分析

examples:
  - "查一下业务库 orders 表今天有多少条数据？"
  - "统计生产库中各部门的用户数量分布"
```

### AI 生成知识域时的注意事项

当用户提到知识域涉及数据库时，应主动询问：
1. 数据库类型（MySQL / Oracle）
2. 连接信息（host、port、库名/service_name）
3. 账号密码（建议使用只读账号）

将收集到的信息写入 domain.yaml 的 `databases` 字段。

## 完整示例

用户说："帮我用 /home/dev/hqjce 和 /home/dev/MarketDataServer 还有 /home/dev/doc 创建一个行情接口的知识域"

AI 应该：

1. 扫描三个目录，分析文件内容和结构
2. 创建如下目录结构：

```
knowledge/mds_interface/
├── domain.yaml
└── data/
    ├── README.md
    ├── jce/          # 从 /home/dev/hqjce 拷贝
    │   ├── StockHq.jce
    │   ├── MarketData.jce
    │   └── ...
    ├── src/          # 从 /home/dev/MarketDataServer 拷贝
    │   ├── BasicHqImp.cpp
    │   ├── BasicHqImp.h
    │   └── ...
    └── doc/          # 从 /home/dev/doc 拷贝
        ├── interface.md
        └── ...
```

3. 生成配置：

```yaml
# knowledge/mds_interface/domain.yaml
name: "行情主站接口"
description: "JCE 接口定义、请求参数、数据结构、源码实现"

data_path: "data"

prompt: |
  ## 行情主站接口
  - data/jce/ 下是 JCE 接口定义文件（*.jce），定义了所有请求和响应结构
  - data/src/ 下是服务端 C++ 实现（*.cpp, *.h）
  - data/doc/ 下是接口文档（*.md）
  - 常见查询：接口参数、枚举值、数据结构、调用示例

examples:
  - "stockHq 接口怎么调用？请求参数是什么？"
  - "E_MARKET_CODE 里深圳是多少？"
  - "哪些接口用到了 HeaderInfo？"
```

4. 告知用户：整个 `knowledge/mds_interface/` 目录可直接拷贝到服务器，重启服务生效
