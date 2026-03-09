# 知识域生成指南（AI 专用）

本文档是 AI 的工作指令。当用户要求创建知识域时，按照以下流程自动完成。

## 核心原则：自包含

每个知识域目录必须是自包含的。所有源码、文档、配置等资料统一拷贝到 `data/` 目录下，不依赖外部路径。这样整个知识域目录可以直接拷贝到部署服务器使用。

## 触发条件

用户提供了一组文件或目录，要求创建/生成知识域。

## 自动化工作流程

### 第一步：扫描分析

对用户提供的每个文件/目录：

1. 列出所有文件，统计文件类型分布（`.java`, `.cpp`, `.h`, `.jce`, `.conf`, `.md`, `.xml` 等）
2. 判断知识域类型（可能是混合型），按对应策略深度分析
3. 抽样读取关键文件，提取写 prompt 所需的具体信息

#### 按场景分析策略

**代码工程**（含 `.java`, `.py`, `.go`, `.cpp`, `.ts` 等源码文件）

必须读取的文件（按优先级）：
1. 构建文件 — `pom.xml` / `build.gradle` / `package.json` / `CMakeLists.txt` / `go.mod` / `Cargo.toml`，确定技术栈、模块划分、依赖关系
2. 入口文件 — main 函数、Application 启动类、路由注册文件，理解启动流程和整体架构
3. 目录结构 — 通过顶层目录命名推断分层模式（如 `controller/service/dao`、`cmd/internal/pkg`、`src/main/java/...`）
4. 核心抽象 — 关键接口/基类/trait/protocol 定义，理解领域模型
5. 配置文件 — `application.yml` / `.env` / `config.*`，了解可配置项

需要提取的信息：
- 技术栈和框架版本（如 Spring Boot 2.7、React 18）
- 模块/包的划分和职责（不是简单罗列目录名，而是说清每个模块做什么）
- 核心类/函数及其关系（如"OrderService 调用 PaymentGateway 完成支付"）
- 关键枚举、常量、错误码（用户高频查询）
- 特殊约定（命名规则、分包策略、设计模式）

**接口定义**（含 `.jce`, `.proto`, `.thrift`, `.idl`, `.graphql`, OpenAPI `.yaml` 等）

必须读取的文件：
1. 所有接口定义文件（通常不多），完整理解服务和方法列表
2. 公共类型定义（枚举、结构体、公共头）

需要提取的信息：
- 服务列表及每个服务的职责
- 核心数据结构和字段含义
- 枚举值及其业务含义
- 接口间的依赖关系（如"A 接口的返回值是 B 接口的入参"）

**文档/知识库**（以 `.md`, `.rst`, `.txt`, `.pdf`, `.docx` 为主）

必须读取的文件：
1. 目录索引文件（README、SUMMARY、index、目录页）
2. 抽样读取各子目录的代表性文档

需要提取的信息：
- 文档的组织层级和分类体系
- 覆盖的主题范围
- 核心术语和概念（建立术语表）
- 文档间的引用关系

**Confluence 导出包**（zip 文件，含 HTML + 图片）

处理方式：
1. 将 zip 文件放到知识域根目录下（与 domain.yaml 同级）
2. domain.yaml 中添加 `confluence_zip: "文件名.zip"`
3. 服务启动时自动解压转换为 Markdown，输出到 data/wiki/ 下，按 Confluence 页面层级组织目录
4. 图片保留在 data/wiki/_attachments/ 下，可通过 web 路由访问

prompt 编写要点：
- 说明 data/wiki/ 下是 Confluence 导出的文档，按页面层级组织
- 提示 AI 用 list_files 浏览 data/wiki/ 目录结构，用 search 搜索关键词
- 如果要在回复中展示图片，使用 `/mds/wiki/<域名>/_attachments/...` 路径

**配置/运维**（以 `.yaml`, `.conf`, `.ini`, `.toml`, `.xml`, `.sh`, `Dockerfile` 等为主）

必须读取的文件：
1. 主配置文件和环境差异配置（dev/staging/prod）
2. 部署脚本、Dockerfile、CI/CD 配置

