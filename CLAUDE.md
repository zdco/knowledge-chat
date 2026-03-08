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

1. 将 `CHANGELOG.md` 中 `[Unreleased]` 下的内容移到新版本号下，格式：`## [x.x.x] - YYYY-MM-DD`
2. 保留一个空的 `[Unreleased]` 段落在最上方
3. 提交：`chore: release vx.x.x`
4. 打 git tag：`vx.x.x`
