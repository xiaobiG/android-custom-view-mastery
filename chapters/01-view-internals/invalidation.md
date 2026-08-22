# Invalidate、requestLayout 与帧调度

控件状态发生变化后，最关键的问题不是“怎样立即重画”，而是“哪一类结果已经失效，以及怎样把工作合并到下一帧”。`invalidate()`、`requestLayout()`、`postInvalidateOnAnimation()` 与 Choreographer 分别处于失效标记、跨线程/帧对齐和顶层调度的不同层次。

## 学习目标

读完本章，你应当能够：

- 根据尺寸、位置或像素变化选择 `requestLayout()` 与 `invalidate()`；
- 描述失效请求从 View 向 ViewRootImpl 上报并进入下一帧的概念路径；
- 区分 `invalidate()`、`postInvalidate()` 与 `postInvalidateOnAnimation()`；
- 解释 Choreographer 与 VSync、遍历调度的关系；
- 编写可停止、无泄漏的逐帧更新逻辑；
- 避免把 API 调用误解为同步绘制。

## 一、先判断失效的是什么

| 变化 | 典型调用 | 原因 |
|---|---|---|
| 颜色、选中态、进度角度 | `invalidate()` | 尺寸与位置不变，只需重画 |
| 文本内容导致期望宽高变化 | `requestLayout()` + `invalidate()` | 需重新协商尺寸，也需更新像素 |
| LayoutParams、padding、子数量 | `requestLayout()` | 可能影响祖先和兄弟布局；框架常会引发后续绘制 |
| 持续动画的下一步像素 | `postInvalidateOnAnimation()` | 把失效与下一显示帧对齐 |
| 后台线程请求重画 | `postInvalidate()` 或切主线程 | `invalidate()` 通常要求 UI 线程 |

`requestLayout()` 和 `invalidate()` 不是互斥替代品。前者标记布局请求并沿父链传播；后者标记显示内容失效。一个属性同时影响尺寸和绘制时，两者都调用最清晰。不要依赖某个父容器“顺便”重绘来掩盖契约。

## 二、invalidate 的概念传播路径

在 UI 线程调用 `invalidate()` 不会立即递归执行 `onDraw()`。View 标记自身或区域为脏，并通过父链把失效信息传到根；顶层将遍历安排到合适帧，多个失效请求可以合并。

```text
view.invalidate()
      |
      v
标记 View / 区域需要重绘
      |
      v
沿 ViewParent 链上报失效
      |
      v
ViewRootImpl 请求 / 合并 traversal
      |
      v
Choreographer 在帧信号附近分发回调
      |
      v
performTraversals() -> 需要的 draw 工作
      |
      v
渲染管线提交画面
```

脏矩形（dirty rect）重载可表达局部变化，但在硬件加速、变换、阴影和父容器组合下，最终工作范围由渲染系统决定。它是优化提示，不应作为裁剪正确性的唯一保障。

## 三、requestLayout 的传播与作用

`requestLayout()` 表示当前 View 的测量尺寸或布局位置可能不再有效。请求会沿父链到达根，下一次遍历通常检查并执行 measure/layout，随后绘制受影响内容。

```text
child.requestLayout()
      |
      v
child 标记 layout requested
      |
      v
parent -> ... -> ViewRootImpl
      |
      v
下一次 traversal
      +--> 重新 measure（范围由系统与标记决定）
      +--> 重新 layout
      +--> 必要的 draw
```

调用后立刻读取 `width` 或位置，得到的仍可能是旧值。需要在布局完成后执行逻辑，可使用 `View.doOnLayout`、`OnLayoutChangeListener` 或合适的生命周期回调，而不是 `requestLayout()` 后立即假设同步完成。

> **注意**：不要在 `onMeasure()` 或 `onLayout()` 中无条件调用 `requestLayout()`。这会在当前遍历尚未稳定时再次请求遍历，形成重复工作或循环。

## 四、postInvalidateOnAnimation 与 Choreographer

`postInvalidateOnAnimation()` 自 API 16 可用，它请求在下一动画时间步进行失效，适合由外部状态机驱动、每帧都需要重画的 View。它并不保证每次调用都生成独立一帧，也不保证回调恰好等于屏幕刷新率；系统可能合并请求或因主线程繁忙而错过帧。

Choreographer 是线程级的帧协调器。主线程收到显示节奏相关信号后，按阶段运行输入、动画、遍历等回调。ViewRootImpl 使用它安排遍历；应用通常通过属性动画、`View.postOnAnimation()` 或 `postInvalidateOnAnimation()` 间接参与，而不是自行复制整套帧调度。

```text
Display VSync / 帧时间基准
             |
             v
        Choreographer
             |
     +-------+--------+-----------+
     v                v           v
 输入阶段          动画阶段     Traversal 阶段
                                      |
                                      v
                              measure/layout/draw
                                      |
                                      v
                                  提交渲染
```

这是概念顺序；内部回调类型和实现细节可能随系统版本演进。关键边界是：Choreographer 协调“何时做一帧的主线程工作”，`invalidate()` 表达“内容需要重画”，二者不是同一个 API 层。

## 五、安全的逐帧更新示例

优先使用 `ValueAnimator` 等生命周期可控的高层动画。当确实需要根据帧时间推进自定义模拟时，可以用 `postOnAnimation()` 安排 Runnable，并在窗口分离时移除。下面示例避免固定假设 16 ms，而使用 `System.nanoTime()` 的实际差值。

