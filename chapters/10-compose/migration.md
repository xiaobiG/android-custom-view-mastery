# 迁移决策与边界

迁移不是把每个 `View` 逐行翻译成 Composable。真正的目标是降低变化成本，同时维持行为、
性能、无障碍与测试可靠性。有些控件适合立刻重写，有些应长期保留在 `AndroidView` 边界，
还有些应先抽离状态与算法，再决定渲染技术。

## 学习目标

- 用风险、收益和依赖关系选择迁移顺序。
- 划分可回滚的互操作边界，而不是制造双向状态网。
- 识别适合保留 View、包装 View 或重写 Compose 的场景。
- 建立包含性能、输入、无障碍、保存状态与测试的验收门槛。

## 1. 先迁移所有权，再迁移像素

旧控件常把五类责任混在一个类中：

```text
┌──────────────── Legacy Custom View ────────────────┐
│ 业务状态 │ 格式化/算法 │ 手势状态机 │ 绘制 │ 资源生命周期 │
└────────────────────────────────────────────────────┘
```

直接重写会同时改变所有变量，难以判断回归来自哪里。更安全的顺序是：

```text
阶段 0：测量当前行为，建立截图/手势/无障碍基线
   │
阶段 1：抽出纯 Kotlin 模型、格式化、几何与状态机
   │
阶段 2：Compose 持有业务状态，AndroidView 受控显示
   │
阶段 3：选择一个边界迁移（外壳、输入或绘制）
   │
阶段 4：达到验收门槛后删除旧实现；否则可回滚
```

阶段 2 往往已经带来最大的架构收益：状态进入 `ViewModel`/Compose，旧 View 成为可替换的
渲染后端。此时是否重写绘制，可以基于数据而不是信仰决定。

## 2. 三种策略

### 2.1 长期保留 View

适合：

- 基于 `SurfaceView`、播放器、地图、相机、Web 内容或成熟第三方 SDK；
- 已经高度优化、稳定且重写收益很小的复杂编辑器；
- Android 平台能力主要通过 View API 暴露。

要求是建立窄适配器：不可变输入、事件输出、明确生命周期与测试标签。长期保留不等于把
Activity、Fragment 或整个业务对象传进 View。

### 2.2 AndroidView 过渡包装

适合：

- 页面外壳已迁移，复杂控件暂时保留；
- 需要分批发布、A/B 对比或随时回滚；
- 团队先统一状态所有权，再逐步替换渲染。

包装器本身应被视为正式 API，而不是临时代码堆放处。

```kotlin
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun LegacySignaturePad(
    strokes: List<Stroke>,
    enabled: Boolean,
    onStrokeFinished: (Stroke) -> Unit,
    modifier: Modifier = Modifier
) {
    val latestStrokeFinished = rememberUpdatedState(onStrokeFinished)

    AndroidView(
        modifier = modifier,
        factory = { context ->
            SignaturePadView(context).apply {
                strokeFinishedListener = {
                    latestStrokeFinished.value(it)
                }
            }
        },
        update = { view ->
            view.isEnabled = enabled
            view.submitStrokes(strokes)
        },
        onReset = { view ->
            view.cancelActiveStroke()
            view.clearFocus()
        },
        onRelease = { view ->
            view.strokeFinishedListener = null
            view.release()
        }
    )
}
```

### 2.3 原生 Compose 重写

适合：

- UI 高频迭代，旧 View API 已成为瓶颈；
- 需要 Compose 动画、语义、状态与布局深度协作；
- 控件规模可控，且团队能建立等价性能与输入测试；
- 重写能删除多层适配器和双栈维护成本。

重写时复用纯 Kotlin 状态机与几何算法，不要同时重写数学、交互和渲染。

## 3. 迁移决策表

先给每项按低/中/高评估，再选择策略：

