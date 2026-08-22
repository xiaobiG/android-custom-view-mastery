# 实战一：可配置圆形进度控件——从测量到绘制

## 学习目标

本章用一个无交互的 `CircularProgressView` 打通自定义 View 的最短完整链路：自定义属性、测量、密度换算、绘制、状态保存、无障碍与测试。

## 需求与验收

- `progress` 限制在 `0..max`，`max` 必须大于 0；支持运行时更新。
- 支持轨道色、进度色、线宽、起始角、顺/逆时针和百分比文字。
- `wrap_content` 有稳定默认尺寸；非正方形约束下居中绘制最大内切圆。
- padding、描边端点和文字基线正确；不能在 `onDraw()` 中持续分配对象。
- 旋转屏幕后恢复进度、最大值和是否显示文字。
- TalkBack 能读出“进度，百分之 N”；进度变化时发送内容变化事件。

验收建议：分别放入 `80dp × 120dp`、`wrap_content`、带 padding 的容器；设置 `max=0` 应抛出清晰异常，设置 `progress=200` 应钳制而不是越界绘制。

## 架构与状态流

```text
XML 属性 / Kotlin setter
          |
          v
  validate + clamp ---------> requestLayout()  尺寸相关属性
          |                   invalidate()      视觉相关属性
          v
 progress / max / style
          |
          v
 onMeasure() ---> content square
          |
          v
 onDraw(): track -> progress arc -> label
          |
          +----> accessibility state description
```

## 核心机制与关键算法

### 1. 正确测量

`resolveSizeAndState()` 会遵守父容器给出的 `MeasureSpec`。期望边长为默认内容尺寸、两侧 padding 和描边宽度之和；最终宽高可以不同，绘制时取内容区短边。

### 2. 弧线几何

Android 角度以三点钟方向为 `0°`，顺时针为正：

```text
fraction   = progress / max
sweepAngle = fraction * 360 * direction
radius     = (min(contentWidth, contentHeight) - strokeWidth) / 2
```

描边中心位于 `RectF` 边界，因此矩形需向内缩进半个线宽，避免裁切。文字垂直居中不能用经验偏移，应使用字体度量：

```text
baseline = centerY - (fontMetrics.ascent + fontMetrics.descent) / 2
```

## 完整 Kotlin 实现