```kotlin
package com.example.customview.internals

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View

class FrameDrivenView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(30, 120, 230)
    }
    private var running = false
    private var lastFrameNanos = 0L
    private var phase = 0f

    private val frameTask = object : Runnable {
        override fun run() {
            if (!running || !isAttachedToWindow) return
            val now = System.nanoTime()
            if (lastFrameNanos != 0L) {
                val deltaSeconds = ((now - lastFrameNanos) / 1_000_000_000f)
                    .coerceAtMost(0.05f)
                phase = (phase + deltaSeconds * 0.5f) % 1f
            }
            lastFrameNanos = now
            invalidate()
            postOnAnimation(this)
        }
    }

    fun start() {
        if (running) return
        running = true
        lastFrameNanos = 0L
        if (isAttachedToWindow) postOnAnimation(frameTask)
    }

    fun stop() {
        running = false
        removeCallbacks(frameTask)
        lastFrameNanos = 0L
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (running) postOnAnimation(frameTask)
    }

    override fun onDetachedFromWindow() {
        removeCallbacks(frameTask)
        lastFrameNanos = 0L
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val radius = height.coerceAtMost(width) * 0.08f
        val x = radius + (width - 2f * radius).coerceAtLeast(0f) * phase
        canvas.drawCircle(x, height / 2f, radius, paint)
    }
}
```

这里 `postOnAnimation()` 安排状态更新，`invalidate()` 声明像素失效。若状态由别处更新，也可在 setter 中调用 `postInvalidateOnAnimation()`。不要同时启动多个自循环 Runnable；`start()` 必须幂等，`stop()` 与分离窗口必须释放。

> **性能提示**：不可见、停止或离屏时继续请求帧会浪费 CPU/GPU 和电量。结合 `isShown`、生命周期和业务可见状态暂停动画，并用 Perfetto 确认实际帧行为。

## 六、线程边界

经典 View 体系绝大多数状态和 `invalidate()`/`requestLayout()` 操作应在创建 View 层级的 UI 线程进行。后台任务完成后，使用 `view.post { ... }`、主线程 Coroutine dispatcher 或其他生命周期感知方式切回 UI 线程更新状态。

`postInvalidate()` 可从非 UI 线程发布失效，但它不让 View 的其他可变状态突然变成线程安全。更稳妥的模式是后台计算不可变结果，然后在主线程一次性替换并失效。

```kotlin
// 假设调用方已在生命周期范围内启动协程
viewLifecycleOwner.lifecycleScope.launch {
    val points = withContext(kotlinx.coroutines.Dispatchers.Default) {
        calculateImmutablePoints()
    }
    chartView.setPoints(points) // 主线程 setter 内 requestLayout/invalidate
}
```

示例需要 AndroidX Lifecycle 和 Kotlin Coroutines；`calculateImmutablePoints()` 为项目自己的纯计算函数。

## 七、常见陷阱

1. **把 `invalidate()` 当同步绘制**：调用后立即截图或读像素可能仍是旧画面。
2. **尺寸变化只 invalidate**：View 会用旧边界重画，内容可能裁切。
3. **颜色变化却 requestLayout**：无意义地扩大遍历成本。
4. **后台线程直接改 View 字段**：`postInvalidate()` 不能修复数据竞争。
5. **每次更新都新增帧 Runnable**：形成多个循环和泄漏。
6. **固定按 16 ms 推进动画**：在高刷新率、掉帧或后台恢复时速度错误。
7. **分离窗口后仍保留回调**：浪费资源并可能持有 Context。
8. **直接使用 Choreographer 却不移除 FrameCallback**：生命周期管理复杂，优先高层 API。

## 八、实践检查清单

- [ ] 纯像素变化调用 `invalidate()`，尺寸/排布变化调用 `requestLayout()`。
- [ ] 同时影响尺寸和像素的属性明确调用了两者。
- [ ] 我没有把任一请求当作同步执行完成。
- [ ] 连续更新与帧节奏对齐，并使用真实时间差推进状态。
- [ ] `start()` 幂等，不会创建多个逐帧循环。
- [ ] 停止、不可见或 `onDetachedFromWindow()` 时移除回调。
- [ ] 后台线程只做计算，View 状态在 UI 线程提交。
- [ ] 已用 Perfetto/System Trace 验证掉帧而非主观猜测。

## 小结

`invalidate()` 标记绘制内容失效，`requestLayout()` 标记尺寸或位置契约可能失效；请求沿 View 树到达 ViewRootImpl，并被合并进后续遍历。`postInvalidateOnAnimation()` 与 `postOnAnimation()` 让更新靠近下一帧节奏，Choreographer 则在更高层协调输入、动画和遍历。正确分类失效、尊重异步帧边界并成对管理生命周期，是流畅且不泄漏的基础。

## 官方延伸阅读

- [View.invalidate](https://developer.android.com/reference/android/view/View#invalidate())
- [View.requestLayout](https://developer.android.com/reference/android/view/View#requestLayout())
- [View.postInvalidateOnAnimation](https://developer.android.com/reference/android/view/View#postInvalidateOnAnimation())
- [View.postOnAnimation](https://developer.android.com/reference/android/view/View#postOnAnimation(java.lang.Runnable))
- [Choreographer](https://developer.android.com/reference/android/view/Choreographer)
- [Slow rendering and frozen frames](https://developer.android.com/topic/performance/vitals/render)
- [System tracing](https://developer.android.com/topic/performance/tracing)