需要提取的信息：
- 关键配置项及其作用
- 环境间的差异点
- 部署架构和依赖关系
- 常见运维操作流程

**数据库**（配合 `databases` 字段使用）

需要了解的信息（通过用户提供的文档或询问获取）：
- 核心表及其业务含义
- 表间关系（外键、业务关联）
- 关键字段的业务含义（特别是命名不直观的字段）
- 常用查询场景

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

# 基于文件分析自动生成的 prompt 片段（见下方 prompt 编写指南）
prompt: |
  ...

# 基于文件内容生成 3-5 个典型问题
# 要求：问题要具体，包含该领域的真实术语和概念
examples:
  - "具体问题 1？"
  - "具体问题 2？"
```

注意：不需要 `search_paths` 字段。`data_path: "data"` 会让引擎自动将 `data/` 目录纳入搜索范围。

#### prompt 编写指南

prompt 是知识域效果的关键。好的 prompt 让 AI 知道"去哪找"和"怎么理解"，差的 prompt 只是重复目录名。

**通用结构**：

```
## 知识域标题

### 文件结构
（列出 data/ 下的子目录，说明每个目录的内容和用途）

### 核心概念
（列出该领域的关键术语、核心抽象、重要约定）

### 查询指引
（告诉 AI 遇到不同类型问题时应该搜索哪里、怎么搜）
```

**反面示例**（不要这样写）：

```
## 交易系统
- data/src/ 下是源码（*.java）
- data/doc/ 下是文档（*.md）
- 常见查询：代码查找、文档查询
```

问题：只罗列了目录和文件类型，AI 不知道模块职责、核心概念、查询策略。

**各场景 prompt 示例**：

代码工程：

```
## 交易系统

### 文件结构
- data/src/ 下是 Spring Boot 工程（Java 17 + Spring Boot 3.1）
  - com.xxx.trade.order/ — 订单模块：OrderController 接收请求，OrderService 处理业务逻辑，OrderMapper 操作数据库
  - com.xxx.trade.payment/ — 支付模块：对接支付宝和微信支付，PaymentGateway 是统一入口
  - com.xxx.trade.risk/ — 风控模块：RiskEngine 在下单前做规则校验
  - com.xxx.trade.common/ — 公共模块：ErrorCode 错误码枚举、BizException 业务异常
- data/doc/ 下是设计文档和接口文档

### 核心概念
- 订单状态机：CREATED → PAYING → PAID → SHIPPING → COMPLETED / CANCELLED
- 幂等机制：所有写接口通过 requestId 做幂等，见 IdempotentAspect
- 金额统一用 BigDecimal，单位为分
- 错误码格式：模块前缀(2位) + 错误编号(4位)，如 OR0001 = 订单不存在

### 查询指引
- 查接口参数 → 搜索对应 Controller 类
- 查业务逻辑 → 搜索对应 Service 类
- 查错误码含义 → 搜索 ErrorCode 枚举
- 查配置项 → 搜索 application.yml 或 @Value 注解
```

接口定义：

```
## 行情主站接口

### 文件结构
- data/jce/ 下是 JCE 接口定义文件（*.jce），定义了所有请求和响应结构
  - StockHq.jce — 股票行情接口，包含 getStockHq / getStockList 等方法
  - MarketData.jce — 市场数据接口，包含 getMarketOverview / getIndexData 等方法
  - CommonTypes.jce — 公共类型定义，E_MARKET_CODE（市场编码枚举）、HeaderInfo（请求头）
- data/src/ 下是服务端 C++ 实现（*.cpp, *.h）
- data/doc/ 下是接口文档

### 核心概念
- E_MARKET_CODE 枚举：0=深圳 1=上海 2=北京
- HeaderInfo 是所有请求的公共头，包含 userId / version / timestamp
- 行情数据精度：价格字段统一放大 10000 倍存储为整数

### 查询指引
- 查接口参数和返回值 → 搜索 data/jce/ 下的 .jce 文件
- 查枚举值含义 → 搜索 CommonTypes.jce
- 查具体实现逻辑 → 搜索 data/src/ 下对应的 Imp.cpp 文件
```

文档/知识库：

```
## 产品运营手册

