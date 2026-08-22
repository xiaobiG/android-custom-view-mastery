# 插值器、估值器与时间系统

## 学习目标

- 区分插值器（Interpolator）与估值器（TypeEvaluator）的职责。
- 为颜色、路径点和领域对象选择正确的估值方式。
- 理解 duration、startDelay、repeat 与帧间隔不是同一概念。
- 编写不依赖固定刷新率、可测试且视觉节奏一致的动画。

## 1. 两次映射

属性动画先把线性时间映射为动画进度，再把进度映射为具体值。

```text
wall clock
    |
    v
linear fraction (0..1)
    |  Interpolator：时间节奏
    v
adjusted fraction
    |  TypeEvaluator：值空间
    v
T(current) ---> 状态更新 ---> 绘制
```

插值器回答“什么时候走到哪里”，估值器回答“起点与终点之间是什么值”。把两者分清后，复杂动画会更容易组合与测试。

## 2. Interpolator：塑造节奏

常见选择：

- `LinearInterpolator`：匀速，适合角速度、确定性进度等。
- `AccelerateDecelerateInterpolator`：默认的缓入缓出，但控制有限。
- `PathInterpolator`：以三次贝塞尔曲线描述产品动效；API 21+。
- AndroidX `FastOutSlowInInterpolator`：Material 风格的进入/位置变化。

```kotlin
val animator = ValueAnimator.ofFloat(0f, 1f).apply {
    duration = 320L
    interpolator = PathInterpolator(0.2f, 0f, 0f, 1f)
    addUpdateListener { animation ->
        revealFraction = animation.animatedValue as Float
        invalidate()
    }
}
```

`PathInterpolator(x1, y1, x2, y2)` 要求 X 方向单调，否则一个时间点会对应多个输出。输出 Y 可以产生超调，但若属性有硬边界，应在提交状态时钳制，而不是假设所有插值器都只返回 0..1。

> **注意**
> 不要把动画的视觉进度用于网络、计费或超时判断。动画时钟可能受系统缩放、暂停和掉帧影响。

## 3. TypeEvaluator：定义值空间

### 3.1 颜色不能按整数直接线性插值

ARGB 颜色是打包整数。直接使用 `IntEvaluator` 会把位模式当普通整数，通道会跳变。应使用 `ArgbEvaluator`：

```kotlin
val colorAnimator = ValueAnimator.ofObject(
    ArgbEvaluator(),
    Color.rgb(244, 67, 54),
    Color.rgb(76, 175, 80),
).apply {
    addUpdateListener {
        paint.color = it.animatedValue as Int
        invalidate()
    }
}
```

如果设计要求感知上更均匀的颜色过渡，可在明确的色彩空间中插值；不要把“ARGB 通道线性”误称为所有意义上的视觉线性。

### 3.2 领域对象使用不可变快照

```kotlin
data class IndicatorPose(
    val centerX: Float,
    val radius: Float,
    val alpha: Float,
)

object IndicatorPoseEvaluator : TypeEvaluator<IndicatorPose> {
    override fun evaluate(
        fraction: Float,
        startValue: IndicatorPose,
        endValue: IndicatorPose,
    ): IndicatorPose = IndicatorPose(
        centerX = lerp(startValue.centerX, endValue.centerX, fraction),
        radius = lerp(startValue.radius, endValue.radius, fraction),
        alpha = lerp(startValue.alpha, endValue.alpha, fraction),
    )

    private fun lerp(start: Float, end: Float, t: Float): Float =
        start + (end - start) * t
}

val poseAnimator = ValueAnimator.ofObject(
    IndicatorPoseEvaluator,
    currentPose,
    targetPose,
)
```

上述写法清晰但每帧创建对象。在对分配敏感的绘制场景，可以改为动画多个 Float 或复用一个仅供动画器内部使用的可变载体；绝不能把会被后续帧修改的对象泄漏给外部持有。

### 3.3 路径与关键帧

