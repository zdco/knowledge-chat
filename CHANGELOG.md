# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- 多轮工具调用上下文截断：保留最近 N 轮完整工具结果，更早轮次自动截断到指定字符数，大幅降低 token 消耗（config.yaml `compact_keep_recent` / `compact_max_length` 可配置）
- 文件上传进度条：大文件上传时显示实时进度百分比，上传完成或失败后自动消失
- 文件上传结果提示：上传完成后在聊天区插入持久状态消息，成功绿色、失败红色，切换页面后仍可见

### Fixed
- 修复首次上传文件时因 session_id 为空导致 400 错误的问题，upload 接口在无 session_id 时自动创建

### Changed
- AI_GUIDE_ANALYZER.md 重写批量注册流程：用户提供仓库地址列表 + 补充信息，AI 自动 clone 代码扫描识别语言/框架/描述，生成完整 services.yaml
- AI_GUIDE_ANALYZER.md 新增单个仓库扫描识别规则：按构建文件识别语言、按优先级提取服务名称和描述，覆盖 C++/Java/Go/Rust/Python/C#/JS/TS 等常见语言
- AI_GUIDE_ANALYZER.md 简化单个服务注册流程：去掉手动收集信息步骤，改为 clone 扫描后自动生成配置
- AI_GUIDE_ANALYZER.md clone 时拉取整个仓库并初始化 submodule，子路径项目同时扫描上级目录的构建文件和公共依赖目录，避免遗漏
- AI_GUIDE_ANALYZER.md 注册时自动从服务 ID 生成 PascalCase/kebab-case/全小写别名，确保用户用任何命名风格都能匹配到服务
- AI_GUIDE_ANALYZER.md 移除与注册生成无关的内容（repo 地址格式表、客户仓库映射运行时示例、上传压缩包说明），减少对 AI 生成流程的干扰
- AI_GUIDE_ANALYZER.md 修正步骤顺序（先推断服务 ID 再 clone）、去掉重复的 client_repos 示例、英文服务名称仅作为别名参考而非直接写入 name 字段
- AI_GUIDE_ANALYZER.md 重写服务描述生成规则：要求从入口文件、配置文件、接口定义等多维度扫描，生成包含核心职责、关键技术、对外接口、数据流向的描述，而非简单复制服务名
- AI_GUIDE_ANALYZER.md 新增"刷新服务描述"流程：用户可触发对已注册服务重新扫描代码并更新描述，解决代码更新后描述过时的问题
- AI_GUIDE_ANALYZER.md 服务描述生成规则补充：描述中不包含版本号
- AI_GUIDE_ANALYZER.md 代码扫描新增排除目录规则：跳过 example/test/demo/doc/benchmark 等非业务代码目录，避免误识别
- AI_GUIDE_ANALYZER.md 重写描述生成维度：从业务视角描述（核心职责、数据流向、外部依赖、关键配置），禁止写入类名/方法名/版本号等代码级细节

### Added
- services.yaml 新增 `businesses` 段：按业务线对服务分组（纯标签，不影响逻辑）
- 新增 `scan_service` 工具：扫描服务代码中的依赖线索（配置文件、RPC 接口定义、构建文件、代码引用），与已注册服务交叉匹配，替代静态 `depends_on`
- `list_services` 工具输出按业务线分组显示
- `load_businesses_config()` 函数：加载 services.yaml 中的业务线分组配置
- git clone 失败时自动将 HTTP(S) 地址转为 SSH 格式重试，用户无需手动配置 git credential
- 页面标题旁显示模式标签（"日志分析"或"知识问答"），区分当前运行模式
- 欢迎语按模式区分：日志分析模式显示"上传日志文件，我来帮你分析定位问题"
- AI 回复过程中发送按钮变为"停止"按钮，点击可中断当前回复
- 客户端断开连接（点击停止或关闭页面）后，后端自动停止生成，不再继续调用 AI API
- 后端 SSE 流每 15 秒发送心跳保持连接，防止 nginx/代理超时断开
- 前端 5 分钟无数据自动超时恢复界面并提示，避免永久卡在"思考中"
- log-analyzer 的 session ID 随对话历史一起持久化，切换历史对话或刷新页面后不会丢失，避免重复拉取代码
- log-analyzer 模式下 search 搜索无结果时不再 fallback 到 knowledge 目录
- log-analyzer 模式下 search 支持更多文件类型（.java/.py/.go/.rs/.proto/.thrift/.json/.ini 等）
- 上传按钮显示时使用 flex 布局，SVG 图标和文字正确对齐

