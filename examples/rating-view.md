# 实战二：可拖动评分控件——事件、离散值与键盘交互

## 学习目标

在测量绘制之上加入完整输入模型：点击、拖动、父容器拦截、RTL、键盘、无障碍动作和回调抑制。最终得到可用于表单的 `RatingView`。

## 需求与验收

- 显示 1～10 个评分图标，默认 5 个；支持整星或半星步进。
- 点击、水平拖动、方向键均可改值；只读模式不响应输入。
- RTL 下视觉与数值方向一致；越界触点钳制到 `0..starCount`。
- 仅用户操作触发 `onRatingChanged(..., fromUser=true)`；编程设置可选择通知。
- 父级为 ViewPager/RecyclerView 时，仅在明确水平拖动后禁止父级拦截。
- 触控目标、键盘焦点、TalkBack 调整动作和状态恢复可用。

## 架构与状态图

```text
                 +-----------------+
MotionEvent ---->| gesture reducer |----> rating
Keys/TalkBack -->| DOWN/MOVE/UP     |        |
API setter ----->| clamp + quantize |        v
                 +-----------------+   invalidate
                          |                callback(fromUser)
                          +--> parent intercept policy

State: Idle --DOWN--> Pending --horizontal slop--> Dragging --UP/CANCEL--> Idle
```

## 关键算法

设可绘制内容宽为 `W`，指针相对内容起点的位置为 `x`。LTR 比例为 `x/W`，RTL 为 `1-x/W`：

```text
raw      = clamp(fraction, 0, 1) * starCount
quantized = round(raw / stepSize) * stepSize
```

`stepSize` 应满足 `(1 / stepSize)` 近似整数，本例接受 `1f` 或 `0.5f`。显示每一颗时把填充量钳制为 `rating-index` 的 `0..1`。半星通过 `clipRect` 裁切已填充路径，避免维护两套图标资源。

## Kotlin 实现