| 评估维度 | 保留 View 倾向 | AndroidView 过渡倾向 | Compose 重写倾向 |
|---|---|---|---|
| 平台/第三方 View 绑定 | 高 | 中到高 | 低 |
| 自定义 Surface/相机/地图 | 高 | 高 | 低，除非已有可靠 Compose API |
| 业务状态与 View 耦合 | 先解耦 | 先受控包装 | 解耦后再重写 |
| UI 变化频率 | 低 | 中 | 高 |
| Compose 语义/布局协作需求 | 低 | 中 | 高 |
| 现有 View 性能成熟度 | 高且已验证 | 高 | 低或难维护 |
| 无障碍债务 | 可在 View 修复 | 边界先修复 | 重写有明确改善时 |
| 自动化测试覆盖 | 完整 | 可建立双边界测试 | 有基线后重写 |
| 回滚要求 | 低改动最安全 | 最适合双实现切换 | 需 feature flag/保留旧实现 |
| 团队维护能力 | View 专长为主 | 双栈过渡 | Compose 专长与工具成熟 |

快速决策规则：

```text
是否强依赖 View-only 平台/SDK？ ──是──> 保留 View + 窄包装
              │否
              ▼
状态/算法是否已从 View 解耦？ ──否──> 先解耦，不开始重写
              │是
              ▼
重写收益是否可量化且有回归基线？ ──否──> AndroidView 过渡
              │是
              ▼
性能、输入、无障碍验收能否自动化？ ──否──> 补基线与测试
              │是
              ▼
        小步 Compose 重写 + 可回滚发布
```

## 4. 设计迁移边界

一个好的边界只有三类东西：

1. **不可变输入**：`UiState`、不可变列表、主题 token、可恢复状态。
2. **用户事件**：点击、拖拽完成、值变化、重试；不直接传 View 实例。
3. **生命周期契约**：暂停、重置、最终释放；不依赖 Activity 强转。

```kotlin
data class ChartUiState(
    val series: List<Series>,
    val viewport: Viewport,
    val selectedPointId: String?,
    val loading: Boolean
)

sealed interface ChartEvent {
    data class SelectPoint(val id: String) : ChartEvent
    data class ChangeViewport(val viewport: Viewport) : ChartEvent
    data object Retry : ChartEvent
}

@Composable
fun ChartRoute(
    state: ChartUiState,
    onEvent: (ChartEvent) -> Unit,
    useComposeRenderer: Boolean
) {
    if (useComposeRenderer) {
        ComposeChart(state = state, onEvent = onEvent)
    } else {
        LegacyChartAdapter(state = state, onEvent = onEvent)
    }
}
```

这样的 feature flag 切换共享同一个状态和事件协议，能做真实对比。不要让两个实现各自维护
选中、缩放与加载状态，否则切换时无法判断行为是否等价。

## 5. 按风险切片，而不是按文件切片

推荐迁移切片：

- 先迁移静态外壳、标题、按钮，保留复杂绘制 View；
- 先抽几何与格式化为纯 Kotlin，并用单元测试锁定；
- 保留 View 手势状态机，只迁移状态持有者；
- 或保留 View 渲染，先用 Compose 处理外围筛选和面板；
- 最后处理多指、惯性、文本输入、无障碍虚拟节点等高风险区域。

不推荐“本周迁移所有绘制，下周补测试”。测试基线应早于实现变化。

## 6. 验收矩阵

每个迁移切片至少验证：

| 维度 | 基线/验收方式 | 不可接受的退化 |
|---|---|---|
| 视觉 | 多尺寸、深浅色、RTL、字体缩放截图 | 裁切、基线偏移、颜色/描边错误 |
| 测量布局 | `EXACTLY`/`AT_MOST`、横竖屏、分屏 | 无限尺寸、频繁 requestLayout |
| 输入 | 点击、拖拽、多指、cancel、fling | 双回调、手势卡死、父子冲突 |
| 状态 | 旋转、进程恢复、列表复用、返回栈 | 丢失、串项、重复事件 |
| 性能 | Macrobenchmark/Perfetto、分配、帧时间 | 仅凭主观“更流畅”宣布通过 |
| 无障碍 | TalkBack、键盘、语义断言 | 重复节点、无名称、焦点陷阱 |
| 资源 | 离屏、离页、反复进入、泄漏检测 | 线程/监听器/纹理继续存活 |
| 测试 | Compose + Espresso 边界测试 | 依赖 sleep 或实现细节 |

> **性能提示**：比较必须使用相同设备、数据、构建类型和交互脚本。Compose 首次组合与 View
> 首次 inflate 的成本结构不同，应同时观察冷启动、首次显示和稳态滚动，而不是只取一个平均值。

