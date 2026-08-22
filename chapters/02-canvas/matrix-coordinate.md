# Matrix 与坐标系统

## 学习目标

- 用齐次矩阵描述平移、缩放与旋转。
- 区分 `pre*`、`post*` 的组合顺序，而不是靠直觉猜。
- 用逆矩阵把触摸点映射到内容坐标完成命中。

## 坐标链

复杂控件至少有三套坐标：屏幕/父容器坐标、View 本地坐标、内容坐标。绘制使用正向矩阵，命中使用同一矩阵的逆。

```text
content point pc ── M ──► view point pv ── window transform ──► screen
      ▲                         │
      └──────── M⁻¹ ◄───────────┘ touch event (View-local)
```

二维仿射矩阵用齐次坐标表示：

```text
┌ x' ┐   ┌ a  c  tₓ ┐ ┌ x ┐
│ y' │ = │ b  d  tᵧ │ │ y │
└ 1  ┘   └ 0  0  1  ┘ └ 1 ┘
```

若 `det=ad-bc=0`，矩阵不可逆，例如某一轴缩放到 0。`Matrix.invert()` 会返回 `false`，命中逻辑必须处理。

## 前乘与后乘

Android `Matrix` 文档定义：

- `postConcat(B)`：`M' = B × M`
- `preConcat(B)`：`M' = M × B`

对列向量，最靠近点的矩阵先作用。不要仅从方法名猜视觉顺序，应把目标关系写出来。例如希望内容先缩放 `S`，再平移 `T`，目标是 `p'=TSp`。可以从单位矩阵开始 `setScale()` 后 `postTranslate()`，得到 `M'=T×S`。

```text
p ─ S ─► scaled ─ T ─► screen
matrix product: T × S × p
(read right to left)
```

绕枢轴 `(px,py)` 缩放：

```text
M = T(pₓ, pᵧ) · S(sₓ, sᵧ) · T(-pₓ, -pᵧ)
```

## 完整 Kotlin 示例：可变换内容与逆矩阵命中

```kotlin
package com.example.canvas

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View

class TransformHitView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val contentToView = Matrix()
    private val viewToContent = Matrix()
    private val node = RectF(0f, 0f, 240f, 140f)
    private val touchPoint = FloatArray(2)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var selected = false
    private var scale = 1f
    private var offsetX = 80f
    private var offsetY = 120f

    private fun rebuildMatrix(): Boolean {
        contentToView.reset()
        contentToView.setScale(scale, scale)
        contentToView.postTranslate(offsetX, offsetY) // M = T × S
        return contentToView.invert(viewToContent)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        rebuildMatrix()
        val checkpoint = canvas.save()
        try {
            canvas.concat(contentToView)
            paint.color = if (selected) Color.rgb(255, 193, 7) else Color.rgb(63, 81, 181)
            paint.style = Paint.Style.FILL
            canvas.drawRoundRect(node, 18f, 18f, paint)
            paint.color = Color.WHITE
            paint.textSize = 32f
            canvas.drawText("content", 36f, 82f, paint)
        } finally {
            canvas.restoreToCount(checkpoint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked != MotionEvent.ACTION_DOWN) return true
        if (!rebuildMatrix()) return false
        touchPoint[0] = event.x
        touchPoint[1] = event.y
        viewToContent.mapPoints(touchPoint)
        selected = node.contains(touchPoint[0], touchPoint[1])
        invalidate()
        return true
    }

    fun setViewport(newScale: Float, x: Float, y: Float) {
        scale = newScale.coerceIn(0.1f, 8f)
        offsetX = x
        offsetY = y
        invalidate()
    }
}
```

`MotionEvent.getX()/getY()` 已是 View 本地坐标，不应先减 `left/top`。若内容还经过其他嵌套变换，应明确维护完整的 content-to-view 矩阵。

## 矩形映射不是旋转矩形

`mapRect()` 返回变换后四角的轴对齐包围盒（AABB），旋转后会比真实几何大：

```text
+--------- AABB --------+
|       / rotated /     |
|      /  content /     |
+-----------------------+
```

粗筛可用 AABB，精确命中应把触点逆变换到内容坐标，再对原始几何判断。这样也避免处理旋转后的多边形。

> **性能提示**：手势移动时复用 `Matrix` 和点数组。只有矩阵变化后才重新求逆，并缓存 `invert()` 结果。

## 常见陷阱

1. 混淆 `pre`/`post`，缩放后平移量也被缩放。
2. 绘制用了 Matrix，点击仍在 View 坐标直接判断。
3. 忽略不可逆矩阵，继续使用上一次成功的逆矩阵。
4. 用旋转后的 AABB 做精确命中，角落误触。
5. 同时变换 Canvas 和手工变换几何，产生双重变换。
6. 直接读取 `Matrix.values` 并假设只有缩放平移，忽略旋转/错切。

## 实践检查清单

- [ ] 写出 `p_view=M p_content`，再决定组合顺序。
- [ ] 绘制与命中共享同一个正向矩阵来源。
- [ ] 检查 `invert()` 返回值，不复用失效逆矩阵。
- [ ] 精确命中在内容坐标完成。
- [ ] 用已知点（原点、单位轴、枢轴）验证矩阵。

## 小结

Matrix 的可靠用法不是背方法名，而是先写坐标链和矩阵乘积。正向变换负责显示，逆变换负责交互，两者必须来自同一状态。

## 延伸阅读

- [Matrix API](https://developer.android.com/reference/android/graphics/Matrix)
- [Canvas.concat](https://developer.android.com/reference/android/graphics/Canvas#concat%28android.graphics.Matrix%29)
- [MotionEvent 坐标](https://developer.android.com/reference/android/view/MotionEvent)
