# 帧同步与动画生命周期

## 学习目标

- 理解 `Choreographer` 如何把输入、动画与绘制工作对齐到显示帧。
- 正确使用 `frameTimeNanos`，避免用回调到达时刻代替帧时刻。
- 根据 View 的 attach、可见性和宿主生命周期暂停或取消工作。
- 避免重复注册帧回调、后台空转和回调持有导致的泄漏。

## 1. 一帧从哪里开始

`Choreographer` 接收显示系统的垂直同步（VSYNC）信号，并在主线程安排输入、动画和遍历等阶段。`invalidate()` 只是标记需要重绘，真正遍历会在后续帧统一发生。

```text
VSYNC
  |
  +--> input callbacks
  +--> animation callbacks / FrameCallback
  +--> View traversal (measure? layout? draw?)
  +--> render submission
  |
next VSYNC
```

一帧预算取决于刷新率：60 Hz 约 16.7 ms，120 Hz 约 8.3 ms。不要把预算写死进算法；应让工作量小而稳定，并用 Perfetto/帧指标验证。

## 2. 什么时候直接使用 Choreographer

普通属性过渡应优先 `ValueAnimator`，它已经处理时钟、缩放和帧同步。只有以下场景通常需要直接帧回调：

- 自定义模拟器或可视化引擎需要每帧积分。
- 需要把外部采样与 Android 帧时间对齐。
- 控件持续运行但不适合固定起止值。

一个可启停的实现如下：

```kotlin
class WaveView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs), Choreographer.FrameCallback {

    private var running = false
    private var callbackPosted = false
    private var lastFrameNanos = 0L
    private var phase = 0f

    fun start() {
        if (running) return
        running = true
        lastFrameNanos = 0L
        postNextFrameIfNeeded()
    }

    fun stop() {
        running = false
        callbackPosted = false
        Choreographer.getInstance().removeFrameCallback(this)
        lastFrameNanos = 0L
    }

    override fun doFrame(frameTimeNanos: Long) {
        callbackPosted = false
        if (!shouldRun()) return

        if (lastFrameNanos != 0L) {
            val rawDelta = (frameTimeNanos - lastFrameNanos) / 1_000_000_000f
            val deltaSeconds = rawDelta.coerceAtMost(0.05f)
            phase = (phase + deltaSeconds * 0.8f) % 1f
            invalidate()
        }
        lastFrameNanos = frameTimeNanos
        postNextFrameIfNeeded()
    }

    private fun shouldRun(): Boolean =
        running && isAttachedToWindow && isShown && windowVisibility == VISIBLE

    private fun postNextFrameIfNeeded() {
        if (!callbackPosted && shouldRun()) {
            callbackPosted = true
            Choreographer.getInstance().postFrameCallback(this)
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        postNextFrameIfNeeded()
    }

    override fun onDetachedFromWindow() {
        stop()
        super.onDetachedFromWindow()
    }

    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        if (visibility == VISIBLE) {
            lastFrameNanos = 0L
            postNextFrameIfNeeded()
        } else {
            Choreographer.getInstance().removeFrameCallback(this)
            callbackPosted = false
            lastFrameNanos = 0L
        }
    }

    override fun onVisibilityChanged(changedView: View, visibility: Int) {
        super.onVisibilityChanged(changedView, visibility)
        // 窗口仍可见时，自身或祖先也可能切换 INVISIBLE/GONE。
        if (isShown && windowVisibility == VISIBLE) {
            lastFrameNanos = 0L
            postNextFrameIfNeeded()
        } else {
            Choreographer.getInstance().removeFrameCallback(this)
            callbackPosted = false
            lastFrameNanos = 0L
        }
    }
}
```

`callbackPosted` 防止同一个对象重复入队。窗口可见性与 View/祖先可见性是两条不同路径，二者都要在隐藏时撤销回调、恢复时重新入队。恢复时清零上一帧时间，避免把几秒后台时间一次性积分进去。

> **注意**
> `Choreographer.getInstance()` 必须在线程具有 Looper 时调用；View 动画通常应在主线程操作。

## 3. frameTimeNanos 的语义

回调可能因为主线程繁忙而延迟。`System.nanoTime()` 表示“代码现在运行的时刻”，`frameTimeNanos` 表示该帧的统一时间基准。多个同帧回调使用后者可保持一致。

```text
VSYNC time -------- delayed main thread -------- callback runs
    ^                                              ^
frameTimeNanos                              System.nanoTime()
```

物理模拟可限制最大 delta；更高精度时使用固定小步长累计器：