```kotlin
package com.example.widgets

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.Parcel
import android.os.Parcelable
import android.util.AttributeSet
import android.view.View
import android.view.accessibility.AccessibilityEvent
import androidx.annotation.ColorInt
import androidx.core.content.withStyledAttributes
import kotlin.math.min
import kotlin.math.roundToInt

class CircularProgressView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = R.attr.circularProgressStyle
) : View(context, attrs, defStyleAttr) {

    private val density = resources.displayMetrics.density
    private val arcBounds = RectF()
    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val progressPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
    }

    private var maxValue = 100
    private var progressValue = 0
    private var strokeWidthPx = 8f * density
    private var startAngle = -90f
    private var clockwise = true
    private var showText = true
    private var textSizePx = 16f * resources.displayMetrics.scaledDensity
    @ColorInt private var trackColor = Color.LTGRAY
    @ColorInt private var progressColor = Color.rgb(33, 150, 243)
    @ColorInt private var textColor = Color.DKGRAY

    init {
        context.withStyledAttributes(
            attrs, R.styleable.CircularProgressView, defStyleAttr,
            R.style.Widget_App_CircularProgress
        ) {
            maxValue = getInt(R.styleable.CircularProgressView_android_max, 100)
            require(maxValue > 0) { "android:max must be > 0" }
            progressValue = getInt(
                R.styleable.CircularProgressView_android_progress, 0
            ).coerceIn(0, maxValue)
            strokeWidthPx = getDimension(
                R.styleable.CircularProgressView_cpv_strokeWidth, strokeWidthPx
            )
            startAngle = getFloat(
                R.styleable.CircularProgressView_cpv_startAngle, -90f
            )
            clockwise = getBoolean(
                R.styleable.CircularProgressView_cpv_clockwise, true
            )
            showText = getBoolean(
                R.styleable.CircularProgressView_cpv_showText, true
            )
            textSizePx = getDimension(
                R.styleable.CircularProgressView_android_textSize, textSizePx
            )
            trackColor = getColor(
                R.styleable.CircularProgressView_cpv_trackColor, trackColor
            )
            progressColor = getColor(
                R.styleable.CircularProgressView_cpv_progressColor, progressColor
            )
            textColor = getColor(
                R.styleable.CircularProgressView_android_textColor, textColor
            )
        }
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        updatePaints()
        updateAccessibility()
    }

    private fun updatePaints() {
        trackPaint.strokeWidth = strokeWidthPx
        trackPaint.color = trackColor
        progressPaint.strokeWidth = strokeWidthPx
        progressPaint.color = progressColor
        textPaint.textSize = textSizePx
        textPaint.color = textColor
    }

    fun setMax(value: Int) {
        require(value > 0) { "max must be > 0" }
        if (maxValue == value) return
        maxValue = value
        progressValue = progressValue.coerceAtMost(value)
        updateAccessibility()
        invalidate()
    }

    fun getMax(): Int = maxValue

    fun setProgress(value: Int) {
        val newValue = value.coerceIn(0, maxValue)
        if (progressValue == newValue) return
        progressValue = newValue
        updateAccessibility()
        invalidate()
        sendAccessibilityEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED)
    }

    fun getProgress(): Int = progressValue

    fun setStrokeWidth(px: Float) {
        require(px >= 0f && px.isFinite()) { "stroke width must be finite and >= 0" }
        if (strokeWidthPx == px) return
        strokeWidthPx = px
        updatePaints()
        requestLayout()
        invalidate()
    }

    fun setShowText(show: Boolean) {
        if (showText == show) return
        showText = show
        updateAccessibility()
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val content = (96f * density).roundToInt()
        val desiredWidth = content + paddingLeft + paddingRight + strokeWidthPx.roundToInt()
        val desiredHeight = content + paddingTop + paddingBottom + strokeWidthPx.roundToInt()
        val width = resolveSizeAndState(desiredWidth, widthMeasureSpec, 0)
        val height = resolveSizeAndState(desiredHeight, heightMeasureSpec, 0)
        setMeasuredDimension(width, height)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val left = paddingLeft.toFloat()
        val top = paddingTop.toFloat()
        val right = width - paddingRight.toFloat()
        val bottom = height - paddingBottom.toFloat()
        val side = min(right - left, bottom - top).coerceAtLeast(0f)
        val cx = (left + right) / 2f
        val cy = (top + bottom) / 2f
        val half = (side - strokeWidthPx).coerceAtLeast(0f) / 2f
        arcBounds.set(cx - half, cy - half, cx + half, cy + half)

        canvas.drawOval(arcBounds, trackPaint)
        val direction = if (clockwise) 1f else -1f
        val sweep = progressValue.toFloat() / maxValue * 360f * direction
        if (sweep != 0f) canvas.drawArc(arcBounds, startAngle, sweep, false, progressPaint)

        if (showText) {
            val percent = (progressValue * 100f / maxValue).roundToInt()
            val fm = textPaint.fontMetrics
            val baseline = cy - (fm.ascent + fm.descent) / 2f
            canvas.drawText("$percent%", cx, baseline, textPaint)
        }
    }

    private fun updateAccessibility() {
        val percent = (progressValue * 100f / maxValue).roundToInt()
        contentDescription = context.getString(
            R.string.circular_progress_description, percent
        )
    }

    override fun onSaveInstanceState(): Parcelable = SavedState(super.onSaveInstanceState()).also {
        it.max = maxValue
        it.progress = progressValue
        it.showText = showText
    }

    override fun onRestoreInstanceState(state: Parcelable?) {
        if (state !is SavedState) {
            super.onRestoreInstanceState(state)
            return
        }
        super.onRestoreInstanceState(state.superState)
        maxValue = state.max.coerceAtLeast(1)
        progressValue = state.progress.coerceIn(0, maxValue)
        showText = state.showText
        updateAccessibility()
        invalidate()
    }

    private class SavedState : BaseSavedState {
        var max = 100
        var progress = 0
        var showText = true

        constructor(superState: Parcelable?) : super(superState)
        private constructor(source: Parcel) : super(source) {
            max = source.readInt()
            progress = source.readInt()
            showText = source.readInt() == 1
        }

        override fun writeToParcel(out: Parcel, flags: Int) {
            super.writeToParcel(out, flags)
            out.writeInt(max)
            out.writeInt(progress)
            out.writeInt(if (showText) 1 else 0)
        }

        companion object CREATOR : Parcelable.Creator<SavedState> {
            override fun createFromParcel(source: Parcel) = SavedState(source)
            override fun newArray(size: Int): Array<SavedState?> = arrayOfNulls(size)
        }
    }
}
```

属性与样式：

```xml
<!-- res/values/attrs.xml -->
<resources>
    <attr name="circularProgressStyle" format="reference" />
    <declare-styleable name="CircularProgressView">
        <attr name="android:max" />
        <attr name="android:progress" />
        <attr name="android:textSize" />
        <attr name="android:textColor" />
        <attr name="cpv_strokeWidth" format="dimension" />
        <attr name="cpv_startAngle" format="float" />
        <attr name="cpv_clockwise" format="boolean" />
        <attr name="cpv_showText" format="boolean" />
        <attr name="cpv_trackColor" format="color" />
        <attr name="cpv_progressColor" format="color" />
    </declare-styleable>
</resources>

<!-- res/values/styles.xml -->
<style name="Widget.App.CircularProgress">
    <item name="cpv_strokeWidth">8dp</item>
    <item name="cpv_showText">true</item>
</style>
```

