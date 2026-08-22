# 实战四：生产级签名板——轨迹平滑、压感、撤销与导出

## 学习目标

本章实现 `SignaturePadView`，覆盖高频触控采样、二次贝塞尔平滑、速度/压感线宽、脏矩形刷新、撤销重做、位图导出、状态分层与生命周期。它比“把触点连成 Path”多出的部分，正是生产签名组件的可靠性来源。

## 需求与验收

- 单指书写，线条连续且平滑；快速划线不丢历史采样点。
- 笔宽根据压力和速度平滑变化，始终处于 `minWidth..maxWidth`。
- 支持撤销、重做、清空；新笔画会清空重做栈。
- 可导出透明或白底 PNG，指定倍率，导出不修改屏幕状态。
- 手掌/第二根手指不会加入当前笔画；收到 CANCEL 能安全收尾。
- 状态恢复仅保存合理规模的矢量笔画；大签名应由 ViewModel/文件管理。
- TalkBack 用户可执行清空/撤销动作，控件有明确状态描述。

## 架构与数据流

```text
MotionEvent(history + current)
       |
       v
Sample(x,y,time,pressure) -> low-pass width filter
       |
       v
midpoint smoothing -> Segment(quad, startWidth, endWidth)
       |
       +----> current Stroke ----UP----> committed strokes
       |                              /          \
       +----> dirty Rect -> invalidate         undo / redo

Render target abstraction:
  screen Canvas  <--- render(strokes) ---> export Bitmap Canvas
```

状态分三层：

1. **持久模型**：已提交 `Stroke` 列表。
2. **瞬时输入**：活动 pointer、上一个采样、当前笔画。
3. **派生缓存**：每段轮廓 Path、脏矩形、可选背景位图。

## 关键算法

### 1. 不漏掉历史采样

`MotionEvent` 的一次 MOVE 可能携带多个历史点。必须先遍历 `historySize`，再处理当前点。每个点都使用对应的 `eventTime/pressure`。

### 2. 中点二次贝塞尔平滑

原始点 `P0,P1,P2` 到达时，用 `P1` 作控制点，从前一中点绘制到新中点：

```text
M0 = (P0 + P1) / 2
M1 = (P1 + P2) / 2
curve: M0 --quadratic(control=P1)--> M1
```

首尾补短线，避免端点缺口。可变宽曲线若只改 Paint.strokeWidth，会让整条 Path 使用同一宽度；本例把每小段存为独立 `Segment`，绘制时取首尾宽度均值。更高质量的实现应生成左右轮廓并填充。

### 3. 速度与压力融合

```text
velocity = distance / max(dt, 1ms)
velocityFactor = 1 / (1 + k * velocity)
pressureFactor = clamp(pressure, .1, 1)
targetWidth = lerp(minWidth, maxWidth, .7*velocityFactor + .3*pressureFactor)
width = lerp(previousWidth, targetWidth, .35)   // 低通滤波
```

算法参数属于视觉语言，应通过真机触笔/手指样本调校。

## Kotlin 实现：数据模型与渲染

```kotlin
package com.example.widgets

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.graphics.RectF
import android.os.Bundle
import android.os.Parcel
import android.os.Parcelable
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.view.ViewCompat
import java.io.OutputStream
import kotlin.math.hypot

class SignaturePadView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    data class Segment(
        val startX: Float, val startY: Float,
        val controlX: Float, val controlY: Float,
        val endX: Float, val endY: Float,
        val startWidth: Float, val endWidth: Float
    )

    data class Stroke(
        val color: Int,
        val segments: MutableList<Segment> = mutableListOf()
    )

    private data class Sample(
        val x: Float, val y: Float,
        val time: Long, val pressure: Float, val width: Float
    )

    private val density = resources.displayMetrics.density
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.BLACK
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val segmentPath = Path()
    private val dirty = RectF()
    private val strokes = mutableListOf<Stroke>()
    private val redoStack = ArrayDeque<Stroke>()
    private var currentStroke: Stroke? = null
    private var previous: Sample? = null
    private var previousMid: PointF? = null
    private var activePointerId = MotionEvent.INVALID_POINTER_ID

    var penColor: Int = Color.BLACK
    var minWidth: Float = 1.5f * density
        set(value) {
            require(value.isFinite() && value >= 0f && value <= maxWidth) {
                "minWidth must be finite and in 0..maxWidth"
            }
            field = value
        }
    var maxWidth: Float = 6f * density
        set(value) {
            require(value.isFinite() && value >= minWidth) {
                "maxWidth must be finite and >= minWidth"
            }
            field = value
        }
    var onSignatureChanged: ((isEmpty: Boolean) -> Unit)? = null

    init {
        setBackgroundColor(Color.TRANSPARENT)
        isFocusable = true
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        updateA11y()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        render(canvas, includeCurrent = true)
    }

    private fun render(canvas: Canvas, includeCurrent: Boolean) {
        strokes.forEach { drawStroke(canvas, it) }
        if (includeCurrent) currentStroke?.let { drawStroke(canvas, it) }
    }

    private fun drawStroke(canvas: Canvas, stroke: Stroke) {
        paint.color = stroke.color
        stroke.segments.forEach { segment ->
            paint.strokeWidth = (segment.startWidth + segment.endWidth) / 2f
            segmentPath.reset()
            segmentPath.moveTo(segment.startX, segment.startY)
            segmentPath.quadTo(
                segment.controlX, segment.controlY,
                segment.endX, segment.endY
            )
            canvas.drawPath(segmentPath, paint)
        }
    }
```

