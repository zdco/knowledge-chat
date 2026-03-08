# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- 修复工具调用时其它工具黑框被压缩看不见内容的问题（flex-shrink）
- 过滤工具调用间模型输出的无意义占位文本（如单个 "."）
- 修复回复过程中用户滚动后无法继续滚动的问题
- 修复工具调用后正文首字被误过滤丢失的问题

### Changed
- 工具调用状态标识（执行中/完成）移到工具名前面，更直观
- 工具调用块改为浅色风格，减少与正文消息的视觉反差
- 知识域数据文件（knowledge/*/data/）加入 gitignore，不再提交到仓库
- README 更新知识域创建说明，增加 AI_GUIDE.md 使用方式，更新项目结构
