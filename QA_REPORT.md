# 质量验收报告

## 书稿规模

- `SUMMARY.md` 导航页面：62
- 非空白字符：438,852
- 正文行数：18,023
- Markdown 代码围栏标记：860（约 430 个代码或图示块）
- ASCII/text 图块：150+，未发现超过 100 列的图
- 外部链接出现次数与唯一 URL 数：由 `scripts/link_check.py` 每次检查输出
- 主要来源域名：`developer.android.com`、`cs.android.com`、`perfetto.dev`

## VitePress 构建

- VitePress：1.6.4
- 输出目录：`dist/`
- SUMMARY 导航页面：62/62 已生成且非空
- 总 HTML 页面：67（含导航外的构建、验收与写作辅助页面）
- 封面已输出为哈希化静态资源
- 本地搜索索引约 934 KB，保留以支持全书离线搜索
- 主题：默认文档主题 + 极简黑白 CSS；不使用自定义页面组件或动画

## 自动检查

```bash
npm run audit
npm run check   # validate_book.py + link_check.py
npm run build
git diff --check
```

验收结果：

- Critical 级 npm 审计门槛通过。
- 章节存在性、内部链接（含 VitePress 绝对路由）、最小章节长度、全书体量、标题、代码围栏与 SUMMARY 孤儿文件检查通过：0 errors，0 warnings。
- 外部链接检查（`scripts/link_check.py`）：356 个链接，0 errors（失效链接已修复），偶发网络超时以 WARN 记录。
- VitePress 成功生成静态页面。
- `dist/` 中 62 个 SUMMARY 页面均有对应的非空 HTML 文件。
- 封面、主题 CSS、VitePress 本地搜索索引均已输出。
- Git 空白错误检查通过。
- 章节文本指纹检查未发现异常高相似度章节。

## 本地阅读

- Windows：运行 `read.cmd`
- 命令行：运行 `npm run read`
- 稳定阅读地址：`http://127.0.0.1:4000/`
- 编辑热更新：`npm run dev -- --port 4000`

阅读入口会在书稿较新或 `dist/` 缺失时自动检查并构建，随后用 Python 静态服务器提供内容。不要直接打开 `dist/index.html`。

## GitHub Pages

- 公开地址：[https://xiaobig.github.io/android-custom-view-mastery/](https://xiaobig.github.io/android-custom-view-mastery/)
- 构建方式：GitHub Actions workflow
- HTTPS：强制启用
- Pages 构建与部署工作流：`33186412506`，build 与 deploy 均成功
- 已直接请求公开首页、章节页和封面资源，全部返回 HTTP 200

> GitHub Pages 会公开 `dist/` 的全部内容。公开前已扫描所有可达 Git 历史、当前工作树和封面元数据，未发现密钥、令牌、个人邮箱、用户路径、手机号或图片隐私元数据。

## 人工/代理交叉审查

书稿按目录拆分并行编写后，另由独立审查代理分区复核：

- View/Measure/Layout/Draw、事件与 ViewGroup
- Canvas/Path/Matrix/文字/混合
- 动画、性能、状态与样式
- 无障碍、测试与 Compose 互操作
- 五个综合案例
- 附录、工具类、导航和参考资料

审查重点包括 Android/AndroidX API 名称与签名、坐标和矩阵结论、事件取消、多指 ID、生命周期释放、无障碍虚拟节点、测试 API、版本边界和文档排版。

## 已知边界

1. Markdown 中的代码既包含完整类，也包含教学片段；没有把所有片段拼成单一 Android App 编译。复制片段时需按正文说明补齐包名、资源和依赖版本。
2. 当前 VitePress/Vite 依赖存在 npm 报告的无上游兼容修复的开发服务器审计项。本项目开发服务器固定绑定 `127.0.0.1`，`dist/` 是不含 Node.js 运行时的纯静态文件；不要用开发服务器处理不受信任的项目内容。
3. 自动检查不能替代不同设备、API、字体缩放、RTL、TalkBack 和刷新率上的真机验证。
4. `link_check.py` 依赖网络环境：离线或网络抖动时输出 WARN 不阻断；明确 404/410 才判定坏链。
5. v2.0 新增内容的 API 版本边界已对照官方文档复核定稿（Baseline Profile 版本矩阵、
   `setCameraDistance` API 12、Robolectric GraphicsMode 4.10/默认 LEGACY、
   `ViewCompositionStrategy` 1.1.0、Choreographer API 16/17、
   `setUseZeroUnspecifiedMeasureSpec` API 23、FrameTimeline API 30）；仅 ComposeShader
   硬件加速非 SRC_OVER 组合与 IME insets 厂商行为需真机验证（正文已注明）。

## v2.0 改版记录（2026-08-29）

- 范围：三区全面审查（核心机制 21 章 / 进阶 23 章 / 案例+附录+结构）→ M0 核验与一致性修复 → M1 新增内容 → M2 薄弱加强 → M3 工具链。
- 规模：58 → 62 个导航页；新增 4 章（Baseline Profile、ComposeView 反向互操作、Camera 三维变换、标准手势识别器）。
- 一致性修复：12 处章节/附录问题 + 4 处案例问题（含 diagram-editor 状态保存、zoomable-chart 生命周期清理）。
- 工具链：新增 `link_check.py` 外部链接校验；`validate_book.py` 增加孤儿文件检测、章节数动态化、绝对路由内链支持；双首页合一（README 即首页）；移除未使用的 `preview` 脚本。
- 全量验证：`validate_book.py` 0 error 0 warning；`link_check.py` 0 error；VitePress 构建成功（67 个 HTML）。
- 发布流程（audit、隐私扫描、2.0.0 版本与 `v2.0.0` tag）尚未执行，由版本发布时按 [ROADMAP.md](ROADMAP.md) 完成。
