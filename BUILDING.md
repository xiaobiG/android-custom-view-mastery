# 构建与阅读说明

## 依赖

- Node.js 18 或更高版本（CI 使用 Node.js 22）
- Python 3.11 或兼容版本（仅一键静态阅读服务使用）

安装锁定依赖：

```bash
npm ci
```

## 质量检查与静态构建

```bash
npm run check
npm run build
```

VitePress 将静态站点输出到：

```text
dist/
```

## 稳定本地阅读

Windows 下运行：

```text
read.cmd
```

或执行：

```bash
npm run read
```

脚本会在 `dist/` 缺失或书稿较新时自动运行检查和构建，然后只监听本机：

```text
http://127.0.0.1:4000/
```

这是一种纯静态 HTTP 阅读方式，适合长时间浏览。按 `Ctrl+C` 停止服务。

> 不要直接打开 `dist/index.html`。VitePress 的路由和本地搜索应通过 HTTP 地址使用。

## 编辑预览

编辑内容时使用 VitePress 开发服务器：

```bash
npm run dev -- --port 4000
```

Windows 下可运行 `serve.cmd`。开发服务器固定监听 `127.0.0.1`，不暴露到局域网。

## 依赖安全边界

```bash
npm run audit
```

该命令以 Critical 为阻断阈值。VitePress/Vite 及其开发服务器的已知审计项应随上游修复及时升级；本项目的开发服务器只绑定 localhost，部署产物 `dist/` 是不含 Node.js 运行时的纯静态文件。不要使用本地开发服务器处理不受信任的项目内容。

CI 以固定提交 SHA 引用 GitHub Actions，并执行：依赖安装、审计、书稿检查、VitePress 构建和静态产物上传。该 artifact 仅供具有仓库访问权限的成员下载；公开 Pages 未启用。
