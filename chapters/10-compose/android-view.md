# AndroidView 与状态同步

`AndroidView` 不是把 `View` “变成 Compose”，而是在 Compose 布局树中维护一个真实的
Android `View`。互操作的难点也不在创建，而在于明确**谁拥有状态、谁发出事件、什么时候把
状态写回 View**。如果边界没有设计好，一次普通重组就可能重复安装监听器、重启动画，甚至
形成 View → Compose → View 的反馈回路。

## 学习目标

- 理解 `factory` 与 `update` 的调用时机和职责边界。
- 用单向数据流连接 Compose 状态与传统 View。
- 正确使用 `rememberUpdatedState` 让长寿命监听器调用最新回调。
- 识别由重组、可变对象和双向同步引起的常见陷阱。

## 1. factory 只创建，update 负责幂等同步

`AndroidView` 最重要的契约可以概括为：

- `factory(Context)`：为当前互操作节点创建 View，通常只执行一次；适合构造、固定属性、
  只需安装一次的监听器。
- `update(View)`：首次创建后会执行，并在其读取的 Compose `State` 发生变化时再次执行；
  必须可重复调用（idempotent）。
- `Modifier`：由 Compose 管理节点的测量、位置、绘制层和语义；不要把 Compose 尺寸反写成
  固定像素的 `LayoutParams`。

```text
外部状态 State<T>
       │ 读取
       ▼
Compose 重组 ──────首次──────> factory(Context) ──> View
       │                                      │
       └────────每次需要同步────────> update(View) │
                                              │ 用户输入
                                              ▼
                                   onValueChange(newValue)
                                              │
                                              └──> 状态持有者
```

下面是一个完整的受控（controlled）适配器。假设已有自定义 `RatingView`，它公开
`rating`、`isIndicator` 与 `setOnRatingChangeListener`：

```kotlin
import android.view.View
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun RatingEditor(modifier: Modifier = Modifier) {
    var rating by remember { mutableFloatStateOf(3.5f) }

    LegacyRating(
        rating = rating,
        onRatingChange = { rating = it },
        modifier = modifier.fillMaxWidth()
    )
}

@Composable
fun LegacyRating(
    rating: Float,
    onRatingChange: (Float) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    // 监听器的身份稳定，但每次都能读到最新 lambda。
    val currentOnRatingChange by rememberUpdatedState(onRatingChange)

    AndroidView(
        modifier = modifier,
        factory = { context ->
            RatingView(context).apply {
                isIndicator = !enabled
                setOnRatingChangeListener { newRating, fromUser ->
                    if (fromUser) currentOnRatingChange(newRating)
                }
            }
        },
        update = { view ->
            view.isIndicator = !enabled
            // 幂等写入，并避免 setter 触发无意义回调或重绘。
            if (view.rating != rating) {
                view.rating = rating
            }
        }
    )
}
```

> **注意**：示例中的 `RatingView` 是项目自定义类型，监听器签名应以真实控件 API 为准。
> `AndroidView` 本身不会自动推断业务状态，也不会替你避免 setter 的副作用。

## 2. 状态所有权：只保留一个事实来源

推荐由 Compose/`ViewModel` 持有业务状态，View 只显示当前值并把用户事件向上报告：

```text
ViewModel/rememberSaveable
          │ UiState
          ▼
       Compose
          │ update: model -> View
          ▼
      Android View
          │ listener: user event
          └──────────────> event -> reducer/ViewModel
```

最危险的写法是在 `update` 中同时“从 View 读状态写回 Compose”：

```kotlin
// 反例：update 读取 state，又修改 state，容易形成反馈回路。
AndroidView(
    factory = { context -> RatingView(context) },
    update = { view ->
        view.rating = rating
        rating = view.rating
    }
)
```

如果 View 内部会规范化数值（例如把 `3.7` 吸附到 `3.5`），把规范化规则放到状态层；若暂时
无法移动，只在**用户事件**中上报规范化后的值，不要在每次 `update` 时回读。

## 3. rememberUpdatedState 解决“旧闭包”

监听器、观察者和回调往往在 `factory` 中安装一次，寿命比一次重组长。它们若直接捕获参数，
可能持续调用首次组合时的旧 lambda：

```kotlin
// 反例：factory 一般不会因 onOpenDetails 改变而重建 View。
factory = { context ->
    ChartView(context).apply {
        onPointClick = { point -> onOpenDetails(point.id) }
    }
}
```

`rememberUpdatedState` 创建一个身份稳定、值随重组更新的 State：

