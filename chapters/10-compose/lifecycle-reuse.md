# 生命周期、复用与资源释放

一个 View 出现在组合中，不等于它只经历“创建—销毁”两个阶段。在 `LazyColumn` 中，它可能
离开当前组合、进入复用池、被重置后绑定到另一项，最后才真正释放。与此同时，View 还可能
持有 `LifecycleOwner`、`SavedStateRegistryOwner`、动画、线程、传感器或解码器。必须把
**暂时停用、复用重绑、永久释放**区分开。

## 学习目标

- 理解 `AndroidView` 的 `onReset`、`update` 与 `onRelease` 协议。
- 在 Lazy 容器中安全复用昂贵 View，避免旧数据、监听器与焦点泄漏。
- 正确获取 `LifecycleOwner`、`SavedStateRegistryOwner` 与 ViewTree owners。
- 为动画、协程、线程、回调和原生资源设计可验证的释放路径。

## 1. AndroidView 的三阶段协议

带非空 `onReset` 的 `AndroidView` 可以在兼容的结构中复用底层 View；没有 `onReset` 时，
离开组合的 View 默认不会被复用。

```text
                    首次进入
                       │
                       ▼
 factory ──────────> update(item A) ─────> 屏幕显示
                         │
                  Lazy 项离开/准备复用
                         ▼
                  onReset(view)
                  清临时、项相关状态
                         │
               ┌─────────┴─────────┐
               │可复用于 item B    │不再需要
               ▼                   ▼
          update(item B)       onRelease(view)
          重新完整绑定           最终释放
               │
               └────未来仍可再次 onReset/update
```

- `onReset`：View 将离开当前内容，且可能被复用；清理与旧列表项相关的瞬时状态。
- `update`：必须完整绑定当前项，不能假定 View 仍保留正确数据。
- `onRelease`：该实例永久离开 Compose；执行最终且幂等的资源释放，之后不会再调用
  `onReset` 或 `update`。

> **版本边界**：带 `onReset`/`onRelease` 的复用重载从 Compose UI **1.4.0-rc01** 引入。
> 项目应通过 Compose BOM/version catalog 锁定同一组 `androidx.compose.ui` 版本；若仍低于该
> 版本，只能使用 `factory`/`update` 重载且没有本节的复用/最终释放回调，不能复制示例后用
> 反射探测回调。

## 2. Lazy 列表中的复用范式

下面的适配器展示了昂贵图表 View 在 `LazyColumn` 中的复用。`onReset` 只清“上一项”的
状态，`onRelease` 才关闭线程和渲染资源。

```kotlin
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun ChartFeed(
    cards: List<ChartCard>,
    onPointClick: (cardId: String, pointId: String) -> Unit
) {
    LazyColumn {
        items(
            items = cards,
            key = { it.id },
            contentType = { "legacy-chart" }
        ) { card ->
            ReusableChart(
                card = card,
                onPointClick = onPointClick,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(220.dp)
            )
        }
    }
}

@Composable
private fun ReusableChart(
    card: ChartCard,
    onPointClick: (String, String) -> Unit,
    modifier: Modifier = Modifier
) {
    val latestClick = rememberUpdatedState(onPointClick)

    AndroidView(
        modifier = modifier,
        factory = { context ->
            StreamingChartView(context).apply {
                pointClickListener = { cardId, pointId ->
                    latestClick.value(cardId, pointId)
                }
            }
        },
        update = { view ->
            // 完整绑定：复用后的 View 可能来自任意旧 card。
            view.bind(
                cardId = card.id,
                title = card.title,
                points = card.points,
                highlightedPointId = card.highlightedPointId
            )
        },
        onReset = { view ->
            view.stopGesture()
            view.clearFocus()
            view.highlightedPointId = null
            view.cancelPendingTooltip()
            // 不关闭可供下一项继续使用的渲染线程或共享缓存。
        },
        onRelease = { view ->
            view.pointClickListener = null
            view.release() // 幂等：停线程、注销回调、释放纹理/解码器。
        }
    )
}
```

