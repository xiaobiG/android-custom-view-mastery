# 常用工具类

本附录收集可直接放入 View 项目的 Kotlin 小工具。示例默认运行在主线程，使用 Android 平台 API；复制后请按包名拆文件，而不是把所有代码塞进一个 `Utils.kt`。

> **注意**：工具只消除样板代码，不能替代对测量契约、坐标空间、事件序列和生命周期的理解。

## 1. dp、sp 与 px

```kotlin
import android.content.res.Resources
import android.util.TypedValue
import kotlin.math.roundToInt

fun Float.dp(resources: Resources): Float =
    TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP,
        this,
        resources.displayMetrics,
    )

fun Float.sp(resources: Resources): Float =
    TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_SP,
        this,
        resources.displayMetrics,
    )

fun Float.dpToPxInt(resources: Resources): Int = dp(resources).roundToInt()
fun Float.spToPxInt(resources: Resources): Int = sp(resources).roundToInt()

fun Float.pxToDp(resources: Resources): Float =
    this / resources.displayMetrics.density

fun Float.pxToSp(resources: Resources): Float =
    this / resources.displayMetrics.scaledDensity
```

用法：

```kotlin
val strokeWidthPx = 2f.dp(resources)
val labelSizePx = 14f.sp(resources)
paint.strokeWidth = strokeWidthPx
paint.textSize = labelSizePx
```

**边界**：

- 几何尺寸用 dp，用户可读文字用 sp；Canvas 的 `Paint.textSize` 接收 px，所以需要转换。
- 中间计算保留 `Float`，只在像素栅格、`setMeasuredDimension()` 等需要整数时取整。
- 不要缓存跨配置永久有效的换算结果；密度、字体缩放或 `Resources` 可能变化。
- `scaledDensity` 反映字体缩放；不要用 `density` 代替它，也不要强行限制用户字号。

## 2. MeasureSpec 辅助

```kotlin
import android.view.View
import kotlin.math.max
import kotlin.math.min

@JvmInline
value class Spec private constructor(private val packed: Int) {
    val mode: Int get() = View.MeasureSpec.getMode(packed)
    val size: Int get() = View.MeasureSpec.getSize(packed)

    fun resolve(desiredSize: Int): Int = when (mode) {
        View.MeasureSpec.EXACTLY -> size
        View.MeasureSpec.AT_MOST -> min(desiredSize, size)
        View.MeasureSpec.UNSPECIFIED -> desiredSize
        else -> error("Unknown MeasureSpec mode: $mode")
    }

    override fun toString(): String = View.MeasureSpec.toString(packed)

    companion object {
        fun from(packed: Int): Spec = Spec(packed)
    }
}

fun View.resolveMeasuredSize(
    desiredContentWidth: Int,
    desiredContentHeight: Int,
    widthMeasureSpec: Int,
    heightMeasureSpec: Int,
): Pair<Int, Int> {
    val desiredWidth = max(suggestedMinimumWidth, paddingLeft +
        desiredContentWidth + paddingRight)
    val desiredHeight = max(suggestedMinimumHeight, paddingTop +
        desiredContentHeight + paddingBottom)

    return View.resolveSizeAndState(desiredWidth, widthMeasureSpec, 0) to
        View.resolveSizeAndState(desiredHeight, heightMeasureSpec, 0)
}
```

在 `onMeasure()` 中：

```kotlin
override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
    val (width, height) = resolveMeasuredSize(
        desiredContentWidth = chartWidthPx,
        desiredContentHeight = chartHeightPx,
        widthMeasureSpec = widthMeasureSpec,
        heightMeasureSpec = heightMeasureSpec,
    )
    setMeasuredDimension(width, height)
}
```

**边界**：

- `EXACTLY` 必须接受父容器给定尺寸；`AT_MOST` 不能超过上限；`UNSPECIFIED` 没有上限。
- `resolveSizeAndState()` 的结果含测量状态位，应原样交给 `setMeasuredDimension()`，不要再参与普通加减。
- 自定义 `ViewGroup` 仍需使用 `getChildMeasureSpec()`、margin 与 LayoutParams 逐个测量子 View；上面的函数只适合叶子 View。
- intrinsic content 应包含 padding、foreground/背景最小尺寸和 `suggestedMinimumWidth/Height`。

## 3. RectF 与 Matrix 坐标映射

### 3.1 点和矩形映射

```kotlin
import android.graphics.Matrix
import android.graphics.PointF
import android.graphics.RectF

fun Matrix.mapPoint(x: Float, y: Float, out: PointF = PointF()): PointF {
    val values = floatArrayOf(x, y)
    mapPoints(values)
    out.set(values[0], values[1])
    return out
}

fun Matrix.mapRectCopy(source: RectF, out: RectF = RectF()): RectF {
    out.set(source)
    mapRect(out)
    return out
}

fun Matrix.invertedOrNull(out: Matrix = Matrix()): Matrix? =
    if (invert(out)) out else null

fun Matrix.unmapPoint(x: Float, y: Float, out: PointF = PointF()): PointF? =
    invertedOrNull()?.mapPoint(x, y, out)
```