```kotlin
package com.example.widgets

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Parcel
import android.os.Parcelable
import android.util.AttributeSet
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.view.ViewCompat
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.round
import kotlin.math.sin

class RatingView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    fun interface OnRatingChangeListener {
        fun onRatingChanged(view: RatingView, rating: Float, fromUser: Boolean)
    }

    private val density = resources.displayMetrics.density
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop
    private val starPath = Path()
    private val emptyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.LTGRAY
        style = Paint.Style.FILL
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 193, 7)
        style = Paint.Style.FILL
    }

    var starCount: Int = 5
        set(value) {
            require(value in 1..10) { "starCount must be in 1..10" }
            if (field == value) return
            field = value
            rating = rating.coerceAtMost(value.toFloat())
            updateGeometry(width, height)
            requestLayout(); invalidate(); updateA11y()
        }

    var stepSize: Float = 0.5f
        set(value) {
            require(value == 0.5f || value == 1f) { "stepSize must be 0.5 or 1" }
            field = value
            setRatingInternal(rating, fromUser = false, notify = false)
        }

    var isIndicator: Boolean = false
        set(value) {
            field = value
            isFocusable = !value
            isClickable = !value
            updateA11y()
        }

    var rating: Float = 0f
        private set

    var listener: OnRatingChangeListener? = null
    private var downX = 0f
    private var downY = 0f
    private var dragging = false
    private var starSize = 0f
    private var gap = 4f * density

    init {
        isFocusable = true
        isClickable = true
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        updateA11y()
    }

    fun setRating(value: Float, notify: Boolean = false) {
        setRatingInternal(value, fromUser = false, notify = notify)
    }

    private fun setRatingInternal(value: Float, fromUser: Boolean, notify: Boolean = true) {
        require(value.isFinite()) { "rating must be finite" }
        val quantized = (round(value / stepSize) * stepSize)
            .coerceIn(0f, starCount.toFloat())
        if (rating == quantized) return
        rating = quantized
        invalidate()
        updateA11y()
        if (notify) listener?.onRatingChanged(this, rating, fromUser)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredStar = 40f * density
        val desiredW = (desiredStar * starCount + gap * (starCount - 1)).toInt() +
            paddingLeft + paddingRight
        val desiredH = desiredStar.toInt() + paddingTop + paddingBottom
        setMeasuredDimension(
            resolveSize(desiredW, widthMeasureSpec),
            resolveSize(desiredH, heightMeasureSpec)
        )
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        updateGeometry(w, h)
    }

    private fun updateGeometry(w: Int, h: Int) {
        val contentW = (w - paddingLeft - paddingRight).coerceAtLeast(0)
        val contentH = (h - paddingTop - paddingBottom).coerceAtLeast(0)
        starSize = min(
            contentH.toFloat(),
            (contentW - gap * (starCount - 1)).coerceAtLeast(0f) / starCount
        )
        buildStarPath(starSize)
    }

    private fun buildStarPath(size: Float) {
        starPath.reset()
        val cx = size / 2f
        val cy = size / 2f
        val outer = size / 2f
        val inner = outer * 0.45f
        for (i in 0 until 10) {
            val r = if (i % 2 == 0) outer else inner
            val angle = -PI / 2 + i * PI / 5
            val x = cx + (cos(angle) * r).toFloat()
            val y = cy + (sin(angle) * r).toFloat()
            if (i == 0) starPath.moveTo(x, y) else starPath.lineTo(x, y)
        }
        starPath.close()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val contentWidth = starSize * starCount + gap * (starCount - 1)
        val originX = paddingLeft +
            ((width - paddingLeft - paddingRight - contentWidth) / 2f)
        val originY = paddingTop +
            ((height - paddingTop - paddingBottom - starSize) / 2f)

        for (visualIndex in 0 until starCount) {
            val valueIndex = if (layoutDirection == LAYOUT_DIRECTION_RTL) {
                starCount - 1 - visualIndex
            } else visualIndex
            val fill = (rating - valueIndex).coerceIn(0f, 1f)
            val x = originX + visualIndex * (starSize + gap)
            canvas.save()
            canvas.translate(x, originY)
            canvas.drawPath(starPath, emptyPaint)
            if (fill > 0f) {
                canvas.save()
                val left = if (layoutDirection == LAYOUT_DIRECTION_RTL) {
                    starSize * (1f - fill)
                } else 0f
                val right = if (layoutDirection == LAYOUT_DIRECTION_RTL) {
                    starSize
                } else starSize * fill
                canvas.clipRect(left, 0f, right, starSize)
                canvas.drawPath(starPath, fillPaint)
                canvas.restore()
            }
            canvas.restore()
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (isIndicator || !isEnabled) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x; downY = event.y; dragging = false
                parent.requestDisallowInterceptTouchEvent(false)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = event.x - downX
                val dy = event.y - downY
                if (!dragging && kotlin.math.abs(dx) > touchSlop &&
                    kotlin.math.abs(dx) > kotlin.math.abs(dy)
                ) {
                    dragging = true
                    parent.requestDisallowInterceptTouchEvent(true)
                }
                if (dragging) updateFromX(event.x)
                return true
            }
            MotionEvent.ACTION_UP -> {
                if (!dragging) updateFromX(event.x)
                parent.requestDisallowInterceptTouchEvent(false)
                dragging = false
                performClick()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                parent.requestDisallowInterceptTouchEvent(false)
                dragging = false
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun updateFromX(x: Float) {
        val starSpan = starSize * starCount + gap * (starCount - 1)
        if (starSpan <= 0f) return
        val left = paddingLeft +
            (width - paddingLeft - paddingRight - starSpan) / 2f
        var fraction = ((x - left) / starSpan).coerceIn(0f, 1f)
        if (layoutDirection == LAYOUT_DIRECTION_RTL) fraction = 1f - fraction
        setRatingInternal(fraction * starCount, fromUser = true)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (isIndicator || !isEnabled) return super.onKeyDown(keyCode, event)
        val logicalDelta = when (keyCode) {
            KeyEvent.KEYCODE_DPAD_RIGHT -> if (layoutDirection == LAYOUT_DIRECTION_RTL) -stepSize else stepSize
            KeyEvent.KEYCODE_DPAD_LEFT -> if (layoutDirection == LAYOUT_DIRECTION_RTL) stepSize else -stepSize
            KeyEvent.KEYCODE_PLUS, KeyEvent.KEYCODE_EQUALS -> stepSize
            KeyEvent.KEYCODE_MINUS -> -stepSize
            else -> return super.onKeyDown(keyCode, event)
        }
        setRatingInternal(rating + logicalDelta, fromUser = true)
        return true
    }

    override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        info.className = "android.widget.SeekBar"
        info.rangeInfo = AccessibilityNodeInfo.RangeInfo.obtain(
            AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_FLOAT,
            0f, starCount.toFloat(), rating
        )
        if (!isIndicator && isEnabled) {
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD)
            info.isClickable = true
        }
    }

    override fun performAccessibilityAction(action: Int, arguments: android.os.Bundle?): Boolean {
        if (!isIndicator && isEnabled) {
            when (action) {
                AccessibilityNodeInfo.ACTION_SCROLL_FORWARD -> {
                    setRatingInternal(rating + stepSize, fromUser = true); return true
                }
                AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD -> {
                    setRatingInternal(rating - stepSize, fromUser = true); return true
                }
            }
        }
        return super.performAccessibilityAction(action, arguments)
    }

    private fun updateA11y() {
        ViewCompat.setStateDescription(
            this, context.getString(R.string.rating_state, rating, starCount)
        )
    }

    override fun onSaveInstanceState(): Parcelable = SavedState(super.onSaveInstanceState()).also {
        it.rating = rating
        it.starCount = starCount
        it.step = stepSize
        it.indicator = isIndicator
    }

    override fun onRestoreInstanceState(state: Parcelable?) {
        if (state !is SavedState) { super.onRestoreInstanceState(state); return }
        super.onRestoreInstanceState(state.superState)
        starCount = state.starCount
        stepSize = state.step
        isIndicator = state.indicator
        setRating(state.rating)
    }

    private class SavedState : BaseSavedState {
        var rating = 0f; var starCount = 5; var step = 0.5f; var indicator = false
        constructor(superState: Parcelable?) : super(superState)
        private constructor(p: Parcel) : super(p) {
            rating = p.readFloat(); starCount = p.readInt(); step = p.readFloat()
            indicator = p.readInt() == 1
        }
        override fun writeToParcel(out: Parcel, flags: Int) {
            super.writeToParcel(out, flags)
            out.writeFloat(rating); out.writeInt(starCount); out.writeFloat(step)
            out.writeInt(if (indicator) 1 else 0)
        }
        companion object CREATOR : Parcelable.Creator<SavedState> {
            override fun createFromParcel(p: Parcel) = SavedState(p)
            override fun newArray(size: Int): Array<SavedState?> = arrayOfNulls(size)
        }
    }
}
```

