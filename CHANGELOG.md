# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