```kotlin
accumulator += deltaSeconds.coerceAtMost(0.1f)
while (accumulator >= STEP_SECONDS) {
    simulation.step(STEP_SECONDS)
    accumulator -= STEP_SECONDS
}
```

要限制单帧循环次数，避免恢复后“追帧”反而阻塞主线程。

## 4. View 生命周期不等于页面生命周期

attach 说明 View 位于某个窗口，不代表页面处于前台或完全可见。持续动画可同时考虑：

```text
requested by feature?
        && attached?
        && window visible?
        && lifecycle STARTED?
        => schedule next frame
```

自定义 View 不应强制把传入 `Context` 转成 Activity。若业务需要宿主生命周期，由外部显式绑定：

```kotlin
fun bindTo(lifecycleOwner: LifecycleOwner) {
    lifecycleOwner.lifecycle.addObserver(object : DefaultLifecycleObserver {
        override fun onStart(owner: LifecycleOwner) = start()
        override fun onStop(owner: LifecycleOwner) = stop()
        override fun onDestroy(owner: LifecycleOwner) {
            owner.lifecycle.removeObserver(this)
        }
    })
}
```

更完整的组件应保存 observer 引用，以便重新绑定时先移除旧 observer。也可以让 Fragment 在 `onStart/onStop` 直接调用 View 的 `start/stop`，所有权最清晰。

## 5. 监听器与 animator 的统一释放

```kotlin
private var animator: Animator? = null
private var preDrawListener: ViewTreeObserver.OnPreDrawListener? = null

override fun onDetachedFromWindow() {
    animator?.removeAllListeners()
    animator?.cancel()
    animator = null

    preDrawListener?.let { listener ->
        if (viewTreeObserver.isAlive) {
            viewTreeObserver.removeOnPreDrawListener(listener)
        }
    }
    preDrawListener = null
    stop()
    super.onDetachedFromWindow()
}
```

取消 animator 前还是后移除 listener 取决于是否需要取消通知。上例明确选择“不让释放流程触发业务结束回调”。应用应为自然完成、用户取消、生命周期清理分别定义语义。

## 6. 反例：递归 postOnAnimation 永不停止

```kotlin
// 反例：detach 后仍可能保留逻辑意图，且每次 start 都会形成一条新链。
private val tick = object : Runnable {
    override fun run() {
        phase += 0.01f
        invalidate()
        postOnAnimation(this)
    }
}
fun start() = postOnAnimation(tick)
```

另一个反例是在 `doFrame` 内做磁盘读取、图片解码或复杂对象创建。帧回调应只做有界计算和状态提交，重任务提前准备或移出主线程。

## 7. 验证与诊断

- 在开发构建中统计帧 delta 分布，不要逐帧打印日志。
- 用 Perfetto 查看主线程、Choreographer 与渲染时间线。
- 用 `FrameMetricsAggregator`（AndroidX Core）或 Macrobenchmark 观察慢帧。
- 测试 start 两次只有一条回调链；stop/detach 后状态不再变化。
- 模拟窗口隐藏再恢复，确认第一帧不会发生大跳跃。

> **性能提示**
> 缩短 `doFrame` 并不保证 GPU 工作及时完成。复杂自定义绘制还需同时观察 RenderThread、GPU 和过度绘制。

## 8. 实践检查清单

- [ ] 普通补间优先 animator，只有确有需要才直接用 Choreographer。
- [ ] 使用 `frameTimeNanos` 作为同帧统一时钟。
- [ ] 时间步有上限或固定步长追赶上限。
- [ ] 重复 start 不会重复注册回调。
- [ ] stop、不可见与 detach 都会移除回调。
- [ ] 恢复时重置上一帧时间。
- [ ] 生命周期清理不会误触发业务成功回调。
- [ ] 帧回调中没有 I/O、解码、日志洪泛或无界循环。

## 小结

Choreographer 是帧同步入口，不是更底层就必然更快的动画工具。直接使用它时，应建立严格的单回调链、统一时钟、时间步保护和生命周期门控；对普通属性动画则应让 ValueAnimator 完成这些基础工作。

## 延伸阅读

- [Choreographer API](https://developer.android.com/reference/android/view/Choreographer)
- [Android Developers：Slow rendering](https://developer.android.com/topic/performance/vitals/render)
- [Perfetto：Frame timeline](https://perfetto.dev/docs/data-sources/frametimeline)
- [View 生命周期 API](https://developer.android.com/reference/android/view/View#onAttachedToWindow())
- [DefaultLifecycleObserver API](https://developer.android.com/reference/androidx/lifecycle/DefaultLifecycleObserver)