## Kotlin 实现：采样与轨迹平滑

```kotlin
    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!isEnabled) return false
                activePointerId = event.getPointerId(0)
                parent.requestDisallowInterceptTouchEvent(true)
                beginStroke(event.getX(0), event.getY(0), event.eventTime, event.getPressure(0))
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val index = event.findPointerIndex(activePointerId)
                if (index < 0) return false
                for (h in 0 until event.historySize) {
                    addSample(
                        event.getHistoricalX(index, h),
                        event.getHistoricalY(index, h),
                        event.getHistoricalEventTime(h),
                        event.getHistoricalPressure(index, h)
                    )
                }
                addSample(event.getX(index), event.getY(index), event.eventTime, event.getPressure(index))
                return true
            }
            MotionEvent.ACTION_POINTER_UP -> {
                val index = event.actionIndex
                if (event.getPointerId(index) == activePointerId) finishStroke(commit = true)
                return true
            }
            MotionEvent.ACTION_UP -> {
                finishStroke(commit = true)
                performClick()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                // CANCEL 可能来自系统手势；保留已产生的可见笔迹比静默丢失更符合签名场景。
                finishStroke(commit = currentStroke?.segments?.isNotEmpty() == true)
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun beginStroke(x: Float, y: Float, time: Long, pressure: Float) {
        val width = widthFor(previous = null, x, y, time, pressure)
        val sample = Sample(x, y, time, pressure, width)
        currentStroke = Stroke(penColor)
        previous = sample
        previousMid = PointF(x, y)
        dirty.set(x, y, x, y)
    }

    private fun addSample(x: Float, y: Float, time: Long, pressure: Float) {
        val p0 = previous ?: return
        val distance = hypot(x - p0.x, y - p0.y)
        if (distance < 0.4f * density) return
        val width = widthFor(p0, x, y, time, pressure)
        val p1 = Sample(x, y, time, pressure, width)
        val oldMid = previousMid ?: PointF(p0.x, p0.y)
        val newMidX = (p0.x + p1.x) / 2f
        val newMidY = (p0.y + p1.y) / 2f
        val segment = Segment(
            oldMid.x, oldMid.y,
            p0.x, p0.y,
            newMidX, newMidY,
            p0.width, p1.width
        )
        currentStroke?.segments?.add(segment)
        previous = p1
        oldMid.set(newMidX, newMidY)
        previousMid = oldMid
        invalidateSegment(segment)
    }

    private fun widthFor(
        previous: Sample?, x: Float, y: Float, time: Long, pressure: Float
    ): Float {
        val previousWidth = previous?.width ?: maxWidth
        val velocity = if (previous == null) 0f else {
            val dt = (time - previous.time).coerceAtLeast(1L).toFloat()
            hypot(x - previous.x, y - previous.y) / dt
        }
        val velocityFactor = 1f / (1f + 0.08f * velocity)
        val pressureFactor = pressure.coerceIn(0.1f, 1f)
        val blend = (0.7f * velocityFactor + 0.3f * pressureFactor).coerceIn(0f, 1f)
        val target = minWidth + (maxWidth - minWidth) * blend
        return previousWidth + (target - previousWidth) * 0.35f
    }

    private fun invalidateSegment(s: Segment) {
        val pad = maxOf(s.startWidth, s.endWidth) / 2f + 2f * density
        dirty.set(
            minOf(s.startX, s.controlX, s.endX) - pad,
            minOf(s.startY, s.controlY, s.endY) - pad,
            maxOf(s.startX, s.controlX, s.endX) + pad,
            maxOf(s.startY, s.controlY, s.endY) + pad
        )
        invalidate(
            dirty.left.toInt(), dirty.top.toInt(),
            dirty.right.toInt() + 1, dirty.bottom.toInt() + 1
        )
    }

    private fun finishStroke(commit: Boolean) {
        val stroke = currentStroke
        val last = previous
        val mid = previousMid
        // 中点平滑只画到最后一个中点；补到最后原始采样，避免笔画尾部缺半段。
        if (stroke != null && stroke.segments.isNotEmpty() && last != null && mid != null &&
            (mid.x != last.x || mid.y != last.y)
        ) {
            val tail = Segment(
                mid.x, mid.y, last.x, last.y, last.x, last.y,
                last.width, last.width
            )
            stroke.segments += tail
            invalidateSegment(tail)
        }
        if (commit && stroke != null && stroke.segments.isNotEmpty()) {
            // 只有真正提交的新笔画才分叉历史；空白轻触不应破坏 redo。
            redoStack.clear()
            strokes += stroke
        }
        currentStroke = null
        previous = null
        previousMid = null
        activePointerId = MotionEvent.INVALID_POINTER_ID
        parent.requestDisallowInterceptTouchEvent(false)
        invalidate()
        notifyChanged()
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
```

