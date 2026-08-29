# 弹簧、衰减与手势衔接

## 学习目标

- 理解物理动画与固定时长补间动画的差异。
- 使用 AndroidX DynamicAnimation 的 `SpringAnimation` 与 `FlingAnimation`。
- 把触摸速度、边界与弹簧目标连接成连续运动。
- 正确处理取消、重新定向以及不可见时停止。

## 1. 为什么选择物理动画

补间动画预先规定“多长时间从 A 到 B”；物理动画从位置、速度和受力推导下一状态。拖拽释放、可中途改目标的指示器、边缘回弹更适合后者。

```text
pointer drag                     release
    |                               |
    v                               v
position follows finger ----> initial velocity
                                      |
                              FlingAnimation
                                      |
                           hit bound / slow down
                                      |
                              SpringAnimation
                                      |
                                  stable target
```

AndroidX DynamicAnimation 以每秒像素等单位表达速度，并跟随帧调度更新属性。依赖项通常为 `androidx.dynamicanimation:dynamicanimation`，版本应由工程的 version catalog 或依赖管理统一决定。

## 2. SpringAnimation：目标可随时变化

弹簧由最终位置、刚度（stiffness）和阻尼比（damping ratio）描述。刚度越大，收敛越快；阻尼比小于 1 会振荡，等于 1 为临界阻尼，大于 1 不振荡但响应更慢。

```kotlin
private val thumbX = object : FloatPropertyCompat<SliderView>("thumbX") {
    override fun getValue(view: SliderView): Float = view.thumbCenterX
    override fun setValue(view: SliderView, value: Float) {
        view.thumbCenterX = value.coerceIn(view.minThumbX, view.maxThumbX)
        view.invalidate()
    }
}

private val spring = SpringAnimation(this, thumbX).apply {
    spring = SpringForce().apply {
        stiffness = SpringForce.STIFFNESS_MEDIUM
        dampingRatio = SpringForce.DAMPING_RATIO_NO_BOUNCY
    }
    addEndListener { _, canceled, value, _ ->
        if (!canceled) commitSelection(nearestIndex(value))
    }
}

fun animateThumbTo(targetX: Float, initialVelocity: Float = 0f) {
    spring.setStartVelocity(initialVelocity)
    spring.animateToFinalPosition(targetX.coerceIn(minThumbX, maxThumbX))
}
```

重复调用 `animateToFinalPosition()` 可以在运行中改变目标；库会从当前值与速度继续，不必取消后从静止重启。若直接替换 `spring` 配置，要保证 `finalPosition` 已设置且阻尼比有效。

> **性能提示**
> `FloatPropertyCompat` 的 setter 每帧执行。只更新状态并失效必要区域，不要在其中分配对象、解析资源或触发布局树重测。

## 3. FlingAnimation：从手势速度自然减速

`FlingAnimation` 根据起始速度和摩擦系数衰减，并通过 min/max value 限制范围。

```kotlin
private val fling = FlingAnimation(this, thumbX).apply {
    friction = 1.6f
    setMinValue(minThumbX)
    setMaxValue(maxThumbX)
    addEndListener { _, canceled, value, velocity ->
        if (!canceled) {
            val target = snapXFor(nearestIndex(value))
            animateThumbTo(target, velocity)
        }
    }
}

fun releaseThumb(velocityX: Float) {
    spring.cancel()
    fling.cancel()
    fling.setStartValue(thumbCenterX)
    fling.setStartVelocity(velocityX)
    fling.start()
}
```

边界依赖布局尺寸，因此尺寸变化后要更新 `setMinValue`/`setMaxValue`。启动值应位于边界内；
若越界，`FlingAnimation` 会把值约束在 min/max 范围内：到达边界即停止并回调
`onAnimationEnd`，不要依赖"抛异常"来兜底。速度来自 `VelocityTracker` 时，通常调用
`computeCurrentVelocity(1000, maxVelocity)`，得到 px/s。

> **注意**：示例中的 `minThumbX`/`maxThumbX` 是滑块边界（由布局宽度与 thumb 尺寸推导），
> `maximumFlingVelocity` 来自 `ViewConfiguration.getScaledMaximumFlingVelocity()`；它们是
> 控件自身的成员/常量，正文为突出动画逻辑而省略了定义。

`FlingAnimation` 还有 `setMinimumVisibleChange(value)`：当速度使每帧位移低于该值（像素或
度数）时，动画视为“视觉上已停止”并提前结束。默认值与属性类型相关（像素属性约 0.5 px），
值设得过大时动画会明显“提前停”——这常被误判为 bug。需要完整跑完减速过程时，应改用更小
的阈值，而不是靠调整摩擦值硬凑。

## 4. 完整的拖拽—释放衔接

