# 书稿写作规范

1. 面向已有 Android/Kotlin 基础的读者，先讲为什么，再讲机制、实现、验证和陷阱。
2. 示例默认 Kotlin；导入、API 级别与 AndroidX 类型应明确，禁止伪造不存在的 API。
3. 每个技术章节至少包含：学习目标、核心机制、ASCII 流程图或结构图、代码示例、常见陷阱、实践检查清单、小结；前言、导读与附录按用途组织，不强套此结构。
4. 使用 `> **注意**`、`> **性能提示**`、`> **无障碍提示**` 标注重要内容。
5. ASCII 图置于 `text` 代码块，建议不超过 88 列。
6. 术语首次出现时给出英文名；同一概念全文统一译法，以 [术语表](appendices/glossary.md) 为准（例如 nested scrolling 统一为“嵌套滚动”）。
7. 外部事实优先链接 Android Developers 官方文档；引用集中放在章末“延伸阅读”。
8. 不把 Compose 说成 View 的简单替代，也不把软件层/硬件层描述成万能优化。
9. 控件状态、动画和监听器在 `onDetachedFromWindow()` 等生命周期中正确释放。
10. 文件名使用英文 kebab-case，标题与正文使用简体中文。
11. 平台与 AndroidX API 在发布前必须对照官方 API Reference 和项目实际 `compileSdk`/依赖版本核验；API level、弃用状态和兼容分支应明确，不能只凭方法名推测。
12. 外部 URL 使用可直接打开的稳定主题页、类页或源码路径，不使用搜索结果页；新增或改动链接后执行链接检查，重定向后的最终页面也应与链接文字相符。
13. 新增、删除或重命名正文/附录时同步更新 `SUMMARY.md`，确保每个 `chapters/`、`examples/`、`appendices/` 下的 Markdown 文件恰好出现一次。
14. README、`BUILDING.md`、`package.json` 与锁文件中的 Node 版本、安装命令、脚本名和产物目录必须一致；发布前以全新依赖安装运行 `npm run check` 与 `npm run build`。