`key` 表示业务身份，`contentType` 帮助 Lazy 容器判断结构兼容性；二者不能替代 `update`
完整绑定。切勿在 `onReset` 中保留旧 `cardId`、选中状态、辅助功能描述或延迟任务。

## 3. onReset 与 onRelease 的责任表

| 资源/状态 | `onReset` | `onRelease` | 原因 |
|---|---:|---:|---|
| 按下、拖拽、临时高亮 | 清除 | 清除 | 不能串到下一列表项 |
| 当前项 ID/文本/内容描述 | 清除或由下次 update 覆盖 | 清除 | 防止旧数据短暂闪现 |
| 项相关延迟任务 | 取消 | 取消 | 回调可能命中错误 item |
| 焦点、输入法编辑态 | 通常清除 | 清除 | 焦点不应随池中实例迁移 |
| 可复用 Bitmap/Path 缓存 | 可保留 | 释放 | 复用收益来自保留昂贵对象 |
| 专属线程/解码器/相机 | 视暂停协议而定 | 必须关闭 | 最终退出不得泄漏 |
| 监听器 | 通常保留并读最新回调 | 置空/注销 | 避免重装，同时断开引用链 |

> **性能提示**：若 `onReset` 直接调用等价于“销毁”的 `release()`，复用只保留了空壳，
> 下一次 `update` 仍会支付全部初始化成本。先用性能分析确认真正昂贵的资源，再决定保留范围。

## 4. LifecycleOwner：观察正确的生命边界

Compose 会把 View tree owners 传播到互操作 View。自定义 View 应优先在已附着后通过
`ViewTreeLifecycleOwner.get(this)` 获取 owner，不要把 `Activity` 强转成 owner，更不要把
它存入进程级单例。

```kotlin
import android.content.Context
import android.util.AttributeSet
import android.view.View
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ViewTreeLifecycleOwner

class CameraPreviewView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs), DefaultLifecycleObserver {

    private var owner: LifecycleOwner? = null

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        val newOwner = checkNotNull(ViewTreeLifecycleOwner.get(this)) {
            "CameraPreviewView requires a ViewTreeLifecycleOwner"
        }
        if (owner !== newOwner) {
            owner?.lifecycle?.removeObserver(this)
            owner = newOwner
            newOwner.lifecycle.addObserver(this)
        }
    }

    override fun onStart(owner: LifecycleOwner) {
        startPreviewIfReady()
    }

    override fun onStop(owner: LifecycleOwner) {
        stopPreview()
    }

    override fun onDetachedFromWindow() {
        stopPreview()
        owner?.lifecycle?.removeObserver(this)
        owner = null
        super.onDetachedFromWindow()
    }

    fun release() {
        stopPreview()
        owner?.lifecycle?.removeObserver(this)
        owner = null
        releaseCameraResources()
    }
}
```

`onDetachedFromWindow()` 可能只是暂时脱离或进入复用阶段，适合暂停界面相关工作；最终不可逆
资源仍应由 `onRelease` 调用 `release()`。`release()` 必须允许重复调用，以抵御宿主异常路径。

如果资源本来属于组合而不是 View，使用 Compose effect 更清晰：

```kotlin
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@Composable
fun RememberedSession(content: @Composable (PreviewSession) -> Unit) {
    val owner = LocalLifecycleOwner.current
    val session = remember { PreviewSession() }

    DisposableEffect(owner, session) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> session.start()
                Lifecycle.Event.ON_STOP -> session.stop()
                else -> Unit
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose {
            owner.lifecycle.removeObserver(observer)
            session.close()
        }
    }
    content(session)
}
```

不要在 `update` 中添加 lifecycle observer；否则每次状态变化都可能重复注册。

## 5. SavedState：保存模型，不保存 View 实例

互操作 View 可通过 `ViewTreeSavedStateRegistryOwner.get(view)` 找到宿主 registry，但应用层更
推荐把可恢复的最小业务状态提升到 Compose，并用 `rememberSaveable`/`ViewModel` 持有。
View 实例、`Context`、Bitmap、线程、Canvas 都不应进入 saved state。