```kotlin
private var velocityTracker: VelocityTracker? = null
private var activePointerId = MotionEvent.INVALID_POINTER_ID

@SuppressLint("ClickableViewAccessibility")
override fun onTouchEvent(event: MotionEvent): Boolean {
    if (event.actionMasked == MotionEvent.ACTION_DOWN) {
        velocityTracker?.recycle()
        velocityTracker = VelocityTracker.obtain()
    }
    velocityTracker?.addMovement(event)

    when (event.actionMasked) {
        MotionEvent.ACTION_DOWN -> {
            parent.requestDisallowInterceptTouchEvent(true)
            activePointerId = event.getPointerId(0)
            fling.cancel()
            spring.cancel()
            return true
        }
        MotionEvent.ACTION_MOVE -> {
            val index = event.findPointerIndex(activePointerId)
            if (index >= 0) {
                thumbCenterX = event.getX(index).coerceIn(minThumbX, maxThumbX)
                invalidate()
            }
        }
        MotionEvent.ACTION_UP -> {
            velocityTracker?.let { tracker ->
                tracker.computeCurrentVelocity(1000, maximumFlingVelocity)
                releaseThumb(tracker.getXVelocity(activePointerId))
            }
            recycleVelocityTracker()
            activePointerId = MotionEvent.INVALID_POINTER_ID
            performClick()
        }
        MotionEvent.ACTION_CANCEL -> {
            animateThumbTo(snapXFor(nearestIndex(thumbCenterX)))
            recycleVelocityTracker()
            activePointerId = MotionEvent.INVALID_POINTER_ID
        }
    }
    return true
}

private fun recycleVelocityTracker() {
    velocityTracker?.recycle()
    velocityTracker = null
}

override fun performClick(): Boolean {
    super.performClick()
    return true
}
```

多指控件还需在 `ACTION_POINTER_UP` 时选择新的 active pointer，并在切换后清除或重新采样速度，避免混入另一根手指的历史。

## 5. 动态边界与配置变化

布局宽度、RTL 或字体缩放可能改变物理边界。处理顺序应是：

1. 取消仍基于旧坐标系的动画。
2. 根据新尺寸重算 min/max 和吸附点。
3. 将当前逻辑值映射到新坐标。
4. 必要时从新位置开始过渡。

不要只保存像素位置作为业务状态；保存选中索引或 0..1 的逻辑进度，像素位置由当前布局推导。

## 6. 反例：弹簧与拖拽同时写同一属性

```kotlin
// 反例：DOWN 时没有取消动画，手指和弹簧争夺 thumbX。
override fun onTouchEvent(event: MotionEvent): Boolean {
    if (event.actionMasked == MotionEvent.ACTION_MOVE) {
        thumbCenterX = event.x
        invalidate()
    }
    return true
}
```

另一个反例是把 `FlingAnimation` 的速度直接填成 dp/s。动画属性是像素坐标时，速度也必须是 px/s；单位不一致会导致不同密度设备手感完全不同。

## 7. 生命周期与测试

```kotlin
override fun onDetachedFromWindow() {
    fling.cancel()
    spring.cancel()
    recycleVelocityTracker()
    super.onDetachedFromWindow()
}
```

tracker 按手势创建并在 `UP`、`CANCEL` 或 detach 时回收，因此 View 再次 attach 后不会复用已 recycle 的实例。测试时关注不变量，而不是等待固定毫秒数：最终位置在容差内、速度趋近于零、取消后没有继续写入、边界永不越界。

## 8. 实践检查清单

- [ ] 需要中途改目标或保留释放速度时，优先考虑物理动画。
- [ ] 位置与速度单位一致，通常分别是 px 与 px/s。
- [ ] Fling 的起始值位于 min/max 边界内。
- [ ] 手指接管前取消所有写同一属性的动画。
- [ ] fling 结束后的吸附继承剩余速度，避免突然停顿。
- [ ] 尺寸、RTL 等变化后重建物理边界。
- [ ] 逻辑状态不依赖旧布局下的绝对像素。
- [ ] detach 时取消动画并正确管理 VelocityTracker。

## 小结

DynamicAnimation 让位置、速度与目标在交互中连续。弹簧适合可变目标与回弹，衰减适合释放后的惯性；真正自然的体验来自单位一致、同一属性只有一个写入者、边界随布局更新，以及取消时保留明确的状态语义。

## 延伸阅读

- [Android Developers：Animate movement using spring physics](https://developer.android.com/develop/ui/views/animations/spring-animation)
- [DynamicAnimation API](https://developer.android.com/reference/androidx/dynamicanimation/animation/DynamicAnimation)
- [SpringAnimation API](https://developer.android.com/reference/androidx/dynamicanimation/animation/SpringAnimation)
- [FlingAnimation API](https://developer.android.com/reference/androidx/dynamicanimation/animation/FlingAnimation)
- [VelocityTracker API](https://developer.android.com/reference/android/view/VelocityTracker)
