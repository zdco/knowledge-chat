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
- **代码仓库路径**：绝对路径
- **子路径**（monorepo 场景）：仓库内的子目录
- **编程语言**：自动识别结果
- **依赖服务**：上下游服务列表
- **服务描述**：一句话说明服务职责

### 第三步：写入 services.yaml

用 `read_file` 读取当前 `services.yaml`，在 `services:` 下追加新服务配置：

```yaml
services:
  <service_id>:
    name: "<中文名称>"
    repo: "<仓库绝对路径>"
    sub_path: "<子路径>"          # 仅 monorepo 需要，否则省略
    language: "<语言>"
    depends_on: [<依赖服务ID列表>]
    description: "<服务描述>"
```

### 第四步：验证

1. 确认 repo 路径存在且是 git 仓库（`list_files` 检查 `.git` 目录）
2. 如果有 `depends_on`，确认依赖的服务已在 `services.yaml` 中注册（未注册的提醒用户后续添加）
3. 用 `read_file` 读取写入后的文件，确认格式正确

## 注意事项

- 服务 ID 使用小写字母和下划线，如 `market_gateway`
- `depends_on` 中的 ID 必须与其他服务的 ID 一致
- 同一个 monorepo 可以注册多个服务，通过 `sub_path` 区分
- description 要简洁明了，说明服务的核心职责
