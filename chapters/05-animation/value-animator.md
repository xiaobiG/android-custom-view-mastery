# ValueAnimator 与属性动画

## 学习目标

- 理解属性动画（property animation）只负责按时间产生值，不会自动决定控件如何呈现。
- 在 `ValueAnimator`、`ObjectAnimator` 与 `ViewPropertyAnimator` 之间做出选择。
- 用显式更新函数把动画值写回控件，并正确触发 `invalidate()` 或布局。
- 在控件离开窗口时取消动画，避免监听器与视图被意外持有。

## 1. 动画真正改变了什么

`ValueAnimator` 在时钟推进时计算“当前值”；它不知道这个值代表透明度、角度还是业务进度。自定义控件应把动画值写入唯一状态，再由绘制读取该状态。

```text
start/end + duration
        |
        v
 ValueAnimator ---- 每帧 ----> animatedValue
                                  |
                                  v
                           控件状态 progress
                                  |
                           invalidate/layout
                                  |
                                  v
                               onDraw
```

如果变化只影响像素，调用 `invalidate()`；只有尺寸或子项位置确实改变时才调用 `requestLayout()`。不要在每一帧无条件同时调用两者。

## 2. ValueAnimator：显式、可控的默认选择

下面的圆形进度控件把“立即设置”与“动画到目标值”分开。示例需要 `android.animation.ValueAnimator`、`android.view.animation.DecelerateInterpolator` 和 `androidx.core.animation.doOnEnd`。

```kotlin
class RingProgressView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    var progress: Float = 0f
        private set

    private var progressAnimator: ValueAnimator? = null

    fun setProgress(value: Float, animate: Boolean) {
        val target = value.coerceIn(0f, 1f)
        if (!animate || !isLaidOut) {
            progressAnimator?.cancel()
            progressAnimator = null
            updateProgress(target)
            return
        }

        progressAnimator?.cancel()
        progressAnimator = ValueAnimator.ofFloat(progress, target).apply {
            duration = 280L
            interpolator = DecelerateInterpolator()
            addUpdateListener { updateProgress(it.animatedValue as Float) }
            doOnEnd { progressAnimator = null }
            start()
        }
    }

    private fun updateProgress(value: Float) {
        if (progress == value) return
        progress = value
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawArc(
            paddingLeft.toFloat(),
            paddingTop.toFloat(),
            (width - paddingRight).toFloat(),
            (height - paddingBottom).toFloat(),
            -90f,
            360f * progress,
            false,
            paint,
        )
    }

    override fun onDetachedFromWindow() {
        progressAnimator?.cancel()
        progressAnimator = null
        super.onDetachedFromWindow()
    }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 12f
    }
}
```

`cancel()` 会结束本轮更新并调用取消/结束回调；若代码不希望把取消当成“自然完成”，应分别注册 `doOnCancel` 与 `doOnEnd`，或在回调中记录取消标记。

> **注意**
> `animatedFraction` 是经过插值器后的进度。仅对 `duration > 0`、无重复的简单动画，`currentPlayTime / duration` 才可用来推导线性播放位置；有重复、反向或零时长时必须单独处理迭代语义。业务逻辑不要把二者混用。

## 3. ObjectAnimator：目标确实具有属性时

`ObjectAnimator` 在 `ValueAnimator` 上增加了“把值写给目标属性”的步骤。Kotlin 属性若供反射路径使用，需要生成可见的 Java setter；更稳妥的方式是提供 `Property`，避免字符串拼写和混淆问题。

```kotlin
class GaugeView(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {
    var needleAngle: Float = 0f
        set(value) {
            if (field == value) return
            field = value
            invalidate()
        }

    companion object {
        val NEEDLE_ANGLE: Property<GaugeView, Float> =
            object : Property<GaugeView, Float>(Float::class.java, "needleAngle") {
                override fun get(view: GaugeView): Float = view.needleAngle
                override fun set(view: GaugeView, value: Float) {
                    view.needleAngle = value
                }
            }
    }
}

val animator = ObjectAnimator.ofFloat(gauge, GaugeView.NEEDLE_ANGLE, 30f, 220f).apply {
    duration = 400L
    start()
}
```

对于 `alpha`、`translationX`、`scaleX` 等 View 原生属性，短小的一次性过渡可用：

```kotlin
view.animate()
    .alpha(1f)
    .translationY(0f)
    .setDuration(180L)
    .withEndAction { view.isClickable = true }
    .start()
```

`ViewPropertyAnimator` 会复用与 View 关联的动画器，适合少量原生属性；需要自定义估值、同步多个业务状态或精确监听时，仍优先显式 animator。

## 4. 组合、重复与可访问性

多个阶段可用 `AnimatorSet` 声明先后关系：

```kotlin
val fade = ObjectAnimator.ofFloat(view, View.ALPHA, 0f, 1f)
val rise = ObjectAnimator.ofFloat(view, View.TRANSLATION_Y, 24f, 0f)
AnimatorSet().apply {
    playTogether(fade, rise)
    duration = 220L
    start()
}
```

系统“移除动画”设置会影响 animator 的时长缩放。装饰性动画不应阻止控件达到最终状态；监听缩放或在动画不可运行时直接提交终值。API 26 起可使用 `ValueAnimator.areAnimatorsEnabled()` 判断属性动画是否启用，低版本则让动画系统自然按缩放执行，并保证立即路径可用。

> **无障碍提示**
> 不要用无限闪烁表达唯一信息。状态变化应同时通过文本、content description 或无障碍事件传达。

## 5. 反例：每次赋值都新建动画

```kotlin
// 反例：快速拖动会堆积 animator；每帧 requestLayout 代价也可能过高。
fun setProgress(value: Float) {
    ValueAnimator.ofFloat(progress, value).apply {
        addUpdateListener {
            progress = it.animatedValue as Float
            requestLayout()
            invalidate()
        }
        start()
    }
}
```

问题包括：旧动画继续写回状态、终值竞争、无法在 detach 时统一取消，以及无差别布局。改法是持有单一 animator、启动前取消旧实例、把状态提交集中在一个函数，并按影响范围选择失效方式。

## 6. 实践检查清单

- [ ] 状态有明确范围，外部输入会被校验或钳制。
- [ ] 动画前取消同一属性的旧 animator。
- [ ] 更新只触发必要的 `invalidate()` 或 `requestLayout()`。
- [ ] 动画被取消时不会误执行“成功完成”业务。
- [ ] `onDetachedFromWindow()` 取消 animator 并清除引用。
- [ ] 关闭动画时仍能立即到达终态。
- [ ] ObjectAnimator 使用真实 setter 或类型安全的 `Property`。
- [ ] 动画过程中没有对象分配、日志洪泛或 I/O。

## 小结

`ValueAnimator` 是自定义绘制状态动画的可靠基元；`ObjectAnimator` 适合目标上存在清晰属性的场景；`ViewPropertyAnimator` 则服务于简短的 View 原生属性过渡。生产级实现的关键不是“让它动起来”，而是让状态单一、更新范围准确、取消语义明确且生命周期可控。

## 延伸阅读

- [Android Developers：Property Animation Overview](https://developer.android.com/develop/ui/views/animations/prop-animation)
- [ValueAnimator API](https://developer.android.com/reference/android/animation/ValueAnimator)
- [ObjectAnimator API](https://developer.android.com/reference/android/animation/ObjectAnimator)
- [AnimatorSet API](https://developer.android.com/reference/android/animation/AnimatorSet)
