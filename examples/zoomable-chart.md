# 实战三：可缩放折线图——矩阵、双指缩放与视口约束

## 学习目标

本章构建 `ZoomableChartView`：数据坐标先映射到内容坐标，再由用户矩阵完成平移缩放。读者将掌握矩阵正反变换、焦点不动缩放、边界约束、手势仲裁、可见区裁剪和大数据性能策略。

## 需求与验收

- 绘制时间序列折线、网格和选中点；空数据与单点数据不崩溃。
- 单指平移、双指缩放、双击复位；缩放范围 `1x..8x`。
- 缩放期间手指焦点对应的数据点在屏幕上基本不动。
- 不能把图表无限拖离屏幕；缩放到 1x 时自动居中并禁止多余平移。
- 点击选择最近数据点，回调原始索引和值；变换后命中仍正确。
- 保存用户矩阵与选中索引；恢复后再次约束到新尺寸。
- TalkBack 可读摘要，键盘可左右切换选中点；大量点时避免逐点分配。

## 坐标系与架构

```text
Data space (x,y)
   | baseMatrix: data bounds -> padded content rect, invert Y
   v
Content space (pixels at 1x)
   | userMatrix: pan + scale around gesture focus
   v
View space (screen pixels)

MotionEvent -> ScaleGestureDetector ----+
            -> GestureDetector ---------+--> userMatrix -> constrain -> invalidate
                                                |
Draw: clip(content) -> concat(userMatrix) -> path in content space
Hit test: view point -> inverse(userMatrix) -> binary/nearest search
```

保持 `baseMatrix` 与 `userMatrix` 分离很关键：数据变化只重建基础路径，用户操作只修改用户矩阵。本文在绘制前先 `concat(userMatrix)`，而数据路径已被 `baseMatrix` 转成内容坐标。

## 关键算法

### 数据映射

数据边界为 `[minX,maxX] × [minY,maxY]`，内容矩形为 `C`：

```text
sx = C.width  / max(maxX-minX, epsilon)
sy = C.height / max(maxY-minY, epsilon)
px = C.left   + (x-minX) * sx
py = C.bottom - (y-minY) * sy     // View 的 y 轴向下
```

单点或常量序列需要人为扩展退化范围，不能除以 0。

### 焦点缩放与约束

`Matrix.postScale(scale, scale, focusX, focusY)` 让焦点保持稳定。约束不要读内部矩阵平移量猜边界，而应把内容矩形映射后检查四边：若映射宽小于视口则居中，否则补齐露出的边。

### 命中测试

把触点经 `userMatrix.invert()` 转回 1x 内容空间，再根据 x 比例估算索引。等间隔数据可 O(1) 估算；不等间隔数据应用二分查找原始 x。

## Kotlin 实现：模型和基础绘制

