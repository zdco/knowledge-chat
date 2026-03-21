# 服务注册指南（AI 专用）

本文档是 AI 的工作指令。当用户要求添加/注册服务时，按照以下流程自动完成。

## 触发条件

- 用户要求添加/注册服务
- 用户要求配置日志分析系统
- 用户提供了一批仓库地址要求批量注册

## 引导策略

根据用户提供的信息量，选择不同的引导方式：

### 场景一：用户要批量注册多个服务

先引导用户提供仓库地址列表和业务线归属，AI 自动识别语言、生成描述。示例引导：

```
为了帮你一次性配置好所有服务，你可以提供以下信息：

1. 每个服务的代码地址（GitLab 链接即可）
2. 这些服务属于哪个业务线？（如行情、复盘、指标等）

不需要梳理依赖关系，AI 在排查问题时会从代码中自动发现。

示例：
行情业务：
- 行情网关：http://gitlab.xxx/group/market_gateway/tree/dev
- 数据服务：http://gitlab.xxx/group/data_server/tree/dev
复盘业务：
- 复盘引擎：http://gitlab.xxx/group/replay_engine/tree/dev
```

用户提供信息后，一次性生成所有服务的 `services.yaml` 配置，包括 `businesses` 分组。

### 场景二：用户只注册单个服务

直接收集该服务的信息，按下方流程操作。

## 单个服务注册流程

### 第一步：收集信息

向用户确认以下信息（已知的跳过）：

- **服务 ID**：英文标识符，如 `market_gateway`
- **服务名称**：中文显示名，如 "行情网关"
- **代码地址**：GitLab/GitHub 页面链接、git 仓库地址、或本地路径
- **业务线**：该服务属于哪个业务线（可选，用于 businesses 分组）
- **编程语言**：如果用户没说，注册后通过 `switch_service` 加载代码再识别
- **服务描述**：一句话说明服务职责
- **别名**（可选）：服务的其他名称，用于模糊匹配
- **客户仓库**（可选）：如果不同客户的代码在不同仓库，询问客户名和对应地址

不需要单独问子路径和分支 — 如果用户提供的是 GitLab 页面链接（如 `http://gitlab.xxx/group/project/tree/dev/some/path`），系统会自动解析出仓库地址、分支和子路径。

### 第二步：写入 services.yaml

用 `read_file` 读取当前 `services.yaml`，追加配置：

```yaml
businesses:
  行情业务:
    - market_gateway
    - data_server

services:
  market_gateway:
    name: "行情网关"
    repo: "<代码地址>"
    language: "C++"
    description: "接收交易所行情数据并分发"
    aliases: ["MarketGateway"]
```

如果不同客户的代码在不同仓库，加上 `client_repos`：

```yaml
    client_repos:
      客户A: "<客户A的代码地址>"
      客户B: "<客户B的代码地址>"
```

### 第三步：验证

1. 用 `read_file` 读取写入后的文件，确认 YAML 格式正确
2. 如果用户提供了本地路径，用 `list_files` 确认路径存在

### 第四步：扫描代码（可选）

如果需要识别语言或补充描述：

1. 用 `switch_service` 加载代码
2. 用 `list_files` 查看目录结构
3. 根据构建文件识别语言和框架（`pom.xml` → Java、`CMakeLists.txt` → C++、`package.json` → Node.js 等）
4. 更新 `services.yaml` 中的 `language` 和 `description`

## repo 地址格式

`repo` 和 `client_repos` 中的地址都支持以下格式，系统自动识别处理：

| 格式 | 示例 | 说明 |
|------|------|------|
| GitLab/GitHub 页面链接 | `http://gitlab.whup.com/group/project/tree/dev/DbQueryServer` | 自动解析出仓库、分支 `dev`、子路径 `DbQueryServer` |
| git 仓库地址 | `https://gitlab.example.com/group/project.git` | 首次使用自动 clone，submodule 自动拉取 |
| SSH 地址 | `git@gitlab.example.com:group/project.git` | 需要服务器有 SSH key 访问权限 |
| 本地 git 仓库 | `/data/repos/market_gateway` | 通过 git worktree 切版本，不影响原仓库 |
| 本地普通目录 | `/data/customer/legacy_code` | 非 git 项目，复制到隔离目录 |

**用户提供什么地址就写什么地址，不需要手动转换。**

## 客户仓库映射（client_repos）

同一个服务，不同客户的代码可能在不同仓库（常见于 git 仓库迁移过的场景）：

```yaml
trade_engine:
  name: "交易引擎"
  repo: "https://new-gitlab.example.com/trading/engine.git"
  language: "C++"
  description: "核心交易撮合引擎"
  client_repos:
    # 直接写地址（支持 GitLab 页面链接）
    客户A: "http://old-gitlab.example.com/legacy/trade-engine/tree/master"
    客户B: "git@internal-git:trading/engine-v2.git"

    # 如果该客户的目录结构不同，用完整格式
    客户C:
      repo: "/data/customer_code/clientC/trade_engine"
      sub_path: "src"
```

用户在对话中说"客户A的交易引擎 v2.3.1 有问题"，AI 调用：
```
switch_service(service="trade_engine", version="v2.3.1", client="客户A")
```

版本号不需要在配置中写死，用户对话时提供即可。没指定版本时加载默认分支的最新代码。

## 用户上传代码压缩包

如果用户在对话中上传了代码压缩包（zip/tar.gz），不需要在 services.yaml 中注册。代码会自动解压到隔离目录，直接用 search/read_file 分析即可。

## 注意事项

- 服务 ID 使用小写字母和下划线，如 `market_gateway`
- description 要简洁明了，说明服务的核心职责
- 远程 git URL 需要服务器有访问权限（SSH key 或 HTTPS token）
- 不需要手动维护依赖关系，AI 在排查问题时用 `scan_service` 从代码中实时发现
