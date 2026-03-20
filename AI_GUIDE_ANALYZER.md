# 服务注册指南（AI 专用）

本文档是 AI 的工作指令。当用户要求添加/注册服务时，按照以下流程自动完成。

## 触发条件

- 用户要求添加/注册服务
- 用户要求配置日志分析系统
- 用户描述了业务架构或服务依赖关系

## 引导策略

根据用户提供的信息量，选择不同的引导方式：

### 场景一：用户要批量注册多个服务

先引导用户描述整体业务架构，再一次性生成所有配置。示例引导：

```
为了帮你一次性配置好所有服务和依赖关系，你可以先描述一下整体业务架构，比如：

1. 你们有哪些业务线？（如行情、复盘、指标、盯盘等）
2. 每个业务线包含哪些服务？
3. 服务之间的调用关系是怎样的？（谁调用谁）
4. 有没有跨业务线的共享服务？

不需要很精确，大致的调用方向说清楚就行，比如：
"行情网关 → 行情分发 → 行情缓存，复盘引擎调用数据查询服务获取历史数据"

然后每个服务给我代码地址（GitLab 链接即可），我来生成完整配置。
```

用户描述完架构后，一次性生成所有服务的 `services.yaml` 配置，包括 `depends_on`。

### 场景二：用户只注册单个服务

直接收集该服务的信息，按下方流程操作。依赖关系如果用户不清楚，先留空，后续可以补充。

### 场景三：用户已有服务，要补充依赖关系

用 `switch_service` 加载服务代码，搜索 RPC 调用、配置文件中的服务地址、import 的 client 包等线索，推断依赖关系，更新 `depends_on`。

## 单个服务注册流程

### 第一步：收集信息

向用户确认以下信息（已知的跳过）：

- **服务 ID**：英文标识符，如 `market_gateway`
- **服务名称**：中文显示名，如 "行情网关"
- **代码地址**：GitLab/GitHub 页面链接、git 仓库地址、或本地路径
- **编程语言**：如果用户没说，注册后通过 `switch_service` 加载代码再识别
- **依赖服务**：上下游服务列表
- **服务描述**：一句话说明服务职责
- **客户仓库**（可选）：如果不同客户的代码在不同仓库，询问客户名和对应地址

不需要单独问子路径和分支 — 如果用户提供的是 GitLab 页面链接（如 `http://gitlab.xxx/group/project/tree/dev/some/path`），系统会自动解析出仓库地址、分支和子路径。

### 第二步：写入 services.yaml

用 `read_file` 读取当前 `services.yaml`，在 `services:` 下追加新服务配置：

```yaml
services:
  <service_id>:
    name: "<中文名称>"
    repo: "<代码地址>"              # 直接粘贴用户提供的地址即可
    language: "<语言>"
    depends_on: [<依赖服务ID列表>]
    description: "<服务描述>"
```

如果不同客户的代码在不同仓库，加上 `client_repos`：

```yaml
    client_repos:
      客户A: "<客户A的代码地址>"
      客户B: "<客户B的代码地址>"
```

### 第三步：验证

1. 用 `read_file` 读取写入后的文件，确认 YAML 格式正确
2. 如果有 `depends_on`，确认依赖的服务已注册（未注册的提醒用户后续添加）
3. 如果用户提供了本地路径，用 `list_files` 确认路径存在

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
- `depends_on` 中的 ID 必须与其他服务的 ID 一致
- description 要简洁明了，说明服务的核心职责
- 远程 git URL 需要服务器有访问权限（SSH key 或 HTTPS token）