```kotlin
package com.example.widgets

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.graphics.RectF
import android.os.Bundle
import android.os.Parcel
import android.os.Parcelable
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.view.GestureDetectorCompat
import androidx.core.view.ViewCompat
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToInt

class ZoomableChartView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    data class Entry(val x: Float, val y: Float)
    fun interface OnSelectionChangedListener {
        fun onSelectionChanged(index: Int, entry: Entry)
    }

    private val density = resources.displayMetrics.density
    private val contentRect = RectF()
    private val mappedRect = RectF()
    private val dataPath = Path()
    private val baseMatrix = Matrix()
    private val userMatrix = Matrix()
    private val inverse = Matrix()
    private val matrixValues = FloatArray(9)
    private val pointBuffer = FloatArray(2)

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(45, 0, 0, 0); strokeWidth = density
    }
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(3, 169, 244); strokeWidth = 2f * density
        style = Paint.Style.STROKE; strokeJoin = Paint.Join.ROUND
    }
    private val pointPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 87, 34); style = Paint.Style.FILL
    }

    private var entries: List<Entry> = emptyList()
    private var selectedIndex = -1
    private var minScale = 1f
    private var maxScale = 8f
    private var pendingRestore: FloatArray? = null
    var selectionListener: OnSelectionChangedListener? = null

    private val scaleDetector = ScaleGestureDetector(context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val current = currentScale()
                val target = (current * detector.scaleFactor).coerceIn(minScale, maxScale)
                val factor = target / current
                userMatrix.postScale(factor, factor, detector.focusX, detector.focusY)
                constrainMatrix()
                invalidate()
                return true
            }
        })

    private val gestureDetector = GestureDetectorCompat(context,
        object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent): Boolean = true

            override fun onScroll(
                e1: MotionEvent?, e2: MotionEvent,
                distanceX: Float, distanceY: Float
            ): Boolean {
                if (scaleDetector.isInProgress) return false
                // 等手势检测器确认滚动后再阻止父级拦截，保留父容器接管 DOWN 的机会。
                parent.requestDisallowInterceptTouchEvent(true)
                userMatrix.postTranslate(-distanceX, -distanceY)
                constrainMatrix()
                invalidate()
                return true
            }

            override fun onSingleTapUp(e: MotionEvent): Boolean {
                selectNearest(e.x, e.y)
                return performClick()
            }

            override fun onDoubleTap(e: MotionEvent): Boolean {
                resetViewport()
                return true
            }
        })

    init {
        isFocusable = true
        isClickable = true
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
    }

    fun submitData(newEntries: List<Entry>) {
        require(newEntries.all { it.x.isFinite() && it.y.isFinite() }) {
            "entries must be finite"
        }
        require(newEntries.zipWithNext().all { (a, b) -> a.x <= b.x }) {
            "entries must be sorted by x"
        }
        entries = newEntries.toList()
        selectedIndex = selectedIndex.coerceIn(-1, entries.lastIndex)
        rebuildDataPath()
        updateA11ySummary()
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        contentRect.set(
            paddingLeft + 32f * density,
            paddingTop + 16f * density,
            w - paddingRight - 12f * density,
            h - paddingBottom - 28f * density
        )
        rebuildDataPath()
        pendingRestore?.let {
            userMatrix.setValues(it)
            pendingRestore = null
        }
        constrainMatrix()
    }

    private fun rebuildDataPath() {
        dataPath.reset()
        if (entries.isEmpty() || contentRect.isEmpty) return

        var minX = entries.first().x
        var maxX = entries.last().x
        var minY = entries.minOf { it.y }
        var maxY = entries.maxOf { it.y }
        if (abs(maxX - minX) < 1e-6f) { minX -= 0.5f; maxX += 0.5f }
        if (abs(maxY - minY) < 1e-6f) { minY -= 0.5f; maxY += 0.5f }

        val sx = contentRect.width() / (maxX - minX)
        val sy = contentRect.height() / (maxY - minY)
        baseMatrix.reset()
        baseMatrix.setValues(floatArrayOf(
            sx, 0f, contentRect.left - minX * sx,
            0f, -sy, contentRect.bottom + minY * sy,
            0f, 0f, 1f
        ))
        entries.forEachIndexed { index, e ->
            pointBuffer[0] = e.x; pointBuffer[1] = e.y
            baseMatrix.mapPoints(pointBuffer)
            if (index == 0) dataPath.moveTo(pointBuffer[0], pointBuffer[1])
            else dataPath.lineTo(pointBuffer[0], pointBuffer[1])
        }
    }
```

## Kotlin 实现：绘制、交互和约束

