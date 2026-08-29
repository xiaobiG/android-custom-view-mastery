# ROADMAP · v2.0 改版蓝图

> 状态：**执行中**。本文档跟踪《Android 自定义控件进阶》v2.0 全面改版的阶段、任务与验收。
> 技术栈（VitePress 1.6.4、极简黑白主题）与写作规范（`WRITING_GUIDE.md`）保持不变。

## 版本定位

v2.0 以「事实核验 → 一致性修复 → 补齐内容 → 薄弱加强 → 工具链」五线推进，将 58 页教材
升级为逐文件经 API 级审校、覆盖四大新方向、可一键验收发布的工程化教材（62 页）。

## 背景：v1 全面审查结论（已执行）

三区并行审查（核心机制 21 章 / 进阶 23 章 / 案例+附录+结构）并对照官方 API 与 AOSP 核验：

- **技术硬错误：未发现高置信度事实错误**；5 处需人工核验项已逐条处理（见 M0）。
- 一致性问题约 12 处（代码/正文矛盾、死代码、未定义变量、双首页路由错位等）已修复。
- 关键遗漏 12 项与薄弱讲解 14 处已补齐/加强（见 M1/M2 清单）。
- 工具链缺口（外部链接不校验、无孤儿检测）已修复（见 M3）。

## 里程碑

### M0 · 事实核验 + 一致性修复（已完成 ✅）

- 核验并修正：`multi-input.md` 滚轮符号（与 AOSP `-vscroll*factor` 一致并加注）、
  `fling-scroll.md` 多指指针切换误用 `tracker.clear()`、`physics.md` FlingAnimation 越界
  说法、`frame-budget.md` `frameDurationCpuMs` API 31 标注、`input-testing.md` Compose
  版本锁定要求。
- 一致性修复 12 处：全局变量封装、`layout_breakLine` 对齐、死代码清理、未定义变量、
  未读取属性、恒真空断言、同名 StepperView 拆分（`StepCounterView`/`StepSelectorView`）、
  附录表述修正等。
- 案例修复 4 处：diagram-editor 补状态保存与初始化检查、zoomable-chart 生命周期清理、
  circular-progress 无障碍节流、signature-pad 导出尺寸判断。
- **验收**：`validate_book.py` 0 error 0 warning ✅

### M1 · 新增内容（已完成 ✅，58 → 62 页）

新增 4 章：

| 章节 | 主题 |
|---|---|
| `chapters/06-performance/baseline-profile.md` | Baseline Profile 与冷启动优化 |
| `chapters/10-compose/compose-in-view.md` | ComposeView 反向互操作 |
| `chapters/02-canvas/camera-3d.md` | Camera 三维变换 |
| `chapters/03-input/gesture-detectors.md` | 标准手势识别器 |

现有章节补充 10 处：inBitmap、setFrame、Outline/clipToOutline、Radial/Sweep/ComposeShader
与 ColorFilter、onRestoreInstanceState 时机与 setSaveEnabled、Choreographer 补充 API、
Robolectric `@GraphicsMode(NATIVE)`、labelFor/importantForAccessibility/live region、
TYPE_NON_TOUCH fling 代码。

### M2 · 薄弱讲解加强（已完成 ✅）

getChildMeasureSpec 源码推导、setLayerType 三种绘制目标、OverScroller 摩擦/样条两种求解
模式、事件拦截不再重复询问与 DOWN 复位 disallow、PathMeasure/Path 动画示例、
`setMinimumVisibleChange` 提前停、withLayer() 展开、FrameTimeline 双轨道图示。

### M3 · 工具链与结构（已完成 ✅）

- 新增 `scripts/link_check.py`：并发校验全部外部链接（HEAD→GET 回退、5s 超时、重试、
  跨域重定向提示、allowlist 跳过），接入 `npm run check`。
- `scripts/validate_book.py`：新增孤儿文件检测（content 目录存在但 SUMMARY 未收录即报错）；
  章节总数改为按 SUMMARY 自动计数（删除硬编码 58）；支持 VitePress 绝对路由内链校验。
- 双首页合一：删除 `index.md`，简介与「开始阅读」并入 `README.md`（README 即 `/`，
  前言内容恢复可达）。
- `package.json`：删除无人引用的 `preview` 脚本；`check` 串联 validate + link_check。

## 质量门槛与发布流程（发布前执行）

1. `npm run audit`（critical 阈值）→ `npm run check` 0 error → `npm run build` 全页非空
2. 隐私扫描（git 历史、工作树、封面元数据）
3. `git diff --check`
4. 更新 `QA_REPORT.md`（62 页、新规模数字、链接检查结果）
5. `package.json` → `2.0.0`，打 tag `v2.0.0`，push main 触发 GitHub Pages；发布后抽查
   首页与新章节 URL 返回 200

## 遗留核验项复核记录（2026-08-29 已复核）

| 核验项 | 结论 |
|---|---|
| Baseline Profile 版本矩阵（AGP/macro/profileinstaller） | 与官方文档核对一致：AGP 8.0.0 / benchmark-macro-junit4 1.4.1 / profileinstaller 1.4.1 为最低支持版本；正文已改为确定表述 |
| `View.setCameraDistance` 引入版本 | API 12（`setRotationX/Y` API 11），正文已标注 |
| Robolectric `@GraphicsMode(NATIVE)` | 4.10 引入、默认 LEGACY、4.12 起支持 Windows x86_64，与发布说明一致；正文已定稿 |
| `ViewCompositionStrategy` 引入版本 | Compose 1.1.0 引入；`ComposeView` 自 1.0 稳定；正文已定稿 |
| Fragment 视图树的 `LifecycleOwner` | Fragment 1.2.0 起提供；正文已定稿 |
| Choreographer 补充 API | `setFrameDelay`/`postFrameCallbackDelayed` API 16、`getFrameIntervalNanos` API 17；正文已标注 |
| `View.setUseZeroUnspecifiedMeasureSpec` | API 23；正文已标注 |
| Perfetto FrameTimeline 可用性 | Android 11 / API 30+；正文已标注 |
| `FlingAnimation` 越界行为 | 官方 javadoc：值约束在 min/max 内、到界即停回调 onAnimationEnd；正文已定稿 |
| `withLayer()` 取消恢复 | AOSP `LayerAnimator.onAnimationEnd` 恢复原 layerType（含取消路径）；正文已定稿 |
| diagram-editor 相机恢复约束 | 已补 `Camera.clampScale()` 并在恢复时收敛缩放 |
| focus-testing 资源命名 | `StepperActivity`/`R.id.stepper` 为宿主工程既有资源，正文已加说明，不做强行改名 |
| 需真机验证（无法文档定稿） | ComposeShader 硬件加速非 SRC_OVER 组合、IME insets 厂商差异——正文保留"以真机验证为准" |

`link_check.py` 依赖网络环境，离线时仅输出 WARN 不阻断（既定行为）。

## 后续候选（v2.1+）

- 为新章节补配可运行示例工程（AGP + Kotlin + 单元测试）。
- 术语表与速查表随新章节增量更新。
- 每章「延伸阅读」链接的自动化文字-目标一致性校验。