> **注意**：库控件应使用库自己的默认样式；示例中的 `R.style.Widget_App_CircularProgress` 必须真实存在。

## XML 与 Compose 使用

```xml
<com.example.widgets.CircularProgressView
    android:id="@+id/progress"
    android:layout_width="120dp"
    android:layout_height="120dp"
    android:padding="8dp"
    android:max="200"
    android:progress="75"
    android:textSize="18sp"
    app:cpv_progressColor="?attr/colorPrimary"
    app:cpv_strokeWidth="10dp" />
```

Compose 中用 `AndroidView` 托管。`update` 可能频繁执行，setter 必须幂等：

```kotlin
@Composable
fun CircularProgress(
    progress: Int,
    max: Int,
    modifier: Modifier = Modifier
) {
    require(max > 0) { "max must be > 0" }
    AndroidView(
        modifier = modifier.semantics {
            progressBarRangeInfo = ProgressBarRangeInfo(
                current = progress.coerceIn(0, max).toFloat(),
                range = 0f..max.toFloat()
            )
        },
        factory = { CircularProgressView(it) },
        update = { view ->
            view.setMax(max)
            view.setProgress(progress)
        }
    )
}
```

## 无障碍

> **无障碍提示**：颜色不是唯一信息载体；保留文字或语义百分比。若进度高频更新，不要每帧发送 announcement，否则会淹没 TalkBack。

对于更严格的范围语义，可覆写 `onInitializeAccessibilityNodeInfo()`，设置 `AccessibilityNodeInfo.RangeInfo`。只读进度不应伪装成可点击按钮。

## 状态保存

View 必须有稳定 `android:id` 才会参与层级状态保存。保存业务状态而非派生值：弧形边界、Paint 和百分比文字可重新计算，不应写入 Parcel。若进度来自 ViewModel，则以 ViewModel 为单一事实源，可不在 View 内重复持久化。

## 性能与常见陷阱

> **性能提示**：`Paint`、`RectF` 都在初始化时创建；`onDraw()` 只修改已有对象。是否使用硬件层应由测量结果决定，不要为简单圆弧调用 `setLayerType()`。

- 把 `dp` 当像素：不同密度下尺寸失真。
- 用 `min(width, height)` 却忘记 padding：圆会偏心。
- 改线宽只调用 `invalidate()`：`wrap_content` 尺寸可能不再成立。
- 直接计算 `progress / max`：整数除法会在到达最大值前一直为 0。
- 每次绘制创建字符串通常成本不高，但高频动画可缓存百分比文字。

动画可放在外部以保持控件简单；若内部持有 `ValueAnimator`，应在 `onDetachedFromWindow()` 中取消。

## 测试策略

### 单元与 Robolectric

```kotlin
@RunWith(RobolectricTestRunner::class)
class CircularProgressViewTest {
    @Test fun progressIsClampedAndRestored() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val view = CircularProgressView(context).apply {
            id = View.generateViewId()
            setMax(10)
            setProgress(99)
        }
        assertThat(view.getProgress()).isEqualTo(10)
        val state = view.onSaveInstanceState()
        val restored = CircularProgressView(context)
        restored.onRestoreInstanceState(state)
        assertThat(restored.getMax()).isEqualTo(10)
        assertThat(restored.getProgress()).isEqualTo(10)
    }
}
```

### 仪器化检查

- 截图测试：0%、1%、50%、100%，浅/深色主题，大字体。
- Accessibility Scanner：描述是否包含当前值，触控目标规则是否适用。
- Macrobenchmark/Profile GPU Rendering：动画时是否稳定在帧预算内。
- 测量测试：`AT_MOST 60dp` 时不得超过父约束。

## 实践检查清单

- [ ] `MeasureSpec`、padding、描边裁切均处理
- [ ] setter 校验输入并选择 `invalidate()` 或 `requestLayout()`
- [ ] 状态有 id 时可恢复
- [ ] TalkBack 可读当前值
- [ ] 绘制热路径无对象抖动

## 扩展练习

1. 增加渐变进度色，并解释 `SweepGradient` 随尺寸变化时如何重建。
2. 用 `ValueAnimator` 实现值变化动画，处理重复目标和 detach。
3. 覆写范围无障碍语义，让测试读取 min/max/current。
4. 添加不定进度模式，并遵守系统动画缩放设置。

## 小结

本例建立了生产级控件的底线：先定义状态不变量，再正确测量，最后绘制；尺寸变化与视觉变化走不同失效路径。后续案例都复用这一原则。

## 延伸阅读

- [自定义 View](https://developer.android.com/develop/ui/views/layout/custom-views/custom-components)
- [保存 View 状态](https://developer.android.com/topic/libraries/architecture/saving-states)
- [Compose 与 View 互操作](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose)