### Changed
- services.yaml 去掉 `depends_on` 字段，依赖关系由 AI 通过 `scan_service` 从代码中实时发现
- log-analyzer 模式下跳过 knowledge 目录的初始化和热加载，避免无意义的目录扫描开销
- 上传文件按钮从纯图标（📎）改为带文字的按钮（📎 上传文件），更直观易识别
- log-analyzer 模式下移除 write_file 工具，search 工具描述改为"在已加载的服务代码中搜索"，避免 AI 误搜知识域目录
- AI_GUIDE_ANALYZER.md 简化注册流程：用户只需提供仓库地址列表和业务线归属，不需要梳理依赖关系
- system prompt 不再列出静态依赖关系，改为按业务线列出服务清单，引导 AI 用 `scan_service` 发现依赖

### Removed
- 移除 `trace_dependency` 工具和 `get_dependency_tree()` 函数（被 `scan_service` 替代）

### Fixed
- 日志分析模式和知识问答模式的浏览器对话历史不再混在一起，localStorage key 加入运行模式区分
- git clone/fetch HTTP 地址时禁止弹出交互式认证提示（GIT_TERMINAL_PROMPT=0），避免进程卡住，认证失败后自动转 SSH 重试
- log-analyzer 模式下 search/read_file/list_files/glob 限制在当前 session 的 worktree 和 uploads 目录内，避免跨 session 访问
- 日志分析模式（log-analyzer）：config.yaml 新增 `mode` 字段切换运行模式，`analyzer` 配置段定义 session/worktree 参数
- 服务注册表（services.yaml）：定义微服务名称、仓库路径、语言、依赖关系，支持 AI 通过对话自动生成
- services.yaml `repo` 支持三种格式：本地 git 仓库、远程 git URL（自动 clone）、本地普通目录（自动复制）
- services.yaml `client_repos` 字段：不同客户映射到不同仓库地址，AI 根据用户提到的客户名自动匹配
- 自动解析 GitLab/GitHub 仓库 URL 中的分支和子路径（如 `/tree/dev/DbQueryServer` → 分支 dev、子路径 DbQueryServer）
- 支持用户上传代码压缩包作为代码来源（`setup_from_upload`），自动解压到 session 隔离目录
- AI_GUIDE_ANALYZER.md：服务注册指南，AI 按指南自动扫描代码仓库并生成 services.yaml 配置
- log_analyzer.py：SessionManager 管理分析会话（创建/清理/过期回收）、git worktree 版本隔离、文件上传处理（zip/tar.gz 自动解压）、日志预处理（ERROR 摘要提取、按级别/关键词/时间范围过滤）
- 新增 4 个日志分析专用工具：read_log（日志过滤读取）、trace_dependency（依赖链查询）、switch_service（加载服务代码 worktree）、list_services（列出已注册服务）
- 文件上传路由（POST /api/upload）：支持日志文件、压缩包、截图上传，压缩包自动解压，图片返回 base64 供多模态消息使用
- chat.html 增强：拖拽上传文件、Ctrl+V 粘贴截图、附件按钮、上传预览区、图片多模态消息支持
- 多模态图片支持：用户上传/粘贴的截图作为 base64 图片消息发送给 AI，支持日志截图识别
- agent_engine.py 支持 session_id 透传：run_agent_stream → 流式调用 → exec_tool，log-analyzer 模式下动态构建 system prompt
- Office/PDF 文本缓存预处理：启动时将二进制文件转为纯文本缓存到 `.text_cache/` 目录，search 工具 grep 搜缓存文件替代实时解析，read_file 优先读缓存
- watchdog 监听 Office/PDF 文件变更，自动增量更新文本缓存（新增/修改/删除）
- `confluence_zip` 配置支持列表格式，可同时导入多个 Confluence 导出 zip 包
- PDF 文件检索支持：`read_file` 和 `search` 工具支持读取和搜索 PDF 文件内容，基于 pdfplumber 按页提取文本
- config.yaml `server` 段新增 `title` 字段，网页标题可通过配置文件修改，不再硬编码
- 工具安全加固：bash 工具执行前检查危险命令黑名单（rm -rf、mkfs、dd、fork bomb 等），命中则拒绝执行
- 工具安全加固：system prompt 中数据库密码改为掩码显示，AI 无法向用户透露密码
- 工具安全加固：run_python 执行时自动注入数据库密码为环境变量，代码通过 os.environ 获取
- 工具安全加固：system prompt 追加安全规则，从源头约束 AI 不执行破坏性操作、不泄露敏感信息
- 工具安全加固：bash 增加 base64 解码执行、eval 等绕过手法检测
- 工具安全加固：run_python 增加危险代码检查（os.system、subprocess、shutil.rmtree 等），禁止执行系统命令
- 工具安全加固：所有工具输出统一脱敏，自动替换数据库密码和 API Key 为掩码

