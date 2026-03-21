# 服务注册指南（AI 专用）

本文档是 AI 的工作指令。当用户要求添加/注册服务时，按照以下流程自动完成。

## 触发条件

- 用户要求添加/注册服务
- 用户要求配置日志分析系统
- 用户提供了一批仓库地址要求批量注册
- 用户要求刷新/重新扫描已注册服务的描述

## 刷新服务描述

当用户说"刷新描述"、"重新扫描"等，对已注册服务重新生成描述：

1. 读取 `services.yaml`，获取需要刷新的服务列表（用户可指定某个服务或全部）
2. 对每个服务，用其 `repo` 地址重新执行「单个仓库扫描识别规则」的第二步（Clone）和第五步（生成描述）
3. 用新描述覆盖 `services.yaml` 中的 `description` 字段，其他字段不动
4. 展示变更对比（旧描述 → 新描述），让用户确认后写入

## 引导策略

根据用户提供的信息量，选择不同的引导方式：

### 场景一：批量注册多个服务

用户可能以如下格式提供信息：

```
帮我注册以下服务：

行情业务：
- http://gitlab.whup.com/HQSystem/market_gateway/tree/dev
  别名：MarketGateway, HQGateway
  客户A: http://old-gitlab.whup.com/legacy/market_gateway/tree/master
- http://gitlab.whup.com/HQSystem/data_server/tree/dev

复盘业务：
- http://gitlab.whup.com/Replay/replay_engine/tree/dev
```

如果用户只给了仓库地址列表，没有提供业务线归属，主动询问：

```
这些服务分别属于哪个业务线？（如行情、复盘、指标等）
如果暂时不分组也可以，后续再补。
```

**AI 处理流程：**

1. **解析用户输入**：提取每个仓库的 URL、业务线归属、别名、客户仓库等附加信息
2. **逐个仓库执行扫描**：对每个仓库地址，按下方「单个仓库扫描识别规则」clone 代码并识别语言/名称/描述
3. **合并信息**：将用户提供的信息（别名、客户仓库、业务线）与自动识别的信息合并，用户提供的优先
4. **生成完整 services.yaml**：包含 `businesses` 分组和所有服务配置
5. **展示结果让用户确认**：以 YAML 格式展示生成的配置，等用户确认后再写入文件

### 场景二：注册单个服务

1. 用户提供仓库地址（及可选的别名、客户仓库、业务线）
2. 按下方「单个仓库扫描识别规则」clone 代码并自动识别语言/名称/描述
3. 生成配置，展示给用户确认后写入 `services.yaml`

## 单个仓库扫描识别规则

拿到仓库地址后，执行以下步骤自动识别服务信息：

### 第一步：推断服务 ID 和自动生成别名

**服务 ID**：从 URL 的仓库名或子路径取，转为 `snake_case`

示例：
  - `http://gitlab.xxx/group/MarketGateway/tree/dev` → `market_gateway`
  - `http://gitlab.xxx/group/mono-repo/tree/dev/DbQueryServer` → `db_query_server`
  - `http://gitlab.xxx/group/data_server/tree/dev` → `data_server`（已是 snake_case，保持不变）

**自动生成别名**：从服务 ID 自动派生常见变体，加入 `aliases`，确保用户用任何命名风格都能匹配到服务：

| 服务 ID | 自动生成的别名 |
|---------|---------------|
| `market_data_server` | `MarketDataServer`（PascalCase）、`market-data-server`（kebab-case）、`marketdataserver`（全小写无分隔） |

生成规则：
1. **PascalCase**：`snake_case` 每段首字母大写拼接 → `MarketDataServer`
2. **kebab-case**：下划线替换为连字符 → `market-data-server`
3. **全小写无分隔**：去掉所有分隔符 → `marketdataserver`

用户额外提供的别名（如中文名、缩写）追加到自动生成的别名之后。

### 第二步：Clone 代码

```bash
git clone <仓库地址> /tmp/<服务ID> --depth 1 --branch <分支>
cd /tmp/<服务ID>
git submodule update --init --depth 1
```

- 如果 URL 中包含分支信息（如 `/tree/dev`），用该分支；否则不加 `--branch`，使用默认分支
- `--depth 1` 只拉最新一次提交，节省时间
- 始终 clone 整个仓库，即使 URL 包含子路径（如 `/tree/dev/DbQueryServer`）
- 初始化 submodule，部分项目的依赖库在 submodule 中

**扫描范围**：以子路径为主入口，但同时检查仓库根目录的以下内容（后续各步骤均遵循此范围）：
- 根目录的构建文件（如顶层 `CMakeLists.txt` 可能定义全局编译选项和依赖）
- `lib/`、`third_party/`、`deps/`、`external/` 等公共依赖目录
- `.gitmodules`（了解 submodule 依赖）
- 根目录的 `README.md`（可能包含整体项目说明）

