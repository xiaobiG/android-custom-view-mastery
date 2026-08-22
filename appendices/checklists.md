# 发布前检查清单

本清单用于自定义 View/ViewGroup 与组件库发布门禁。每项应有代码、测试、trace、截图或评审记录作为证据；“本机看起来正常”不是验收结论。

## 1. 性能

### 测量与布局

- [ ] `onMeasure()` 遵守 EXACTLY/AT_MOST/UNSPECIFIED，包含 padding、minimum 与测量状态。
- [ ] 自定义 ViewGroup 正确处理 margin、LayoutParams、GONE 子项与 child measured state。
- [ ] 数据只影响绘制时调用 `invalidate()`；只有尺寸契约变化才 `requestLayout()`。
- [ ] 动画没有无意中逐帧触发整棵 View 树重测/重排。
- [ ] 极端尺寸（0、1 px、超大、wrap_content、match_parent）无溢出或负布局。

### 绘制与内存

- [ ] `onDraw()`、MOVE、帧回调中不解码资源、不做 I/O、不创建大量临时对象。
- [ ] Paint/Path/RectF/Matrix/数组按所有权安全复用，缓存有明确失效条件。
- [ ] `save()`/`restoreToCount()` 成对；`saveLayer()` 范围最小且确有混合需求。
- [ ] 局部更新确有收益时提供 dirty rect；未把复杂无效区域维护当成默认优化。
- [ ] Bitmap 按显示尺寸解码；缓存上限、回收/共享所有权与低内存策略明确。
- [ ] 硬件加速与目标 API 下使用的 Canvas/BlendMode/clip 操作均已真机验证。
- [ ] overdraw、透明层、大阴影和全屏模糊经过 GPU/Perfetto 检查。

### 帧与生命周期

- [ ] 在目标刷新率（60/90/120 Hz）上看 frame timeline，而非假定固定 16 ms。
- [ ] 使用 Macrobenchmark/JankStats/Perfetto 或等价证据覆盖关键交互。
- [ ] 慢帧定位到 UI thread、RenderThread、GPU、I/O 或锁等待，修复基于证据。
- [ ] detach 后 Animator、Choreographer、Scroller、Runnable、监听器全部停止/解绑。
- [ ] 后台/不可见时没有无意义持续重绘；恢复后状态一致。
- [ ] 装饰动画尊重系统动画偏好，禁用动画时业务状态仍能完成。

## 2. 无障碍

### 语义与动作

- [ ] 控件角色、名称、值、状态（选中/禁用/范围）能被辅助技术读出。
- [ ] 点击最终调用 `performClick()` 且 override 调用 `super.performClick()`。
- [ ] 自定义动作通过 accessibility action 暴露，不要求用户只能做复杂手势。
- [ ] 一个 Canvas 内多个交互对象通过 `ExploreByTouchHelper` 或等价方式成为虚拟节点。
- [ ] 动态内容变化按需要发送合适事件/announcement，避免无意义播报风暴。
- [ ] 装饰图形不产生重复语义；关键信息不只靠颜色、位置或动画传递。

### 焦点与可操作性

- [ ] TalkBack/触摸探索可遍历，顺序符合阅读与操作逻辑，无焦点陷阱。
- [ ] 键盘、D-pad、Switch Access 可完成核心流程；焦点样式清晰。
- [ ] Enter/Space/ACTION_CLICK 与触摸点击行为一致。
- [ ] 触摸目标与目标间距合理；扩大命中区时语义边界仍准确。
- [ ] RTL 下阅读、焦点、手势方向与图标镜像符合产品语义。

### 视觉与文字

- [ ] 前景/背景、禁用态、焦点态对比度经过工具检测和人工复核。
- [ ] 字体缩放至少覆盖常用大字号，文字不裁切、不重叠，重要操作仍可达。
- [ ] 高对比度、深色主题、颜色反转/灰阶等目标场景已检查。
- [ ] Accessibility Scanner 与 Espresso AccessibilityChecks 已运行；抑制项精确且有跟踪任务。
- [ ] 至少一次真机辅助技术人工走查，不把自动扫描当作完整证明。

## 3. API 与组件契约

### 构造、属性与主题

- [ ] View 构造函数支持 XML inflation，正确传递 `defStyleAttr/defStyleRes`（若需要）。
- [ ] 自定义属性有命名空间、格式、默认值、范围和错误策略说明。
- [ ] `obtainStyledAttributes()` 使用 `try/finally` 或 `use` 回收 TypedArray。
- [ ] 颜色、文字外观、最小尺寸来自主题/资源，不硬编码产品色值。
- [ ] public API 使用 dp/sp、模型值或语义类型；不把内部 px 缓存泄漏为稳定契约。