```kotlin
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        drawGrid(canvas)
        canvas.save()
        canvas.clipRect(contentRect)
        canvas.concat(userMatrix)
        canvas.drawPath(dataPath, linePaint)
        if (selectedIndex in entries.indices) {
            pointBuffer[0] = entries[selectedIndex].x
            pointBuffer[1] = entries[selectedIndex].y
            baseMatrix.mapPoints(pointBuffer)
            canvas.drawCircle(pointBuffer[0], pointBuffer[1], 5f * density, pointPaint)
        }
        canvas.restore()
    }

    private fun drawGrid(canvas: Canvas) {
        if (contentRect.isEmpty) return
        for (i in 0..4) {
            val x = contentRect.left + contentRect.width() * i / 4f
            val y = contentRect.top + contentRect.height() * i / 4f
            canvas.drawLine(x, contentRect.top, x, contentRect.bottom, gridPaint)
            canvas.drawLine(contentRect.left, y, contentRect.right, y, gridPaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val scaled = scaleDetector.onTouchEvent(event)
        val gestured = gestureDetector.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> parent.requestDisallowInterceptTouchEvent(false)
            MotionEvent.ACTION_POINTER_DOWN -> parent.requestDisallowInterceptTouchEvent(true)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL ->
                parent.requestDisallowInterceptTouchEvent(false)
        }
        return scaled || gestured || super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun currentScale(): Float {
        userMatrix.getValues(matrixValues)
        return matrixValues[Matrix.MSCALE_X]
    }

    private fun constrainMatrix() {
        if (contentRect.isEmpty) return
        val scale = currentScale().coerceIn(minScale, maxScale)
        if (abs(scale - currentScale()) > 1e-4f) {
            val factor = scale / currentScale()
            userMatrix.postScale(factor, factor, contentRect.centerX(), contentRect.centerY())
        }
        mappedRect.set(contentRect)
        userMatrix.mapRect(mappedRect)
        var dx = 0f
        var dy = 0f
        dx = if (mappedRect.width() <= contentRect.width()) {
            contentRect.centerX() - mappedRect.centerX()
        } else when {
            mappedRect.left > contentRect.left -> contentRect.left - mappedRect.left
            mappedRect.right < contentRect.right -> contentRect.right - mappedRect.right
            else -> 0f
        }
        dy = if (mappedRect.height() <= contentRect.height()) {
            contentRect.centerY() - mappedRect.centerY()
        } else when {
            mappedRect.top > contentRect.top -> contentRect.top - mappedRect.top
            mappedRect.bottom < contentRect.bottom -> contentRect.bottom - mappedRect.bottom
            else -> 0f
        }
        userMatrix.postTranslate(dx, dy)
    }

    private fun selectNearest(viewX: Float, viewY: Float) {
        if (entries.isEmpty() || !contentRect.contains(viewX, viewY) ||
            !userMatrix.invert(inverse)
        ) return
        pointBuffer[0] = viewX; pointBuffer[1] = viewY
        inverse.mapPoints(pointBuffer)
        val contentX = pointBuffer[0]

        // 转回数据坐标后对有序 x 二分搜索。
        if (!baseMatrix.invert(inverse)) return
        pointBuffer[0] = contentX; pointBuffer[1] = contentRect.centerY()
        inverse.mapPoints(pointBuffer)
        val dataX = pointBuffer[0]
        var low = 0; var high = entries.lastIndex
        while (low < high) {
            val mid = (low + high) ushr 1
            if (entries[mid].x < dataX) low = mid + 1 else high = mid
        }
        val right = low
        val left = (right - 1).coerceAtLeast(0)
        val index = if (abs(entries[left].x - dataX) <= abs(entries[right].x - dataX)) left else right
        setSelectedIndex(index, fromUser = true)
    }

    private fun setSelectedIndex(index: Int, fromUser: Boolean) {
        val next = index.coerceIn(-1, entries.lastIndex)
        if (selectedIndex == next) return
        selectedIndex = next
        updateA11ySummary()
        invalidate()
        if (fromUser && next >= 0) selectionListener?.onSelectionChanged(next, entries[next])
    }

    fun resetViewport() {
        userMatrix.reset()
        constrainMatrix()
        invalidate()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        val delta = when (keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT -> -1
            KeyEvent.KEYCODE_DPAD_RIGHT -> 1
            else -> return super.onKeyDown(keyCode, event)
        }
        if (entries.isEmpty()) return true
        val start = if (selectedIndex == -1) {
            if (delta > 0) -1 else entries.size
        } else selectedIndex
        setSelectedIndex(start + delta, fromUser = true)
        return true
    }
```

> **注意**：这里复用了同一个 `inverse` 矩阵分两阶段反变换，顺序是用户空间再基础空间。若并发预计算路径，矩阵和缓冲数组必须线程隔离。

## Kotlin 实现：无障碍与状态

```kotlin
    private fun updateA11ySummary() {
        val text = if (selectedIndex in entries.indices) {
            val e = entries[selectedIndex]
            context.getString(R.string.chart_selected, selectedIndex + 1, entries.size, e.y)
        } else {
            context.getString(R.string.chart_summary, entries.size)
        }
        ViewCompat.setStateDescription(this, text)
    }

    override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        info.className = ZoomableChartView::class.java.name
        info.contentDescription = context.getString(R.string.chart_content_description)
        if (entries.isNotEmpty()) {
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD)
        }
    }

    override fun performAccessibilityAction(action: Int, arguments: Bundle?): Boolean {
        val delta = when (action) {
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD -> 1
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD -> -1
            else -> return super.performAccessibilityAction(action, arguments)
        }
        if (entries.isEmpty()) return false
        val start = if (selectedIndex == -1) {
            if (delta > 0) -1 else entries.size
        } else selectedIndex
        setSelectedIndex(start + delta, fromUser = true)
        return true
    }

    override fun onSaveInstanceState(): Parcelable = SavedState(super.onSaveInstanceState()).also {
        userMatrix.getValues(it.matrix)
        it.selectedIndex = selectedIndex
    }

    override fun onRestoreInstanceState(state: Parcelable?) {
        if (state !is SavedState) { super.onRestoreInstanceState(state); return }
        super.onRestoreInstanceState(state.superState)
        selectedIndex = state.selectedIndex
        if (width == 0 || height == 0) pendingRestore = state.matrix.copyOf()
        else {
            userMatrix.setValues(state.matrix)
            constrainMatrix()
        }
        updateA11ySummary()
        invalidate()
    }

    private class SavedState : BaseSavedState {
        var matrix = FloatArray(9).also { Matrix().getValues(it) }
        var selectedIndex = -1
        constructor(superState: Parcelable?) : super(superState)
        private constructor(p: Parcel) : super(p) {
            p.readFloatArray(matrix)
            selectedIndex = p.readInt()
        }
        override fun writeToParcel(out: Parcel, flags: Int) {
            super.writeToParcel(out, flags)
            out.writeFloatArray(matrix)
            out.writeInt(selectedIndex)
        }
        companion object CREATOR : Parcelable.Creator<SavedState> {
            override fun createFromParcel(p: Parcel) = SavedState(p)
            override fun newArray(size: Int): Array<SavedState?> = arrayOfNulls(size)
        }
    }
}
```