```kotlin
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun RestorableZoomChart(points: List<ChartPoint>) {
    var zoom by rememberSaveable { mutableFloatStateOf(1f) }

    AndroidView(
        factory = { context ->
            ZoomChartView(context).apply {
                onZoomChanged = { newZoom, fromUser ->
                    if (fromUser) zoom = newZoom
                }
            }
        },
        update = { view ->
            view.submitPoints(points)
            if (view.zoom != zoom) view.zoom = zoom
        },
        onRelease = { view -> view.release() }
    )
}
```

若同一屏有多个实例，必须为保存状态提供稳定且唯一的业务 key；Lazy 列表也应使用稳定 item
key。只保存恢复后能重新构建 UI 的值，例如缩放级别、选中 ID、滚动位置，而不是资源对象。

## 6. 资源释放的双保险

推荐同时建立两道防线：

1. 自定义 View 在 `onDetachedFromWindow()` 暂停动画、移除仅附着期间的回调。
2. `AndroidView.onRelease` 调用显式、幂等的 `release()` 做最终关闭。

重点检查：

- `Choreographer`、`postDelayed`、`ViewTreeObserver`、广播与传感器监听器；
- `Animator`、手势惯性任务、`CoroutineScope`；
- `Surface`、相机、播放器、WebView、纹理、解码器；
- 持有 Activity/View 的静态引用或长寿命回调；
- 线程退出后是否还能回调已复用到其他 item 的 View。

> **注意**：不同重量级组件有各自的生命周期协议。例如播放器常把播放会话提升到
> `ViewModel`，而 View 只附着渲染表面；不要机械地在每次离屏时销毁整个会话。

## 7. 常见陷阱

| 陷阱 | 后果 | 正确做法 |
|---|---|---|
| `onReset = {}` 空实现 | 旧高亮、焦点、任务串项 | 明确清理所有 item 相关状态 |
| `update` 只更新变化字段 | 复用后残留前一项字段 | 每次完整绑定当前 item |
| `onReset` 关闭所有昂贵资源 | 复用无性能收益 | 暂停/清临时状态，最终释放留给 `onRelease` |
| 在 `update` 注册 observer | 重复回调和泄漏 | `factory`/附着回调注册，释放时注销 |
| 保存 View 或 Context | 配置变化后泄漏、不可序列化 | 只保存最小模型状态 |
| 只依赖 `onDetachedFromWindow` | 永久资源可能未彻底释放 | 增加显式幂等 `release()` |
| Lazy item 使用位置作 key | 重排后状态错位 | 使用稳定业务 ID |

## 8. 实践检查清单

- [ ] 明确区分 `onReset`（可复用）与 `onRelease`（永久结束）。
- [ ] `update` 能把任意旧实例完整绑定成当前 item。
- [ ] 列表有稳定 `key`，相同结构有合理 `contentType`。
- [ ] View tree owner 在附着后获取，observer 在脱离/释放时注销。
- [ ] saved state 只保存可序列化、可重建 UI 的最小状态。
- [ ] `release()` 幂等，覆盖动画、线程、监听器和原生资源。
- [ ] 通过滚动往返、配置变化和离开页面验证无串项、无泄漏。

## 小结

复用不是少调用几次构造函数，而是一份严格协议：`onReset` 擦除上一任使用者的痕迹，
`update` 完整绑定下一任，`onRelease` 终结实例。生命周期与保存状态也应以 owner 和模型为
边界，而不是依赖 Activity 强转或保存 View 本身。做到这些，Lazy 复用才既快又正确。

## 延伸阅读

- [Compose 中的 View 互操作](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose)
- [Compose 副作用 API](https://developer.android.com/develop/ui/compose/side-effects)
- [保存 UI 状态](https://developer.android.com/develop/ui/compose/state-saving)
- [ViewTreeLifecycleOwner](https://developer.android.com/reference/androidx/lifecycle/ViewTreeLifecycleOwner)