### 状态与兼容

- [ ] 可变属性 setter 做相等性检查，并选择 `invalidate()`、`requestLayout()` 或两者。
- [ ] 保存/恢复必要实例状态，包含 `superState`；旋转、进程重建后验证。
- [ ] Drawable state、enabled/pressed/selected/checked 与视觉和语义同步。
- [ ] minSdk 到 targetSdk 的 API 分支有 `Build.VERSION`/AndroidX 兼容路径和测试。
- [ ] Kotlin nullability、线程要求、坐标空间、单位、异常/越界行为写入 KDoc。
- [ ] listener 可清除；回调时机、重入、去抖和是否主线程调用明确。
- [ ] 不持有 Activity/Fragment/Context 的不必要长生命周期强引用。
- [ ] 二进制/源码兼容策略明确；公共名称、资源名和 styleable 变更经过 API diff。

### 互操作

- [ ] 在 RecyclerView 复用、Fragment 重建和 Window attach/detach 中行为正确。
- [ ] Compose `AndroidView` 场景明确 create/update/dispose 与状态单一来源。
- [ ] nested scrolling、WindowInsets、RTL 与可访问性 delegate 不互相覆盖。
- [ ] 文档给出最小用例、属性表、线程/生命周期边界和迁移说明。

## 4. 测试矩阵

### 单元与组件测试

- [ ] MeasureSpec：三种 mode、0/极值、padding、minimum、wrap_content。
- [ ] 几何：Matrix 正逆映射、旋转包围盒、不可逆矩阵、浮点误差容限。
- [ ] 状态机：DOWN/MOVE/UP、CANCEL、pointer 切换、阈值边界与非法序列。
- [ ] setter：不变值不重复刷新；几何变化 requestLayout；纯视觉变化仅 invalidate。
- [ ] saved state：super state、默认值、版本演进和缺失数据。

### 仪器化与端到端

- [ ] Espresso 覆盖点击、拖动、状态断言；异步工作使用 IdlingResource/可测试同步点。
- [ ] 无障碍节点树、动作、范围和焦点顺序有断言。
- [ ] 截图/像素测试覆盖 light/dark、LTR/RTL、字号、密度；基线更新经过人工评审。
- [ ] 真机覆盖 minSdk 代表设备、当前稳定版、不同厂商/刷新率/输入设备。
- [ ] 手势与系统返回、通知打断、父容器拦截、窗口失焦产生 CANCEL 的场景已覆盖。
- [ ] 旋转、分屏、字体/显示大小变化、进程死亡恢复已覆盖。

### 性能与稳定性

- [ ] benchmark 使用 release-like 构建、预热和多次迭代，结果包含分布而非单次数字。
- [ ] 关键手势长时间运行无持续分配增长、泄漏、ANR 或热循环。
- [ ] LeakCanary/heap dump 或等价方法验证 detach/页面退出后控件可回收。
- [ ] StrictMode/日志无主线程 I/O、资源泄漏、错误 API 使用。
- [ ] 混沌输入（快速多指、边缘坐标、重复 attach/detach）不崩溃。

## 5. 发布门禁记录

| 门禁 | 负责人 | 证据 | 结果 |
|---|---|---|---|
| API review |  | KDoc/API diff | ☐ |
| 性能基线 |  | benchmark/Perfetto 链接 | ☐ |
| 无障碍 |  | 自动报告 + 人工走查 | ☐ |
| 测试矩阵 |  | CI/设备矩阵 | ☐ |
| 视觉回归 |  | 基线评审 | ☐ |
| 生命周期/泄漏 |  | heap/LeakCanary 记录 | ☐ |
| 版本与迁移 |  | changelog/migration guide | ☐ |

## 6. 阻断发布的问题

以下任一项默认阻断发布：

- 核心操作无法通过 TalkBack 或键盘完成。
- 常规触摸序列会崩溃、卡死或在 CANCEL 后保留脏状态。
- detach 后持续回调/动画导致泄漏或后台耗电。
- 公共 API 的单位、线程或兼容行为未定义。
- 关键交互存在可复现严重卡顿，却没有 trace 与处置结论。
- 测试仅覆盖 happy path，未覆盖测量模式、多点/CANCEL、配置变化。

## 延伸阅读

- [慢渲染与卡顿](https://developer.android.com/topic/performance/vitals/render)
- [优化自定义 View](https://developer.android.com/develop/ui/views/layout/custom-views/optimizing-view)
- [自定义 View 的无障碍设计](https://developer.android.com/develop/ui/views/layout/custom-views/create-view#accessibility)
- [Espresso 无障碍检查](https://developer.android.com/training/testing/espresso/accessibility-checking)