### 文件结构
- data/product/ — 产品说明文档，按功能模块组织（用户管理、订单管理、报表）
- data/ops/ — 运营操作手册，包含日常操作流程和应急预案
- data/faq/ — 常见问题汇总，按客户反馈分类

### 核心概念
- 用户等级体系：普通用户 / VIP / SVIP，影响费率和权限
- "T+1 结算"：交易日次日完成资金清算
- 文档中"灰度"指按用户 ID 尾号分批放量

### 查询指引
- 查功能说明 → 搜索 data/product/
- 查操作步骤 → 搜索 data/ops/
- 查历史问题 → 搜索 data/faq/
```

配置/运维：

```
## 部署与运维

### 文件结构
- data/conf/ — 各环境配置文件
  - dev/ prod/ staging/ — 按环境区分，主要差异在数据库连接和日志级别
  - nginx/ — Nginx 配置，包含反向代理和限流规则
- data/scripts/ — 运维脚本（部署、回滚、健康检查）
- data/docker/ — Dockerfile 和 docker-compose 配置

### 核心概念
- 部署架构：Nginx → 2 台应用服务器（蓝绿部署）→ MySQL 主从
- 配置优先级：环境变量 > 环境配置文件 > 默认配置
- 日志路径统一在 /data/logs/<服务名>/，按天轮转

### 查询指引
- 查某个配置项 → 搜索 data/conf/ 下的配置文件
- 查部署流程 → 搜索 data/scripts/deploy
- 查环境差异 → 对比 dev/ 和 prod/ 下的同名配置文件
```

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

### prompt 中数据库相关规则

在 prompt 中编写数据库查询指引时，必须遵循以下规则：

1. **连接代码不要写 `init_oracle_client`**，系统会自动注入 thick 模式初始化，prompt 中只需写：
   ```python
   import oracledb
   conn = oracledb.connect(user="xxx", password="xxx", dsn="host:port/service")
   ```

2. **必须强调"禁止猜测表名和字段名"**，要求 AI 先通过以下方式确认：
   - 搜索 data/ 下的文档（如果有导出的元数据文件）
   - 查询数据库的元数据表（如 Oracle 的 `ALL_TABLES`、`ALL_TAB_COLUMNS`，MySQL 的 `information_schema`）
   - 确认表名和字段名后再写业务查询

3. **提供元数据查询模板**，在 prompt 的"查询指引"中给出具体的元数据查询 SQL，降低 AI 猜测的概率

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

  ### 文件结构
  - data/jce/ 下是 JCE 接口定义文件（*.jce）
    - StockHq.jce — 股票行情接口，包含 getStockHq / getStockList 等方法
    - MarketData.jce — 市场数据接口，包含 getMarketOverview / getIndexData 等方法
    - CommonTypes.jce — 公共类型定义，E_MARKET_CODE（市场编码枚举）、HeaderInfo（请求头）
  - data/src/ 下是服务端 C++ 实现（*.cpp, *.h）
    - BasicHqImp.cpp/h — 基础行情接口实现
  - data/doc/ 下是接口文档（*.md）

  ### 核心概念
  - E_MARKET_CODE 枚举：0=深圳 1=上海 2=北京
  - HeaderInfo 是所有请求的公共头，包含 userId / version / timestamp
  - 行情数据精度：价格字段统一放大 10000 倍存储为整数

  ### 查询指引
  - 查接口参数和返回值 → 搜索 data/jce/ 下的 .jce 文件
  - 查枚举值含义 → 搜索 CommonTypes.jce
  - 查具体实现逻辑 → 搜索 data/src/ 下对应的 Imp.cpp 文件

examples:
  - "stockHq 接口怎么调用？请求参数是什么？"
  - "E_MARKET_CODE 里深圳是多少？"
  - "哪些接口用到了 HeaderInfo？"
```

4. 告知用户：整个 `knowledge/mds_interface/` 目录可直接拷贝到服务器，重启服务生效
