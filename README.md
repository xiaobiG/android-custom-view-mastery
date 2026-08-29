# Android 自定义控件进阶

![《Android 自定义控件进阶》封面](assets/cover.png)

一本面向具备 Kotlin 与 Android 基础的进阶教材。内容覆盖 View 测量、布局、绘制、Canvas、手势、ViewGroup、动画、性能、状态、无障碍、测试以及 Compose 互操作。

- 62 个章节与附录页面
- 5 个递进式综合控件案例
- Kotlin 示例、ASCII 流程图、工具类和检查清单

[开始阅读 →](/chapters/00-introduction/how-to-read)

## 阅读本书

Windows 下直接双击：

```text
read.cmd
```

或者在项目目录执行：

```bash
npm ci
npm run read
```

该入口会在需要时检查并构建 VitePress 静态站点，然后在浏览器打开：

```text
http://127.0.0.1:4000/
```

请通过 HTTP 地址阅读，不要直接双击 `dist/index.html`。

## 本地构建

```bash
npm ci
npm run check
npm run build
```

构建产物位于 `dist/`。

编辑书稿并需要热更新时：

```bash
npm run dev -- --port 4000
```

VitePress 主题刻意保持极简黑白文档风格：目录、搜索、章节大纲、上一页/下一页和 Markdown 代码高亮，除此之外不添加复杂页面元素。

## GitHub Pages

此仓库已设置为公开，VitePress 会在 `main` 推送后部署到：

```text
https://xiaobiG.github.io/android-custom-view-mastery/
```

公开站点只包含已通过隐私扫描的书稿；请不要将本地配置、密钥、个人数据或未审查内容提交到 `main`。

详细的阅读、构建和依赖安全边界见 [BUILDING.md](BUILDING.md)。最终验收记录见 [QA_REPORT.md](QA_REPORT.md)。

## 适合读者

- 已掌握 Activity、Fragment、XML 布局与 Kotlin
- 想系统理解 View 底层机制
- 需要开发图表、编辑器、复杂交互控件或组件库
- 正在把传统 View 控件接入 Compose
