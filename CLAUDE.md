# CLAUDE.md

本文件是 Claude Code 的项目级指令，Claude 在本项目中工作时必须遵守以下规则。

## 变更日志

每次对项目进行变更（功能新增、bug 修复、配置修改、重构等），必须同步更新 `CHANGELOG.md`：

- 格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 规范
- 记录在 `[Unreleased]` 下对应的分类中：`Added` / `Changed` / `Fixed` / `Removed` / `Deprecated`
- 每条记录用简洁中文描述变更内容

## 自动提交

完成变更或 bug 修复后，自动执行 git 提交：

- commit message 使用中文，格式：`<type>: <简要描述>`
- type 取值：`feat`（新功能）、`fix`（修复）、`docs`（文档）、`refactor`（重构）、`chore`（杂项）
- 示例：`fix: 修复工具调用时黑框被压缩的布局问题`
- 每个独立的变更单独提交，不要把不相关的改动混在一起

## 发版

当用户说"发版 x.x.x"时，执行以下操作：

1. 检查 `CHANGELOG.md` 的 `[Unreleased]` 下是否有内容，如果为空则提示用户并中止
2. 将 `[Unreleased]` 下的内容移到新版本号下，格式：`## [x.x.x] - YYYY-MM-DD`
3. 保留一个空的 `[Unreleased]` 段落在最上方
4. 提交：`chore: release vx.x.x`
5. 打 git tag：`vx.x.x`

版本号遵循 [Semantic Versioning](https://semver.org/)：
- 主版本号（x.0.0）：不兼容的重大变更
- 次版本号（0.x.0）：新增功能，向下兼容
- 修订号（0.0.x）：bug 修复，向下兼容

## 代码变更原则

- 修改任何文件前，必须先读取该文件内容，理解现有逻辑后再动手
- `knowledge/*/data/` 下是用户的知识域数据，禁止修改或删除，除非用户明确要求