> **注意**：本文把单点轻触视为空笔画。若产品要保留点，应在 UP 时添加一个长度极短、圆端点的 Segment。

## Kotlin 实现：命令、导出、无障碍与状态

```kotlin
    fun canUndo(): Boolean = strokes.isNotEmpty()
    fun canRedo(): Boolean = redoStack.isNotEmpty()
    fun isSignatureEmpty(): Boolean = strokes.isEmpty() && currentStroke == null

    fun undo(): Boolean {
        val stroke = strokes.removeLastOrNull() ?: return false
        redoStack.addLast(stroke)
        invalidate(); notifyChanged()
        return true
    }

    fun redo(): Boolean {
        val stroke = redoStack.removeLastOrNull() ?: return false
        strokes += stroke
        invalidate(); notifyChanged()
        return true
    }

    fun clear() {
        if (strokes.isEmpty() && currentStroke == null) return
        strokes.clear(); redoStack.clear(); currentStroke = null
        previous = null; previousMid = null
        activePointerId = MotionEvent.INVALID_POINTER_ID
        parent?.requestDisallowInterceptTouchEvent(false)
        invalidate(); notifyChanged()
    }

    fun exportPng(
        output: OutputStream,
        scale: Float = 1f,
        backgroundColor: Int = Color.TRANSPARENT
    ): Boolean {
        require(scale.isFinite() && scale > 0f && scale <= 4f) { "scale must be in (0,4]" }
        val bitmap = Bitmap.createBitmap(
            (width * scale).toInt().coerceAtLeast(1),
            (height * scale).toInt().coerceAtLeast(1),
            Bitmap.Config.ARGB_8888
        )
        return try {
            val exportCanvas = Canvas(bitmap)
            if (backgroundColor != Color.TRANSPARENT) exportCanvas.drawColor(backgroundColor)
            exportCanvas.scale(scale, scale)
            render(exportCanvas, includeCurrent = false)
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
        } finally {
            bitmap.recycle()
        }
    }

    private fun notifyChanged() {
        updateA11y()
        onSignatureChanged?.invoke(isSignatureEmpty())
    }

    private fun updateA11y() {
        ViewCompat.setStateDescription(
            this,
            context.resources.getQuantityString(
                R.plurals.signature_stroke_count, strokes.size, strokes.size
            )
        )
    }

    override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        info.className = SignaturePadView::class.java.name
        if (canUndo()) info.addAction(
            AccessibilityNodeInfo.AccessibilityAction(
                R.id.accessibility_action_undo, context.getString(R.string.undo)
            )
        )
        if (!isSignatureEmpty()) info.addAction(
            AccessibilityNodeInfo.AccessibilityAction(
                R.id.accessibility_action_clear, context.getString(R.string.clear_signature)
            )
        )
    }

    override fun performAccessibilityAction(action: Int, arguments: Bundle?): Boolean = when (action) {
        R.id.accessibility_action_undo -> undo()
        R.id.accessibility_action_clear -> { clear(); true }
        else -> super.performAccessibilityAction(action, arguments)
    }

    override fun onSaveInstanceState(): Parcelable = SavedState(super.onSaveInstanceState()).also {
        // 限制层级状态体积，超出时交给 ViewModel/文件层。
        it.strokes = if (segmentCount() <= MAX_SAVED_SEGMENTS) deepCopy(strokes) else emptyList()
    }

    override fun onRestoreInstanceState(state: Parcelable?) {
        if (state !is SavedState) { super.onRestoreInstanceState(state); return }
        super.onRestoreInstanceState(state.superState)
        strokes.clear(); strokes.addAll(state.strokes)
        redoStack.clear(); notifyChanged(); invalidate()
    }

    private fun segmentCount() = strokes.sumOf { it.segments.size }
    private fun deepCopy(source: List<Stroke>) = source.map {
        Stroke(it.color, it.segments.toMutableList())
    }

    private class SavedState : BaseSavedState {
        var strokes: List<Stroke> = emptyList()
        constructor(superState: Parcelable?) : super(superState)
        private constructor(p: Parcel) : super(p) {
            val strokeCount = p.readInt().coerceAtLeast(0)
            strokes = List(strokeCount) {
                val color = p.readInt()
                val segments = MutableList(p.readInt().coerceAtLeast(0)) {
                    Segment(
                        p.readFloat(), p.readFloat(), p.readFloat(), p.readFloat(),
                        p.readFloat(), p.readFloat(), p.readFloat(), p.readFloat()
                    )
                }
                Stroke(color, segments)
            }
        }
        override fun writeToParcel(out: Parcel, flags: Int) {
            super.writeToParcel(out, flags)
            out.writeInt(strokes.size)
            strokes.forEach { stroke ->
                out.writeInt(stroke.color); out.writeInt(stroke.segments.size)
                stroke.segments.forEach { s ->
                    out.writeFloat(s.startX); out.writeFloat(s.startY)
                    out.writeFloat(s.controlX); out.writeFloat(s.controlY)
                    out.writeFloat(s.endX); out.writeFloat(s.endY)
                    out.writeFloat(s.startWidth); out.writeFloat(s.endWidth)
                }
            }
        }
        companion object CREATOR : Parcelable.Creator<SavedState> {
            override fun createFromParcel(p: Parcel) = SavedState(p)
            override fun newArray(size: Int): Array<SavedState?> = arrayOfNulls(size)
        }
    }

    override fun onDetachedFromWindow() {
        parent?.requestDisallowInterceptTouchEvent(false)
        onSignatureChanged = null
        super.onDetachedFromWindow()
    }

    companion object { private const val MAX_SAVED_SEGMENTS = 2_000 }
}
```