> **注意**：示例为突出输入模型省略了 XML 属性读取；生产库应仿照上一章声明 `starCount`、`stepSize`、颜色和间距，并通过统一 setter 校验。

## XML 与 Compose 使用

```xml
<com.example.widgets.RatingView
    android:id="@+id/rating"
    android:layout_width="match_parent"
    android:layout_height="56dp"
    android:contentDescription="@string/product_rating" />
```

```kotlin
binding.rating.listener = RatingView.OnRatingChangeListener { _, value, fromUser ->
    if (fromUser) viewModel.setRating(value)
}
```

Compose 互操作要在 `DisposableEffect` 中清除监听，避免旧 lambda 被 View 持有：

```kotlin
@Composable
fun LegacyRating(rating: Float, onRatingChange: (Float) -> Unit) {
    val latestCallback by rememberUpdatedState(onRatingChange)
    val viewRef = remember { mutableStateOf<RatingView?>(null) }
    AndroidView(
        factory = { context ->
            RatingView(context).also { view ->
                view.listener = RatingView.OnRatingChangeListener { _, value, fromUser ->
                    if (fromUser) latestCallback(value)
                }
                viewRef.value = view
            }
        },
        update = { view -> view.setRating(rating) }
    )
    DisposableEffect(Unit) {
        onDispose {
            viewRef.value?.listener = null
            viewRef.value = null
        }
    }
}
```