```kotlin
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun LegacyChart(
    points: List<ChartPoint>,
    onOpenDetails: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val latestOpenDetails = rememberUpdatedState(onOpenDetails)

    AndroidView(
        modifier = modifier,
        factory = { context ->
            ChartView(context).apply {
                onPointClick = { point ->
                    latestOpenDetails.value(point.id)
                }
            }
        },
        update = { chart ->
            // submitPoints 应自行比较版本或使用不可变快照，避免每次全量重建。
            chart.submitPoints(points)
        }
    )
}
```

它适用于“对象不应重建，但行为需要更新”的场景。若依赖变化后本来就应该重新注册资源，
应使用 `DisposableEffect(key)`，而不是用 `rememberUpdatedState` 隐藏依赖变化。

## 4. update 的重组读取范围

只有 `update` 执行时读取到的 Compose 状态才会使该更新块失效。把昂贵计算提前到 Compose
侧，并用稳定结果驱动 View：

```kotlin
val renderedPoints = remember(rawPoints, viewport) {
    decimate(rawPoints, viewport) // 仅在 key 变化时计算
}
AndroidView(
    factory = { ChartView(it) },
    update = { it.submitPoints(renderedPoints) }
)
```

注意：`remember(list)` 按 key 的相等性判断。原地修改 `MutableList` 而不更换对象，Compose
可能看不到变化。边界参数优先使用不可变集合或显式版本号。

## 5. 测量与布局边界

Compose 把约束传给承载 View 的节点，再以 View 的测量结果参与布局。互操作时应遵循：

1. 尺寸意图写在 `Modifier`（例如 `fillMaxWidth()`、`heightIn()`）。
2. View 自身正确实现 `onMeasure()`，尤其处理 `AT_MOST` 与 `UNSPECIFIED`。
3. 不在 `update` 中反复替换 `layoutParams`；这会引起额外 `requestLayout()`。
4. 需要密度转换时使用 Compose `LocalDensity` 在组合侧计算，或在 View 中使用
   `resources.displayMetrics`，不要把 dp 数字直接当 px。

> **性能提示**：`update` 可能比预想更频繁。setter 内部若会分配大对象、解析文本或重建
> Path，应在 View 内做相等性短路，或把结果在 Compose 侧 `remember` 后再提交。

## 6. 常见重组陷阱

| 陷阱 | 表现 | 原因 | 修复 |
|---|---|---|---|
| 在 `update` 安装监听器 | 回调次数逐渐增加 | 每次更新都新增监听器 | 在 `factory` 安装一次，配合 `rememberUpdatedState` |
| 在 `update` 调 `start()` | 动画不断重启 | 更新块可重复执行 | 以事件驱动，或在 View 中检查运行状态 |
| 直接捕获旧 lambda | 点击后执行旧导航/旧参数 | `factory` 未重建 | `rememberUpdatedState` |
| 原地修改集合 | View 没收到新数据 | Compose 未观察到引用变化 | 使用不可变快照或版本号 |
| setter 无条件触发 listener | 状态来回写、重复重组 | 程序写入与用户输入未区分 | 相等性短路，并提供 `fromUser` 标记 |
| 在 `factory` 读取会变化的值 | 后续主题/开关不更新 | `factory` 不是更新通道 | 可变属性放入 `update` |
| 用 `key()` 强制重建 | 滚动、焦点和缓存丢失 | 把同步问题变成销毁重建 | 保持实例，做幂等增量更新 |

## 7. 实践检查清单

- [ ] `factory` 只做创建、固定配置和一次性监听器安装。
- [ ] `update` 可安全重复执行，昂贵 setter 有相等性短路。
- [ ] 业务状态只有一个事实来源，View 事件只向上报告。
- [ ] 长寿命回调通过 `rememberUpdatedState` 获取最新行为。
- [ ] 列表、路径、Bitmap 等输入有明确的不可变快照或版本策略。
- [ ] 尺寸由 `Modifier` 和 View 的 `onMeasure()` 协商，而非硬编码像素。
- [ ] 没有通过频繁改变 `key` 来掩盖状态同步错误。

## 小结

`AndroidView` 的可靠用法不是“每次重组配置一遍 View”，而是建立清晰的单向边界：
`factory` 创建稳定实例，`update` 幂等地把模型投影到 View，监听器把用户事件送回状态层。
`rememberUpdatedState` 则让一次安装的监听器始终执行最新行为。下一章将进一步处理实例复用、
生命周期所有者与资源释放。

## 延伸阅读

- [AndroidView 官方 API](https://developer.android.com/reference/kotlin/androidx/compose/ui/viewinterop/package-summary#AndroidView(kotlin.Function1,androidx.compose.ui.Modifier,kotlin.Function1))
- [Compose 中的 View 互操作](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose)
- [Compose 状态与 Jetpack Compose](https://developer.android.com/develop/ui/compose/state)