### Changed
- PDF 解析引擎从 pdfplumber 切换为 PyMuPDF（fitz），全量缓存构建速度提升约 5 倍

### Fixed
- bash 安全规则误拦 `2>/dev/null` 重定向：修正正则排除 `/dev/null`，只拦截写其他设备文件
- system prompt 增加 run_python 可用包列表提示，避免模型猜错 PDF/Excel 库导致 import 失败
- 工具详情展开后鼠标滚轮被内部 pre 元素捕获导致页面无法滚动：去掉嵌套滚动，改为 overflow-y:hidden + 展开全部按钮
- AI 回复过程中展开工具详情导致自动滚动失效、内容显示不全：展开前记录滚动位置，展开后恢复自动跟随
- AI 回复结束后前端卡住不恢复发送按钮：收到 done 事件后主动关闭 SSE 流并退出读取循环
- bash 工具执行外部 Python 脚本时注入 `.venv/bin` 到 PATH，解决找不到虚拟环境依赖包的问题
- 同一 IP 部署多个服务时历史会话列表混在一起，localStorage key 加入端口号和路径区分
- nginx 反代到不同路径时前端 API 请求和分享链接地址错误，改为从页面路径动态推算
- 分享链接复制按钮在非 HTTPS 环境下点击无反应，改用兼容的 execCommand 降级方案

## [0.3.1] - 2026-03-09

### Added
- 启动时显示局域网访问地址，方便从其他设备访问或复制链接
- start.sh 支持 `-d` 参数后台运行，日志输出到 output.log
- 所有路由统一添加 `/kchat` 前缀，便于 nginx 反向代理一条规则转发
- config.yaml 新增 `oracle_client_path` 配置项，支持设为 `auto` 自动下载安装 Oracle Instant Client，run_python 执行时自动注入 thick 模式初始化和 LD_LIBRARY_PATH
- AI_GUIDE.md 新增数据库知识域 prompt 编写规则：禁止猜测表名字段名、连接代码无需手动初始化 client、提供元数据查询模板
- 工具执行完进入下一轮 AI 思考时，前端重新显示"思考中..."提示，避免用户以为卡住

### Fixed
- start.sh 移除强制环境变量检查，支持仅通过 config.yaml 配置 API 密钥启动
- start.sh 自动检测并安装缺失的 python3-venv 系统包（通过检测 ensurepip 模块），无需用户手动处理
- start.sh 检测不完整的 .venv 目录（缺少 activate）时自动重建，避免上次创建失败后卡住

### Changed
- 环境变量重命名：`ANTHROPIC_AUTH_TOKEN` → `AI_CHAT_API_KEY`、`ANTHROPIC_BASE_URL` → `AI_CHAT_BASE_URL`、`ANTHROPIC_MODEL` → `AI_CHAT_MODEL`，避免与 Claude Code 等工具的环境变量冲突
- 私有知识域的 domain.yaml 从 git 中移除并加入 gitignore，防止提交到 GitHub 泄露信息
- 优化 README.md：修正过时路径和配置示例，新增手动安装说明、功能特性段落、API 格式说明，补全项目结构

## [0.3.0] - 2026-03-08

### Added
- 对话分享功能：一键生成固定链接，对方打开即可只读查看完整对话
- 分享页面（share.html）：复用对话样式，只读展示，无 JS 交互
- 发送消息后显示"思考中..."加载指示器，AI 开始回复或调用工具后自动消失
- 分享 API（POST /api/share）：基于内容 SHA-256 生成幂等分享 ID
- search 工具追加 `--exclude-dir=shares` 防止搜索污染分享数据
- 支持 OpenAI API 格式：新增 `api_format` 配置项，可选 `anthropic` 或 `openai`，不设置时根据 `base_url` 是否含 `/v1` 自动判断。非 Claude 模型建议用 openai 格式

### Changed
- 缩小对话区域中回复文本与工具块之间的间距（gap 16px → 8px）
- 默认模型从 `claude-opus-4-6` 改为 `MiniMax-M2.5`
- 所有路由路径简化：`/mds/chat` → `/chat`、`/mds/api/chat` → `/api/chat`、`/mds/wiki/` → `/wiki/`
- domain.yaml 中 wiki 图片引用路径同步更新

