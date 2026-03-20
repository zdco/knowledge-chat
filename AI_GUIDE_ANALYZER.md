# 服务注册指南（AI 专用）

本文档是 AI 的工作指令。当用户要求添加/注册服务时，按照以下流程自动完成。

## 触发条件

用户提供了服务信息（名称、代码路径、依赖关系等），要求添加到日志分析系统。

## 自动化工作流程

### 第一步：扫描分析

对用户提供的代码仓库路径：

1. 用 `list_files` 列出顶层目录结构
2. 识别项目语言和框架：
   - 查找 `pom.xml` / `build.gradle` → Java
   - 查找 `CMakeLists.txt` / `Makefile` → C/C++
   - 查找 `package.json` → Node.js
   - 查找 `go.mod` → Go
   - 查找 `requirements.txt` / `setup.py` → Python
3. 读取构建文件，提取项目名称和模块信息
4. 扫描源码目录结构，识别核心模块

### 第二步：确认信息

向用户确认以下信息（已知的跳过）：

- **服务 ID**：英文标识符，如 `market_gateway`
- **服务名称**：中文显示名，如 "行情网关"
- **代码来源**：本地路径、远程 git URL、或用户上传的压缩包
- **子路径**（monorepo 场景）：仓库内的子目录
- **编程语言**：自动识别结果
- **依赖服务**：上下游服务列表
- **服务描述**：一句话说明服务职责
- **客户仓库**（可选）：如果不同客户的代码在不同仓库，询问客户名和对应仓库地址

### 第三步：写入 services.yaml

用 `read_file` 读取当前 `services.yaml`，在 `services:` 下追加新服务配置：

```yaml
services:
  <service_id>:
    name: "<中文名称>"
    repo: "<仓库地址>"              # 支持直接粘贴 GitLab 页面地址（见下方说明）
    sub_path: "<子路径>"            # 仅 monorepo 需要，否则省略
    language: "<语言>"
    depends_on: [<依赖服务ID列表>]
    description: "<服务描述>"
    client_repos:                   # 可选：不同客户的仓库地址
      客户A: "https://old-gitlab.example.com/xxx.git"
      客户B: "git@another-git:xxx.git"
      客户C:
        repo: "/data/customer_code/xxx"
        sub_path: "src"             # 该客户的子路径不同时才需要
```

**repo 支持直接粘贴 GitLab/GitHub 页面地址**，系统会自动解析出仓库地址、分支和子路径：

```yaml
# 用户提供的地址：
repo: "http://gitlab.whup.com/UPService-HQSystem/Data_Servers/tree/dev/DbQueryServer"
# 自动解析为：仓库 Data_Servers.git，默认分支 dev，子路径 DbQueryServer
# 不需要手动拆分 repo 和 sub_path

# 以下格式都支持自动解析：
# http://gitlab.example.com/group/project/tree/branch/path
# http://gitlab.example.com/group/project/-/tree/branch/path
# http://gitlab.example.com/group/project.git          （普通 git 地址也行）
```

所以当用户提供 GitLab 页面链接时，直接写入 `repo` 字段即可，不需要手动提取仓库地址和子路径。

### 第四步：验证

1. 确认 repo 路径存在（本地路径检查目录，远程 URL 检查格式）
2. 如果有 `depends_on`，确认依赖的服务已在 `services.yaml` 中注册（未注册的提醒用户后续添加）
3. 用 `read_file` 读取写入后的文件，确认格式正确

## repo 支持的三种格式

### 1. 本地 git 仓库

```yaml
repo: "/data/repos/market_gateway"
```

最常见的场景。AI 用 `switch_service` 加载时通过 git worktree 切换版本，不影响原仓库。

### 2. 远程 git URL

```yaml
repo: "https://gitlab.example.com/backend/auth.git"
# 或
repo: "git@gitlab.example.com:backend/auth.git"
```

首次使用时自动 clone 到本地。后续使用自动 fetch 更新。submodule 会自动拉取。

### 3. 本地普通目录（非 git）

```yaml
repo: "/data/customer/legacy_code"
```

适用于客户提供的代码包解压后的目录，没有 git 历史。加载时会复制到 session 隔离目录。

## 客户仓库映射（client_repos）

同一个服务，不同客户的代码可能在不同的 git 仓库（常见于仓库迁移过的场景）。用 `client_repos` 配置客户名到仓库的映射：

```yaml
trade_engine:
  name: "交易引擎"
  repo: "https://new-gitlab.example.com/trading/engine.git"   # 标准仓库
  language: "C++"
  description: "核心交易撮合引擎"
  client_repos:
    # 简写：客户名 → 仓库地址
    客户A: "https://old-gitlab.example.com/legacy/trade-engine.git"
    客户B: "git@internal-git:trading/engine-v2.git"

    # 完整格式：客户名 → {repo, sub_path}
    客户C:
      repo: "/data/customer_code/clientC/trade_engine"
      sub_path: "src"    # 该客户的目录结构不同
```

**使用方式：** 用户在对话中说"客户A的交易引擎 v2.3.1 有问题"，AI 调用：
```
switch_service(service="trade_engine", version="v2.3.1", client="客户A")
```
自动从客户A的仓库拉取 v2.3.1 版本代码。

**版本号不需要在配置中写死**，用户在对话中提供即可。没有指定版本时默认加载最新代码。

**典型场景：**
- git 仓库做过迁移，不同客户的代码在不同的 gitlab 地址
- 某些客户的代码是离线提供的，放在本地目录
- monorepo 重构过目录结构，某些客户的子路径不同

## 用户上传代码压缩包

如果用户在对话中上传了代码压缩包（zip/tar.gz），AI 不需要在 services.yaml 中注册，直接告知用户代码已加载，然后用 search/read_file 分析即可。

上传的代码会自动解压到 session 隔离目录，不同用户互不影响。

## 注意事项

- 服务 ID 使用小写字母和下划线，如 `market_gateway`
- `depends_on` 中的 ID 必须与其他服务的 ID 一致
- 同一个 monorepo 可以注册多个服务，通过 `sub_path` 区分
- description 要简洁明了，说明服务的核心职责
- 远程 git URL 需要服务器有访问权限（SSH key 或 HTTPS token）