### 3.2 内容坐标命中测试

```kotlin
class ContentTransform {
    /** content -> view */
    val contentToView = Matrix()
    private val viewToContent = Matrix()
    private val scratchPoint = FloatArray(2)

    fun updateInverse(): Boolean = contentToView.invert(viewToContent)

    /** 返回复用数组；调用方不要持有。 */
    fun viewToContent(x: Float, y: Float): FloatArray {
        scratchPoint[0] = x
        scratchPoint[1] = y
        viewToContent.mapPoints(scratchPoint)
        return scratchPoint
    }

    fun hitTest(viewX: Float, viewY: Float, contentBounds: RectF): Boolean {
        val p = viewToContent(viewX, viewY)
        return contentBounds.contains(p[0], p[1])
    }
}
```

更新顺序：

```text
模型内容坐标 --contentToView--> View 局部坐标 --Canvas/窗口--> 屏幕
触摸 View 坐标 --inverse Matrix--> 内容坐标 --命中测试--> 模型对象
```

> **性能提示**：`onDraw()` 和高频 `ACTION_MOVE` 中复用 `Matrix`、`RectF`、`FloatArray`，避免逐帧分配。

**边界**：

- `MotionEvent.x/y` 是接收 View 的局部坐标；`rawX/rawY` 接近屏幕坐标。不要混用。
- `Matrix.mapRect()` 对旋转或斜切后的矩形返回轴对齐包围盒（AABB），不是四边形精确边界；精确命中应映射四个角或把触点逆变换回模型空间。
- 奇异矩阵（如某轴缩放为 0）不可逆，必须检查 `invert()` 的布尔返回值。
- 修改正向矩阵后必须同步刷新逆矩阵；上例适合手动控制更新时机的控件。
- `View.matrix` 不包含祖先滚动、窗口位置等完整层级变换；跨 View/窗口映射优先使用平台坐标 API，并明确源与目标坐标空间。

## 4. 触摸状态辅助

下面的状态机只处理“单指点击或拖动”的仲裁，多点缩放应交给 `ScaleGestureDetector` 并建立单独状态。

```kotlin
import android.view.MotionEvent
import android.view.ViewConfiguration
import kotlin.math.hypot

class DragTouchState(viewConfiguration: ViewConfiguration) {
    enum class Phase { IDLE, POSSIBLE_CLICK, DRAGGING }

    var phase: Phase = Phase.IDLE
        private set
    var activePointerId: Int = MotionEvent.INVALID_POINTER_ID
        private set
    var lastX: Float = 0f
        private set
    var lastY: Float = 0f
        private set

    private var downX = 0f
    private var downY = 0f
    private val touchSlop = viewConfiguration.scaledTouchSlop.toFloat()

    fun onDown(event: MotionEvent) {
        activePointerId = event.getPointerId(0)
        downX = event.x
        downY = event.y
        lastX = downX
        lastY = downY
        phase = Phase.POSSIBLE_CLICK
    }

    /** 返回本次位移；找不到活动指针时返回 null。 */
    fun onMove(event: MotionEvent): Pair<Float, Float>? {
        val index = event.findPointerIndex(activePointerId)
        if (index < 0) return null
        val x = event.getX(index)
        val y = event.getY(index)

        if (phase == Phase.POSSIBLE_CLICK &&
            hypot(x - downX, y - downY) > touchSlop
        ) {
            phase = Phase.DRAGGING
        }

        val delta = (x - lastX) to (y - lastY)
        lastX = x
        lastY = y
        return delta
    }

    fun onPointerUp(event: MotionEvent) {
        val upIndex = event.actionIndex
        if (event.getPointerId(upIndex) != activePointerId) return
        val replacement = if (upIndex == 0) 1 else 0
        if (replacement < event.pointerCount) {
            activePointerId = event.getPointerId(replacement)
            lastX = event.getX(replacement)
            lastY = event.getY(replacement)
        } else {
            reset()
        }
    }

    fun reset() {
        phase = Phase.IDLE
        activePointerId = MotionEvent.INVALID_POINTER_ID
    }
}
```

典型接入：

```kotlin
private val touch = DragTouchState(ViewConfiguration.get(context))

override fun onTouchEvent(event: MotionEvent): Boolean = when (event.actionMasked) {
    MotionEvent.ACTION_DOWN -> {
        parent.requestDisallowInterceptTouchEvent(true)
        touch.onDown(event)
        isPressed = true
        true
    }
    MotionEvent.ACTION_MOVE -> {
        touch.onMove(event)?.let { (dx, dy) ->
            if (touch.phase == DragTouchState.Phase.DRAGGING) {
                panBy(dx, dy)
                postInvalidateOnAnimation()
            }
        }
        true
    }
    MotionEvent.ACTION_POINTER_UP -> {
        touch.onPointerUp(event)
        true
    }
    MotionEvent.ACTION_UP -> {
        val click = touch.phase == DragTouchState.Phase.POSSIBLE_CLICK
        isPressed = false
        touch.reset()
        parent.requestDisallowInterceptTouchEvent(false)
        if (click) performClick()
        true
    }
    MotionEvent.ACTION_CANCEL -> {
        isPressed = false
        touch.reset()
        parent.requestDisallowInterceptTouchEvent(false)
        true
    }
    else -> super.onTouchEvent(event)
}

override fun performClick(): Boolean {
    super.performClick()
    // 执行业务点击；保留 super 以产生无障碍点击事件。
    return true
}
```

