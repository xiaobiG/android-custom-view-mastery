# 构建与依赖说明

## 本地构建

需要 Node.js 18 或更高版本。仓库包含 `package-lock.json`，请使用 `npm ci` 进行可复现安装：

```bash
npm ci
npm run check
npm run build
```

生成的静态站点位于 `_book/`。

## 本地阅读与链接跳转

HonKit 的目录跳转、上一页/下一页和搜索依赖 HTTP 环境。直接双击 `_book/index.html` 会使用 `file://` 协议，可能被浏览器或内嵌预览容器限制，表现为链接点击后不跳转。

Windows 下推荐运行：

```text
read.cmd
```

也可以执行：

```bash
npm run read
```

该入口会在 `_book` 缺失或源码更新时自动检查并构建，然后用 Python 静态服务器打开 `http://127.0.0.1:4000/`。它适合长时间阅读，不运行 HonKit 的文件监听器。

编辑书稿并需要 LiveReload 时，可使用 `serve.cmd` 或 `npm run serve`。

部署 `_book/` 到任意静态 HTTP 服务器后也可正常导航。`npm run check` 检查目录、内部链接与书稿结构；它不检查外部 URL，外部引用仍需在改动时单独验证。

## HonKit 依赖审计说明

截至本项目锁定的 HonKit 6.2.2，其传递依赖 `immutable` 旧版本存在拒绝服务类安全公告，且 npm 当前没有兼容的自动修复。直接用 npm `overrides` 升级到 `immutable` 4.3.9 会破坏 HonKit 所依赖的旧 Record/Seq API，并导致构建时报 `plugins.valueSeq is not a function`。

因此本项目遵循以下边界：

1. HonKit 仅作为开发依赖，在本地或受控 CI 中处理本仓库审查过的 Markdown。
2. 不使用此构建流程处理第三方上传或不受信任的书稿。
3. `_book/` 是纯静态产物，部署时不携带 Node.js 或 HonKit 运行时。
4. 上游提供兼容修复后，应升级 HonKit、重新执行 `npm audit` 和完整构建。

这是一项已知且显式接受的构建期风险，不代表生成的静态页面包含同一运行时漏洞。