`R.id.accessibility_action_undo` 与 `clear` 可在 `res/values/ids.xml` 声明：

```xml
<resources>
    <item name="accessibility_action_undo" type="id" />
    <item name="accessibility_action_clear" type="id" />
</resources>
```

> **注意**：`Bitmap.createBitmap()` 可能因超大倍率造成内存压力。上限之外还应依据 `width * height * 4 * scale²` 做预算，导出放到工作线程时必须先复制不可变笔画快照，不能跨线程读取正在变更的 View 状态。

## XML 与 Compose 使用

```xml
<com.example.widgets.SignaturePadView
    android:id="@+id/signature"
    android:layout_width="match_parent"
    android:layout_height="240dp"
    android:background="@drawable/signature_border"
    android:contentDescription="@string/signature_pad" />
```

```kotlin
binding.undo.setOnClickListener { binding.signature.undo() }
binding.clear.setOnClickListener { binding.signature.clear() }
lifecycleScope.launch(Dispatchers.IO) {
    contentResolver.openOutputStream(uri)?.use { stream ->
        withContext(Dispatchers.Main) {
            binding.signature.exportPng(stream, scale = 2f, backgroundColor = Color.WHITE)
        }
    }
}
```

上例压缩发生在主线程，仅适合小图。生产实现应在主线程生成矢量快照，后台创建 Bitmap、渲染并压缩。