## 7. 常见迁移反模式

### 7.1 双向镜像状态

```text
Compose selectedId <──监听器/setter──> View selectedId
```

两端都可写会产生循环、竞态和恢复顺序问题。改为 Compose/状态层拥有业务状态，View 只保留
手势中的瞬时状态，并在手势完成或明确节点上报事件。

### 7.2 每次重组重建 View

通过变化的 `key` 强制刷新看似简单，却会丢失焦点、滚动与缓存，并掩盖 `update` 不完整。
应修复幂等绑定，只在 View 类型/不可变构造契约真正变化时更换实例。

### 7.3 同时改架构、视觉和手势

一次 PR 改三个维度，截图变了、手势也坏了时无法二分。每个切片只改变一个主要变量，保持
旧实现可对照。

### 7.4 永久双栈

过渡层没有退出条件，会把每个功能和测试成本翻倍。创建迁移项时就写清：保留 View 的长期
理由，或删除旧实现的量化门槛和负责人。

### 7.5 把 Compose 当性能优化开关

技术栈不保证性能。大量状态读取、频繁 Path 分配、无界重组与昂贵 AndroidView update
同样会掉帧。优化必须基于 trace 和 benchmark。

## 8. 分阶段迁移示例

以可缩放折线图为例：

1. **建立基线**：保存 1/10/100k 点截图；录制缩放、平移、fling 脚本；记录帧时间。
2. **抽纯逻辑**：`ViewportReducer`、点抽稀、坐标变换成为纯 Kotlin，并补单元测试。
3. **受控包装**：Compose 持有 `ChartUiState`，`AndroidView.update` 只投影状态。
4. **迁移外围**：图例、筛选器、加载/错误态改为 Compose；图表 View 保留。
5. **验证输入边界**：嵌套滚动、父层手势、TalkBack 和键盘焦点。
6. **实验渲染器**：用相同 state/event 协议实现 `ComposeChart`，feature flag 切换。
7. **量化比较**：视觉、输入、性能、资源、测试全部达标后逐步放量。
8. **收尾**：删除旧渲染器和 Espresso 专属测试，保留共享 reducer/契约测试。

## 9. 发布与回滚

- 双实现期间使用运行时开关，但不要让开关改变状态模型。
- 记录实现类型、设备、数据规模与关键性能指标，便于定位退化。
- 灰度时同时观察崩溃、ANR、卡顿、无障碍反馈和业务事件重复率。
- 回滚必须只切渲染器，不迁移/丢弃用户状态。
- 删除旧实现前，确认最低支持版本、自动化矩阵和线上观察窗口已满足。

> **无障碍提示**：视觉一致不代表功能一致。迁移后的角色、状态描述、自定义动作、遍历顺序
> 和触控目标必须单独验收。

## 10. 实践检查清单

- [ ] 已量化迁移收益，而不是只写“统一技术栈”。
- [ ] 状态、算法、手势与渲染已拆分，至少有纯逻辑测试。
- [ ] 互操作边界只有不可变输入、用户事件和生命周期契约。
- [ ] 旧/新实现共享同一 state/event 协议，可通过 feature flag 回滚。
- [ ] 视觉、输入、状态、性能、无障碍、资源和测试均有基线。
- [ ] 没有双向镜像状态，也不靠变化 key 强制刷新。
- [ ] 已定义保留 View 的长期理由，或删除旧实现的退出标准。

## 小结

成功迁移的核心不是 Composable 数量，而是风险是否被切小、状态是否单向、结果是否可验证。
先抽状态和算法，再用 `AndroidView` 建立受控边界；只有当收益明确且验收完备时才重写渲染。
对于平台绑定或成熟重型组件，长期保留窄 View 边界同样是正确架构选择。

## 延伸阅读

- [迁移到 Jetpack Compose](https://developer.android.com/develop/ui/compose/migrate)
- [Compose 与 View 互操作 API](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis)
- [Compose 性能最佳实践](https://developer.android.com/develop/ui/compose/performance/bestpractices)
- [Macrobenchmark](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview)
- [Compose 无障碍](https://developer.android.com/develop/ui/compose/accessibility)