二维曲线可用 `Path` 与 `ObjectAnimator.ofFloat(target, xProperty, yProperty, path)`（API 21+），或自行用 `PathMeasure` 采样。非均匀关键帧可用 `PropertyValuesHolder`/`Keyframe`：

```kotlin
val scale = PropertyValuesHolder.ofKeyframe(
    View.SCALE_X,
    Keyframe.ofFloat(0f, 1f),
    Keyframe.ofFloat(0.65f, 1.08f),
    Keyframe.ofFloat(1f, 1f),
)
ObjectAnimator.ofPropertyValuesHolder(view, scale).apply {
    duration = 240L
    start()
}
```

## 4. 时间参数与帧无关性

`duration = 300L` 表示播放时间，不表示“执行 18 次更新”。在 60 Hz、90 Hz、120 Hz 或掉帧设备上，回调次数不同，但同一播放时刻应得到相同状态。

```text
60 Hz : |----|----|----|----|
120 Hz: |--|--|--|--|--|--|--|--|
        0 ms             300 ms
             同一时间 -> 同一进度
```

因此不要写“每帧加 0.05”。手写帧循环时，应使用时间差：

```kotlin
fun integrate(position: Float, velocityPxPerSec: Float, deltaNanos: Long): Float {
    val deltaSeconds = deltaNanos / 1_000_000_000f
    return position + velocityPxPerSec * deltaSeconds
}
```

长时间暂停后 `delta` 可能很大，物理积分应限制步长或分小步追赶，避免对象穿越边界。对于普通补间动画，让 `ValueAnimator` 根据播放时钟计算即可。

## 5. 重复、反向与关键状态

```kotlin
ValueAnimator.ofFloat(0f, 1f).apply {
    duration = 700L
    repeatCount = ValueAnimator.INFINITE
    repeatMode = ValueAnimator.REVERSE
}
```

无限动画必须有可见性和生命周期停止条件。`reverse()` 会从当前播放位置反向；如果交互可频繁改变目标，先确定产品语义是“保持速度连续”“保持位置连续”还是“重新计时”，再选择反向、取消重启或物理动画。

## 6. 反例：把帧数当时间

```kotlin
// 反例：高刷新率设备更快，掉帧时更慢。
fun onFrame() {
    x += 4f
    if (x < targetX) postOnAnimation(::onFrame)
}
```

另一个常见反例是让 evaluator 修改并返回 `startValue`：调用方若仍持有起点，它会在动画期间悄悄变化，下一次动画也失去真实起点。

## 7. 实践检查清单

- [ ] 插值器只负责节奏，估值器只负责值的计算。
- [ ] 颜色使用 `ArgbEvaluator` 或明确的色彩空间插值。
- [ ] 自定义 evaluator 不会意外修改外部共享对象。
- [ ] 动画结果由时间决定，而不是由回调次数决定。
- [ ] 手写积分使用纳秒时间戳并处理过大的时间步。
- [ ] 无限重复动画在不可见、detach 或宿主停止时会结束。
- [ ] 关键帧的中间值与对应 fraction 有设计依据。
- [ ] 测试覆盖 0、0.5、1 以及越界 fraction 的策略。

## 小结

Interpolator 设计时间曲线，TypeEvaluator 设计值空间。以真实时间而不是帧数驱动状态，才能让动画跨刷新率保持一致；以明确的对象所有权和边界策略实现 evaluator，才能避免难以复现的状态污染。

## 延伸阅读

- [Android Developers：Property Animation](https://developer.android.com/develop/ui/views/animations/prop-animation)
- [TimeInterpolator API](https://developer.android.com/reference/android/animation/TimeInterpolator)
- [TypeEvaluator API](https://developer.android.com/reference/android/animation/TypeEvaluator)
- [PathInterpolator API](https://developer.android.com/reference/android/view/animation/PathInterpolator)
- [Keyframe API](https://developer.android.com/reference/android/animation/Keyframe)