```kotlin
@Composable
fun SignatureHost(modifier: Modifier = Modifier, onViewReady: (SignaturePadView) -> Unit) {
    AndroidView(
        modifier = modifier,
        factory = { context -> SignaturePadView(context).also(onViewReady) }
    )
}
```

Compose 层可把撤销/保存按钮放在外部并持有受控 controller；不要在重组时重复 `clear()` 或反复注册监听。

## 无障碍

> **无障碍提示**：签名本身是视觉/运动任务，无法靠 TalkBack 等价完成。必须提供替代业务路径，例如“键入姓名并确认”或服务端认可的电子同意方式；自定义撤销、清空动作只是辅助，不能宣称完全可访问。

清空属于破坏性操作，外部按钮应有明确标签，必要时二次确认。颜色和线宽工具也应由标准可访问控件承担。

## 状态与数据安全

签名可能属于敏感个人数据：

- 默认不要写入公共相册、日志或分析事件。
- 临时文件放 app 私有目录，完成上传后按策略删除。
- `SavedState` 经过 Binder 传递，不能无限增长；示例用 2000 段上限。
- 旋转必须保留完整签名时，把矢量模型置于 ViewModel，并由 View 只渲染快照。
- redo 栈是编辑会话状态，是否跨旋转保留取决于产品需求；示例不保留。

## 性能与常见陷阱

> **性能提示**：MOVE 只刷新新段包围盒。历史笔画很多时，仍会在每次 `onDraw()` 重画全部内容；可把已提交笔画缓存到离屏 Bitmap，当前笔画保持矢量，撤销时重建缓存。

- 忽略 historical samples：快速划线出现折角和长直线。
- 每个采样创建 Path：造成 GC；本文仅保存数值段，绘制 Path 复用。
- 固定线宽：能工作但缺少自然笔感；滤波过强又会延迟。
- 直接持有 Activity listener：容易泄漏；detach 清理或由宿主显式解绑。
- 每次 MOVE 回调业务层：造成数据库/Compose 状态风暴；只在笔画结束通知。
- 导出调用 `view.draw()` 会连背景、辅助线和选框一起导出；独立 renderer 更可控。

## 测试策略

### 算法单元测试

- 同速不同压力时，压力高的目标宽度更大。
- 同压不同速度时，快速线更细。
- dt 为 0、不规范压力值不会产生 NaN 或越界宽度。
- 中点段连续：上一段 end 等于下一段 start。

### Robolectric/仪器化

```kotlin
@Test fun undoThenNewStrokeClearsRedo() {
    // 使用 MotionEvent.obtain 注入两条笔画。
    drawStroke(view, 10f, 10f, 100f, 100f)
    assertThat(view.undo()).isTrue()
    drawStroke(view, 20f, 20f, 80f, 80f)
    assertThat(view.canRedo()).isFalse()
}
```

- 注入包含 history 的 MotionEvent，断言段数包含历史点。
- ACTION_CANCEL 后 active pointer 被释放，父级可再次拦截。
- 导出 PNG 解码后尺寸、透明背景和非空像素正确。
- 大笔画基准：连续 10 秒采样，检查帧时间、分配和状态大小。
- 截图覆盖细慢线、粗压感线、多次撤销后的结果。

## 实践检查清单

- [ ] 消费历史采样并按 active pointer 过滤
- [ ] 轨迹和线宽都做平滑且有边界
- [ ] 撤销/重做遵循命令语义
- [ ] 导出与屏幕渲染共享 renderer
- [ ] 大状态不会进入 Binder
- [ ] 有无障碍替代签署路径和隐私策略

## 扩展练习

1. 生成可变宽左右轮廓 Path，比较平均线宽段的接缝。
2. 增加橡皮擦，选择“删除整条笔画”或基于路径布尔运算。
3. 将已提交笔画缓存为 Bitmap，并正确处理 undo 重建。
4. 使用 `MotionEvent.getToolType()` 区分手写笔、手指与橡皮端。
5. 导出裁剪到签名包围盒并保留可配置边距。

## 小结

签名板把事件处理推进到高频数据管线：完整采样、滤波、平滑、局部失效和可重放模型缺一不可。把渲染与 View 生命周期分离后，撤销、导出和测试都会显著清晰。

## 延伸阅读

- [MotionEvent](https://developer.android.com/reference/android/view/MotionEvent)
- [触笔输入](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input)
- [减少过度绘制](https://developer.android.com/topic/performance/rendering/overdraw)