## XML 与 Compose 使用

```xml
<com.example.widgets.ZoomableChartView
    android:id="@+id/chart"
    android:layout_width="match_parent"
    android:layout_height="280dp"
    android:padding="8dp" />
```

```kotlin
binding.chart.submitData(samples.mapIndexed { i, y ->
    ZoomableChartView.Entry(i.toFloat(), y)
})
```

```kotlin
@Composable
fun ChartHost(entries: List<ZoomableChartView.Entry>, modifier: Modifier = Modifier) {
    AndroidView(
        modifier = modifier,
        factory = { ZoomableChartView(it) },
        update = { view -> view.submitData(entries) }
    )
}
```

若数据流每次发出内容相同的新 List，`update` 会重建路径。包装层应使用稳定、去重后的模型，或让 `submitData()` 比较版本号。

## 无障碍

> **无障碍提示**：不能要求盲人“探索曲线形状”。提供图表摘要、当前点数值、键盘/调整动作；业务重要时再提供“查看数据表”按钮。这往往比为上千个点创建虚拟节点更实用。

文字轴标签需支持足够对比度和字体缩放。若图表仅装饰，应设为 `IMPORTANT_FOR_ACCESSIBILITY_NO`，并由附近文本给出结论。

## 状态保存

矩阵像素平移依赖旧尺寸，恢复到新方向后必须再次 `constrainMatrix()`。更稳健的产品实现可保存“数据视口”——可见 x/y 范围——而不是像素矩阵，这样跨尺寸语义更稳定。数据本身通常来自 ViewModel/仓库，不要塞入 `SavedState`。

## 性能与生产策略

> **性能提示**：路径在数据或尺寸变化时重建，而非每帧重建。绘制前裁剪内容区。10 万点不能直接逐点连线，应按屏幕 x 像素桶做 min/max 降采样，在后台线程生成不可变结果，再切回主线程提交。

- 不要在 `onDraw()` 中调用 `entries.minOf`。
- Path 太大时可按可见数据窗口构建；平移跨阈值再更新缓存。
- 网格和静态轴可缓存到 Picture/RenderNode，但先用基准测试确认收益。
- `Matrix` 拼接顺序错误会导致平移随缩放倍率变化；用已知点做单元测试。
- 折线开启阴影可能触发昂贵离屏绘制，不要把软件层当默认修复。

## 测试策略

### 数学单元测试

把约束和坐标变换抽成纯 Kotlin 类，验证：

- 数据最小/最大值映射到内容矩形对应边。
- 以 `(fx, fy)` 缩放前后的反算数据点相等，误差小于 epsilon。
- 任意平移后映射矩形不会完全离开内容区。
- 常量数据与单点数据不产生 NaN。

### 仪器化与性能

```kotlin
@Test fun doubleTapResetsViewport() {
    onView(withId(R.id.chart)).perform(doubleClick())
    // 暴露仅供测试的 viewport 快照，断言 scale == 1f。
}
```

- 多点注入测试焦点缩放；截图对比 1x、4x、边界位置。
- 键盘左右键和无障碍滚动动作更新选中描述。
- Macrobenchmark 分别提交 1k、10k、100k 点，记录路径构建与帧时间。
- 开启“显示布局边界”，确认 clip 不越过轴标签区域。

## 实践检查清单

- [ ] 数据、内容、View 三个坐标系明确
- [ ] 每次修改矩阵后执行约束
- [ ] 命中测试使用逆矩阵
- [ ] 退化数据范围无除零
- [ ] 大数据有降采样与异步策略
- [ ] 有非视觉的数据访问路径

## 扩展练习

1. 添加惯性滚动：`VelocityTracker + OverScroller`，并在 detach 时终止。
2. 保存数据视口而非矩阵，验证横竖屏恢复。
3. 实现按像素桶的 min/max 降采样并做 benchmark。
4. 增加两条曲线、图例与十字准星，处理命中优先级。

## 小结

矩阵型控件的核心不是记住 API，而是划清坐标空间。正向变换用于绘制，逆向变换用于命中；每次变换后统一约束。这个模型会直接延伸到最后的图形编辑器。

## 延伸阅读

- [Canvas 与 Drawable](https://developer.android.com/develop/ui/views/graphics/drawables)
- [多点触控](https://developer.android.com/develop/ui/views/touch-and-input/gestures/multi)
- [优化自定义 View](https://developer.android.com/develop/ui/views/layout/custom-views/optimizing-view)