### Fixed
- 修复日志 `request_id` 字段缺失导致启动报错：将 filter 从 root logger 移到 handler 上，确保子 logger 的日志也能注入 request_id
- 修复 Confluence 导航树解析不完整：兼容每个子页面独立 `<ul>` 的 HTML 结构，从 3 个页面恢复到完整 84 个页面
- Confluence 转换跳过空内容页面，不再生成空 Markdown 文件
- Confluence 转换时将页面标题作为 H1 写入 Markdown 开头，使按标题关键词搜索能命中文件
- 修复 `PROJECT_ROOT` 路径计算错误（指向 `/mnt` 而非项目目录），导致搜索工具找不到文件或扫描超时
- 工具执行增加必填参数校验，模型传空参数时返回友好提示而非抛出 KeyError
- 空参数的工具调用不再显示在前端界面，避免刷屏；同时标记 `is_error` 帮助模型理解失败
- 连续 3 轮工具调用参数全部为空时自动终止循环，防止模型陷入死循环浪费轮次
- system prompt 自动检测 wiki 目录并显式提示搜索，引导能力较弱的模型也能搜到 Confluence 文档
- 搜索工具在指定子目录无结果时，自动扩大到整个 knowledge/ 目录重搜，避免模型选错知识域导致搜不到
- 搜索工具启用扩展正则（`grep -E`），支持 `|` 或运算符等语法，修复模型使用正则交替搜索无结果的问题

## [0.2.0] - 2026-03-08

### Added
- 完善服务日志记录：配置 logging 格式、console + 文件双输出、按天轮转保留 30 天
- 请求级 request_id：每条日志携带 8 位请求 ID，可关联同一请求的全链路日志
- 请求入口日志：记录用户消息摘要和请求来源 IP（支持 X-Forwarded-For / X-Real-IP）
- AI 调用日志：记录每轮 API 调用、token 用量、异常堆栈
- 工具执行日志：记录工具名称、参数、耗时、结果长度、异常堆栈
- config.yaml 新增 logging 配置段（level / file / backup_days）
- search 工具增加 --exclude-dir=logs 防止搜索污染
- Confluence ZIP 自动转换：服务启动时检测 domain.yaml 中的 `confluence_zip` 字段，自动将 Confluence 导出的 HTML zip 包转换为 Markdown + 图片，按导航层级组织目录结构
- Wiki 图片 Web 路由：新增 `/mds/wiki/<domain>/<path>` 路由，支持前端直接展示 Confluence 文档中的图片
- 新增 beautifulsoup4、markdownify 依赖

### Fixed
- 修复 memory 记忆功能时序问题：将"先回答再记录"改为"回答时同步写入笔记"，避免回答完成后无执行窗口导致笔记从不触发
- 调整 memory 记录条件：改为"反复搜索仍难以定位、多线索交叉验证才得出的结论"，避免常规问答频繁触发

## [0.1.0] - 2026-03-08

### Added
- AI 学习记忆机制：AI 可将有价值的结论、纠正、隐性知识写入 memory 笔记，下次通过 search 检索复用，实现自我进化学习
- `run_python` 工具：支持执行 Python 代码，可用于数据库查询和数据分析
- 知识域数据库配置：domain.yaml 新增可选 `databases` 字段，配置数据库连接信息后 AI 自动生成代码查询
- 数据库驱动依赖：新增 pymysql、oracledb、pandas
- 对话式知识域创建：用户可直接在对话中提供文件路径，AI 自动创建知识域并热加载生效
- 知识域热加载：监听 knowledge/ 目录下 domain.yaml 的变化，自动重新加载知识域和 system prompt，无需重启服务
- Office 文件解析支持：`read_file` 工具支持读取 `.xlsx`/`.xls`/`.docx`/`.pptx` 文件，`search` 工具支持搜索 Office 文件中的关键词

### Fixed
- 修复工具调用时其它工具黑框被压缩看不见内容的问题（flex-shrink）
- 过滤工具调用间模型输出的无意义占位文本（如单个 "."）
- 修复回复过程中用户滚动后无法继续滚动的问题
- 修复工具调用后正文首字被误过滤丢失的问题

### Changed
- AI_GUIDE.md 知识域扫描分析按场景分类（代码工程/接口定义/文档知识库/配置运维/数据库），各场景有针对性的分析策略
- AI_GUIDE.md prompt 编写指南：新增通用结构模板、反面示例、五种场景的高质量 prompt 示例
- `AI_GUIDE.md` 从 `knowledge/` 移到项目根目录
- 删除 `DEV_GUIDE.md`，扩展工具说明合并到 README
- 工具调用状态标识（执行中/完成）移到工具名前面，更直观
- 工具调用块改为浅色风格，减少与正文消息的视觉反差
- 知识域数据文件（knowledge/*/data/）加入 gitignore，不再提交到仓库
- README 更新知识域创建说明，增加 AI_GUIDE.md 使用方式，更新项目结构
