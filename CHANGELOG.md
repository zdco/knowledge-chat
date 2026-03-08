# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- 对话分享功能：一键生成固定链接，对方打开即可只读查看完整对话
- 分享页面（share.html）：复用对话样式，只读展示，无 JS 交互
- 分享 API（POST /api/share）：基于内容 SHA-256 生成幂等分享 ID
- search 工具追加 `--exclude-dir=shares` 防止搜索污染分享数据

### Changed
- 所有路由路径简化：`/mds/chat` → `/chat`、`/mds/api/chat` → `/api/chat`、`/mds/wiki/` → `/wiki/`
- domain.yaml 中 wiki 图片引用路径同步更新

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
