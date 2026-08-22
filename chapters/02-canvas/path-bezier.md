# Path 与贝塞尔曲线

## 学习目标

- 正确组织 `Path` 的轮廓、闭合和填充规则。
- 理解二次/三次贝塞尔曲线及控制点的含义。
- 使用 `PathMeasure` 按弧长取位置、切线和路径片段。

## Path 是几何，不是像素

`Path` 保存线段、曲线与轮廓（contour）。它本身没有颜色或线宽；同一路径可分别填充、描边或用于裁剪。

```text
moveTo A ─ lineTo B      separate contour
          ╲              moveTo E ── lineTo F
           ╲ quad/cubic
            C ─ close → A

Path geometry → Canvas matrix → clipping → Paint rasterization
```

`moveTo()` 开始新轮廓，`close()` 加入回到轮廓起点的线段。`reset()` 清空几何但不改变填充规则；`rewind()` 同样清空几何，并保留内部数据结构以便更快复用。

## 贝塞尔曲线推导

二次贝塞尔由起点 `P0`、控制点 `P1`、终点 `P2` 定义：

```text
B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂,  t ∈ [0,1]
```

三次贝塞尔再增加控制点 `P2` 与终点 `P3`：

```text
B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃
```

端点切线方向来自导数：三次曲线在 `t=0` 的切线平行 `P1-P0`，在 `t=1` 平行 `P3-P2`。控制点通常不在曲线上，它们“拉动”切线。

> **注意**：参数 `t` 不是弧长比例。`t=0.5` 一般不代表已经走过路径长度的一半；按距离动画应使用 `PathMeasure`。

## 完整 Kotlin 示例：沿曲线运动并绘制已走路径

```kotlin
package com.example.canvas

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PathMeasure
import android.util.AttributeSet
import android.view.View

class BezierProgressView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val path = Path()
    private val traveled = Path()
    private val measure = PathMeasure()
    private val position = FloatArray(2)
    private val tangent = FloatArray(2)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = resources.displayMetrics.density * 3f
        strokeCap = Paint.Cap.ROUND
    }

    var progress: Float = 0f
        set(value) {
            field = value.coerceIn(0f, 1f)
            invalidate()
        }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        val left = paddingLeft.toFloat()
        val right = (w - paddingRight).toFloat()
        val cy = h / 2f
        path.rewind()
        path.moveTo(left, cy)
        path.cubicTo(w * .25f, h * .1f, w * .75f, h * .9f, right, cy)
        measure.setPath(path, false)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        paint.color = Color.LTGRAY
        canvas.drawPath(path, paint)

        val distance = measure.length * progress
        traveled.rewind()
        measure.getSegment(0f, distance, traveled, true)
        paint.color = Color.rgb(33, 150, 243)
        canvas.drawPath(traveled, paint)

        if (measure.getPosTan(distance, position, tangent)) {
            paint.style = Paint.Style.FILL
            canvas.drawCircle(position[0], position[1], 7f * resources.displayMetrics.density, paint)
            paint.style = Paint.Style.STROKE
        }
    }
}
```

`getSegment(startD, stopD, dst, true)` 的最后参数会在目标 Path 中先移动到片段起点。多轮廓路径中，`length` 只对应当前轮廓；用 `nextContour()` 前进，并分别累计长度。

## 填充规则与命中

`WINDING` 按绕数判断内部；`EVEN_ODD` 从点向外作射线，与边界相交奇数次即内部。环形常写为两个圆并设 `EVEN_ODD`：

```text
ray ───────► | outer | inner | inner | outer |
intersections from point: odd = inside, even = outside
```

Android `Path` 没有 `contains(x, y)` API。常见做法是用 `Region.setPath(path, clip)` 将 Path 栅格化为整数区域后调用 `Region.contains()`；`clip` 必须覆盖待测路径，且这种方式受整数精度限制。需要浮点精度时，应针对具体几何实现命中或借助可靠的几何库。复杂命中还应考虑描边宽度，单纯测试填充区域并不等价于“点到描边中心线的距离小于半宽”。

## 常见陷阱

1. 连续 `moveTo()` 之间忘记 `close()`，填充可能自动闭合而描边不显示闭合边。
2. 每帧重建静态 Path；应在 `onSizeChanged()` 或数据变化时重建。
3. 把控制点当作必经点，错误调节曲线。
4. 用参数 `t` 做匀速动画，视觉速度忽快忽慢。
5. 忽略 `PathMeasure` 的多轮廓语义。
6. `getSegment()` 结果为空时仍假设可绘制；先限制距离并检查返回值。

> **性能提示**：复用 `Path`、`PathMeasure` 和 `FloatArray`。布尔运算 `Path.op()` 对复杂路径较贵，尽量在几何变化时执行而非每帧执行。

## 实践检查清单

- [ ] 明确每个轮廓的起点、闭合方式与填充规则。
- [ ] 动画按弧长而非直接按贝塞尔参数推进。
- [ ] 多轮廓遍历了 `nextContour()`。
- [ ] 静态 Path 在尺寸/数据变化时缓存。
- [ ] 命中区域包含视觉描边宽度和变换关系。

## 小结

Path 是可复用矢量几何；贝塞尔控制切线，PathMeasure 把几何转换为可用于动画的弧长信息。区分参数空间、距离空间和填充空间，是稳定实现的关键。

## 延伸阅读

- [Path API](https://developer.android.com/reference/android/graphics/Path)
- [PathMeasure API](https://developer.android.com/reference/android/graphics/PathMeasure)
- [Canvas.drawPath](https://developer.android.com/reference/android/graphics/Canvas#drawPath%28android.graphics.Path,android.graphics.Paint%29)