`rememberUpdatedState` 保证监听器调用最新 lambda，`DisposableEffect` 在组合释放时解绑，避免 View 持有过期回调。

## 无障碍

> **无障碍提示**：一个整体可调控件比五个无标签虚拟按钮更易理解。将类名暴露为 SeekBar、提供 RangeInfo 和前后滚动动作，TalkBack 即可宣布范围并调整。

图标本身无需单独朗读。控件最小高度建议 48dp；若视觉星星较小，仍保留足够的 View 边界。高对比模式下不要仅用黄色/灰色区分，可给空星增加描边。

## 状态保存与生命周期

保存评分配置与当前值，不保存手势中的 `dragging/downX`：旋转会终止当前手势。`listener` 属于外部依赖，绝不能写入状态。ViewModel 是表单真实数据源时，恢复后由状态流重新下发评分可避免双源冲突。

## 性能与陷阱

> **性能提示**：星形 `Path` 只在尺寸变化时构建，绘制时复用。图标数量上限也防止无意产生超大循环。

- DOWN 时立刻禁止父级拦截会破坏页面纵向滚动。
- 忽略 `ACTION_CANCEL` 会让父级长期无法拦截。
- `round()` 的半值规则可能影响产品体验；需要“触到即半星”时可改用 `ceil()` 并补边界测试。
- 只实现触摸不实现 `performClick()` 会触发 Lint 且无障碍点击链路不完整。
- RTL 只翻转绘制、不翻转输入映射，会出现“点左边得到最高分”。

## 测试策略

```kotlin
@Test fun halfStepIsQuantized() {
    val view = RatingView(context)
    view.stepSize = 0.5f
    view.setRating(3.26f)
    assertThat(view.rating).isEqualTo(3.5f)
}

@Test fun programmaticChangeDoesNotNotifyByDefault() {
    var calls = 0
    val view = RatingView(context)
    view.listener = RatingView.OnRatingChangeListener { _, _, _ -> calls++ }
    view.setRating(4f)
    assertThat(calls).isEqualTo(0)
}
```

仪器化测试覆盖：

1. Espresso `swipeRight()` 后值增加，RTL 下值方向符合视觉。
2. `pressKey(DPAD_RIGHT)` 更新一个步长。
3. AccessibilityNodeInfo 包含范围与调整动作。
4. 放入可滚动父容器，竖向滑动仍滚动页面，横向滑动调评分。
5. 截图覆盖 0、半星、满星、禁用、深色主题。

## 实践检查清单

- [ ] 输入先钳制再量化，NaN/Infinity 被拒绝
- [ ] 手势状态处理 DOWN/MOVE/UP/CANCEL
- [ ] 与父容器的拦截协议正确
- [ ] RTL、键盘、TalkBack 方向一致
- [ ] 用户回调与编程更新可区分

## 扩展练习

1. 用 `ExploreByTouchHelper` 把每颗星暴露为虚拟子节点，并比较整体 Range 模型的优缺点。
2. 增加悬停与鼠标滚轮支持。
3. 加载 VectorDrawable 星形并缓存为 Bitmap，比较不同尺寸下的清晰度与成本。
4. 支持任意合法步长，如 0.25，并处理浮点误差。

## 小结

交互控件不是给 `onTouchEvent()` 塞几行坐标判断。生产实现需要统一值约束、显式手势状态、父子协作，并让触摸、键盘和无障碍动作收敛到同一个状态更新函数。

## 延伸阅读

- [处理触摸手势](https://developer.android.com/develop/ui/views/touch-and-input/gestures)
- [让自定义 View 更易访问](https://developer.android.com/guide/topics/ui/accessibility/custom-views)
- [RTL 支持](https://developer.android.com/training/basics/supporting-devices/languages)
