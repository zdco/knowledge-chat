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
- **版本映射**（可选）：客户环境的版本号对应的 git commit/tag

### 第三步：写入 services.yaml

用 `read_file` 读取当前 `services.yaml`，在 `services:` 下追加新服务配置：

```yaml
services:
  <service_id>:
    name: "<中文名称>"
    repo: "<仓库路径或远程URL>"
    sub_path: "<子路径>"          # 仅 monorepo 需要，否则省略
    language: "<语言>"
    depends_on: [<依赖服务ID列表>]
    description: "<服务描述>"
    versions:                     # 可选：版本别名映射
      v2.3.1: "abc1234"          # 客户版本号 → git commit hash
      生产环境: "release/2.0"     # 中文别名也可以
```

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

首次使用时自动 clone 到本地（`--no-checkout`，只下载 git 对象，不占用额外空间）。后续使用自动 fetch 更新。

### 3. 本地普通目录（非 git）

```yaml
repo: "/data/customer/legacy_code"
```

适用于客户提供的代码包解压后的目录，没有 git 历史。加载时会复制到 session 隔离目录。

## 版本映射（versions）

当客户运行的版本在 git 分支/tag 中找不到时，需要手动映射：

```yaml
versions:
  v2.3.1: "abc1234def5678"     # 版本号 → commit hash
  v2.2.0: "release/2.2.0"     # 版本号 → 分支名
  客户A生产: "abc1234"          # 中文别名
  客户B生产: "def5678"
```

**典型场景：**
- 客户跑的是很老的版本，仓库里已经没有对应的分支
- 客户的版本号和 git tag 命名规则不一致
- 需要同时对比多个客户的不同版本

**如何获取 commit hash：**
- 让用户提供部署时的版本信息（构建号、commit hash）
- 或者根据用户提供的版本发布时间，用 `git log --before="2025-01-01"` 定位

## 用户上传代码压缩包

如果用户在对话中上传了代码压缩包（zip/tar.gz），AI 不需要在 services.yaml 中注册，直接告知用户代码已加载，然后用 search/read_file 分析即可。

上传的代码会自动解压到 session 隔离目录，不同用户互不影响。

## 注意事项

- 服务 ID 使用小写字母和下划线，如 `market_gateway`
- `depends_on` 中的 ID 必须与其他服务的 ID 一致
- 同一个 monorepo 可以注册多个服务，通过 `sub_path` 区分
- description 要简洁明了，说明服务的核心职责
- 远程 git URL 需要服务器有访问权限（SSH key 或 HTTPS token）