**边界**：

- 只有在 `ACTION_DOWN` 返回 `true` 后，View 才能期待收到后续序列。
- 必须处理 `ACTION_CANCEL`；它不是点击，也不应提交拖动结果。
- `requestDisallowInterceptTouchEvent(true)` 不是永久锁，应在 UP/CANCEL 释放；复杂嵌套滚动优先实现 AndroidX Nested Scrolling 协议。
- pointer **index** 会变化，pointer **ID** 才用于跨事件追踪。
- 触摸状态机不负责速度。需要 fling 时复用一个 `VelocityTracker`，每个事件调用 `addMovement()`，UP 时 `computeCurrentVelocity(1000, max)`，结束后 `recycle()`。

## 5. 动画与生命周期

### 5.1 Animator 托管器

```kotlin
import android.animation.Animator

class AnimatorRegistry {
    private val running = LinkedHashSet<Animator>()

    fun start(animator: Animator) {
        running += animator
        animator.addListener(object : Animator.AnimatorListener {
            override fun onAnimationStart(animation: Animator) = Unit
            override fun onAnimationRepeat(animation: Animator) = Unit
            override fun onAnimationCancel(animation: Animator) = Unit
            override fun onAnimationEnd(animation: Animator) {
                running -= animation
                animation.removeListener(this)
            }
        })
        animator.start()
    }

    fun cancelAll() {
        running.toList().forEach(Animator::cancel)
        running.clear()
    }
}
```

在自定义 View 中，保存每一个延迟任务的原始引用，并在 detach 时移除：

```kotlin
private val animators = AnimatorRegistry()
private val settleRunnable = Runnable { settleNow() }

override fun onDetachedFromWindow() {
    animators.cancelAll()
    removeCallbacks(settleRunnable)
    super.onDetachedFromWindow()
}
```

### 5.2 帧回调托管器

```kotlin
import android.view.Choreographer

class FrameTicker(
    private val onFrame: (frameTimeNanos: Long) -> Boolean,
) : Choreographer.FrameCallback {
    private val choreographer = Choreographer.getInstance()
    private var posted = false

    fun start() {
        if (!posted) {
            posted = true
            choreographer.postFrameCallback(this)
        }
    }

    override fun doFrame(frameTimeNanos: Long) {
        posted = false
        if (onFrame(frameTimeNanos)) start()
    }

    fun stop() {
        if (posted) choreographer.removeFrameCallback(this)
        posted = false
    }
}
```

```kotlin
private val ticker = FrameTicker { frameTimeNanos ->
    val needsMoreFrames = physics.step(frameTimeNanos)
    postInvalidateOnAnimation()
    needsMoreFrames
}

override fun onDetachedFromWindow() {
    ticker.stop()
    animators.cancelAll()
    super.onDetachedFromWindow()
}
```

**边界**：

- `Animator`、`Choreographer` 与 View 修改必须在创建它们的 Looper（通常是主线程）使用。
- `cancel()` 通常仍会触发 cancel/end 回调；业务提交逻辑应区分正常结束与取消。
- `onDetachedFromWindow()` 中停止 animator、frame callback、fling、Runnable、观察者和监听器；重新 attach 时按状态恢复，而不是默认续播。
- 不要从 View 持有 Activity、Fragment 或长生命周期 owner 的强引用；回调在 detach 时置空或由 owner 注册/注销。
- 动画只改变绘制参数时用 `postInvalidateOnAnimation()`；改变测量尺寸才 `requestLayout()`，避免每帧重测整棵树。
- 尊重“移除动画”偏好；装饰动画可缩短或直接到终态，不能让禁用动画导致业务状态永远不完成。

## 6. 发布前复制检查

- [ ] 工具类命名表达坐标空间或单位，例如 `contentToView`、`dpToPx`。
- [ ] 高频路径无临时对象；必要时用 profiler 验证，而不是凭感觉优化。
- [ ] `ACTION_CANCEL`、活动指针切换和不可逆 Matrix 都有测试。
- [ ] View detach 后无 Animator、帧回调、Runnable 或监听器继续持有它。
- [ ] 点击最终调用 `performClick()`；自定义虚拟子元素使用 `ExploreByTouchHelper`。
- [ ] 配置变化、RTL、字体缩放、不同刷新率与硬件加速开关下行为可接受。

## 延伸阅读

- [View.MeasureSpec API](https://developer.android.com/reference/android/view/View.MeasureSpec)
- [Matrix API](https://developer.android.com/reference/android/graphics/Matrix)
- [触摸手势概览](https://developer.android.com/develop/ui/views/touch-and-input/gestures)
- [优化自定义 View](https://developer.android.com/develop/ui/views/layout/custom-views/optimizing-view)