这样即使服务代码在子目录，也不会漏掉上级目录的依赖信息和构建配置。

### 第三步：识别编程语言

按构建文件判断：

| 构建文件 | 语言 | 框架线索 |
|----------|------|----------|
| `CMakeLists.txt` | C++ | `find_package(Qt)` → Qt 项目 |
| `pom.xml` | Java | `spring-boot-starter` → Spring Boot |
| `build.gradle` / `build.gradle.kts` | Java/Kotlin | `org.jetbrains.kotlin` → Kotlin |
| `package.json` | JavaScript | 同时存在 `tsconfig.json` → TypeScript |
| `go.mod` | Go | |
| `Cargo.toml` | Rust | |
| `setup.py` / `pyproject.toml` / `requirements.txt` | Python | |
| `*.sln` / `*.csproj` | C# | |
| `Makefile`（且无上述文件） | C/C++ | 看源文件后缀 `.c` → C，`.cpp` → C++ |

如果存在多个构建文件，取主构建文件对应的语言（如同时有 `pom.xml` 和 `package.json`，主语言是 Java）。

### 第四步：提取服务名称

按优先级尝试：

1. `README.md` / `README` 的第一个 `#` 标题
2. `pom.xml` 的 `<name>` 标签
3. `package.json` 的 `name` 字段
4. `CMakeLists.txt` 的 `project(...)` 名称
5. `build.gradle` 的 `rootProject.name`
6. `Cargo.toml` 的 `[package] name`
7. 以上都找不到 → 留空，让用户补充

注意：如果提取到的名称是英文（如 `Market Gateway`），仅作为参考放入 aliases，`name` 字段留空让用户补充中文显示名。

### 第五步：生成服务描述

描述应能让 AI 在排查问题时快速理解服务的职责和技术特征，不是一句话概括，而是包含以下维度：

1. **核心职责**：这个服务做什么（从 README、入口文件、main 函数推断）
2. **关键技术**：用了什么协议/中间件（如 TCP 长连接、gRPC、Redis、Kafka、Oracle）
3. **对外接口**：提供什么接口或端口（从配置文件、proto 文件、路由定义推断）
4. **数据流向**：数据从哪来、到哪去（从代码中的上下游调用推断）

**信息来源**（按优先级扫描）：

1. `README.md` 的项目介绍段落
2. 构建文件中的描述字段（`pom.xml` `<description>`、`package.json` `description` 等）
3. 入口文件（`main.cpp`、`Application.java`、`main.go`、`app.py` 等）的结构和注释
4. 配置文件（`application.yml`、`config.ini`、`.env.example` 等）中的端口、连接地址、中间件配置
5. 接口定义文件（`*.proto`、`*.thrift`、OpenAPI/Swagger）
6. 目录结构和模块划分

**排除目录**：以下目录中的代码不代表服务本身的行为，扫描时必须跳过：
- `example/`、`examples/`、`sample/`、`samples/`
- `test/`、`tests/`、`unittest/`
- `demo/`、`doc/`、`docs/`
- `benchmark/`、`tools/`（辅助脚本）

**描述示例**：

```
接收交易所 TCP 行情数据，解码后通过共享内存和 UDP 组播分发给下游服务；支持多交易所多协议（上交所 FAST、深交所 Binary），内置行情快照缓存，提供 REST 接口供查询最新行情
```

**注意**：描述中不要包含版本号（如 v1.0.5），版本号会随代码变化，由用户在对话中指定。

而不是：

```
行情网关服务
```

### 第六步：清理临时文件

扫描完成后删除 clone 的临时目录：

```bash
rm -rf /tmp/<服务ID>
```

## 写入 services.yaml

用 `read_file` 读取当前 `services.yaml`，追加配置：

```yaml
businesses:
  行情业务:
    - market_gateway
    - data_server

services:
  market_gateway:
    name: "行情网关"
    repo: "http://gitlab.whup.com/HQSystem/market_gateway/tree/dev"
    language: "C++"
    description: "接收交易所 TCP 行情数据，解码后通过共享内存和 UDP 组播分发给下游服务；支持多交易所协议，内置行情快照缓存，提供 REST 接口查询最新行情"
    aliases: ["MarketGateway", "HQGateway"]
    client_repos:
      客户A: "http://old-gitlab.whup.com/legacy/market_gateway/tree/master"
```

写入后用 `read_file` 读取确认 YAML 格式正确。

**用户提供什么地址就写什么地址，不需要手动转换。** 系统会自动识别 GitLab/GitHub 页面链接、git 仓库地址、SSH 地址、本地路径等格式。

## 注意事项

- 服务 ID 使用小写字母和下划线，如 `market_gateway`
- description 要简洁明了，说明服务的核心职责
- 远程 git URL 需要服务器有访问权限（SSH key 或 HTTPS token）
- 不需要手动维护依赖关系，AI 在排查问题时用 `scan_service` 从代码中实时发现
