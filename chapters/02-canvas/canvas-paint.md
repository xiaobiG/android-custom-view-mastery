# Canvas、Paint 与绘图状态

## 学习目标

- 区分 `Canvas` 的变换/裁剪状态与 `Paint` 的绘制参数。
- 用 `save()`/`restoreToCount()` 建立可证明配对的局部坐标系。
- 理解密度、像素对齐、描边边界及抗锯齿的成本。

## 为什么先管理状态

自定义绘制最难排查的问题通常不是“不会画”，而是前一次绘制遗留了状态。`Canvas` 保存的是矩阵和裁剪；`Paint` 是独立、可变的参数对象，不随 `Canvas.save()` 保存。

```text
Canvas state stack                  Paint (not in stack)
┌──────────────────────┐            color / style / strokeWidth
│ matrix M2, clip C2   │ <- current shader / alpha / typeface
├──────────────────────┤
│ matrix M1, clip C1   │
├──────────────────────┤
│ matrix I,  clip view │
└──────────────────────┘
       save ↑  ↓ restore
```

## 核心机制

绘制点 `p=(x,y,1)^T` 会先经当前矩阵变为设备坐标：

```text
p_d = M_c · p
```

随后与当前裁剪区域相交，最后使用 `Paint` 栅格化。`Paint.Style.STROKE` 以几何路径为中心向两侧各扩展 `strokeWidth/2`。因此在左边界 `x=0` 画 4 px 描边，有 2 px 落到 View 外。

常用状态归属：

| 状态 | 所属对象 | `Canvas.save()` 是否保存 |
|---|---|---|
| translate/scale/rotate/concat | Canvas | 是 |
| clipRect/clipPath | Canvas | 是 |
| color/style/strokeWidth/alpha | Paint | 否 |
| shader/colorFilter/blendMode | Paint | 否 |

`clipRect()` 在现代 API 上只应做收窄裁剪。若要临时裁剪，保存后裁剪，再恢复；不要试图“反向扩大”裁剪。

## 完整 Kotlin 示例：状态隔离的刻度盘

```kotlin
package com.example.canvas

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

class DialView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val density = resources.displayMetrics.density
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeCap = Paint.Cap.ROUND
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f
        val cy = height / 2f
        val radius = min(width, height) * 0.36f

        paint.reset()
        paint.isAntiAlias = true
        paint.color = Color.rgb(45, 52, 64)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 2f * density
        canvas.drawCircle(cx, cy, radius, paint)

        val checkpoint = canvas.save()
        try {
            canvas.translate(cx, cy)
            paint.color = Color.rgb(255, 171, 64)
            paint.strokeWidth = 3f * density
            paint.strokeCap = Paint.Cap.ROUND
            repeat(12) { index ->
                val longTick = index % 3 == 0
                val inner = radius - (if (longTick) 16f else 9f) * density
                canvas.drawLine(0f, -inner, 0f, -radius, paint)
                canvas.rotate(30f)
            }
        } finally {
            canvas.restoreToCount(checkpoint)
        }

        paint.style = Paint.Style.FILL
        paint.color = Color.WHITE
        canvas.drawCircle(cx, cy, 4f * density, paint)
    }
}
```

`save()` 返回的计数可交给 `restoreToCount()`，即使循环以后增加嵌套保存，也能恢复到入口状态。`try/finally` 让提前返回或异常不会污染后续绘制。

## 像素与密度推导

`dp` 到像素为 `px=dp×density`。若 1 px 的水平线使用 `STROKE`，中心位于整数 y 时覆盖 `[y-0.5,y+0.5]`，可能落在两行像素间；在无缩放且确需锐利 1 px 线时可将中心移至 `y+0.5f`。但高密度下优先按 dp 定义视觉粗细，不要到处硬编码半像素。

> **性能提示**：在构造阶段创建 `Paint`，不要在 `onDraw()` 中分配对象。`reset()` 会恢复默认值，包括关闭抗锯齿，之后要显式重设。

> **注意**：`canvas.width/height` 是当前绘制目标尺寸；View 内容区还应扣除 `padding`。变换 Canvas 不会改变 View 的点击坐标。

## 常见陷阱

1. 以为 `restore()` 会恢复 `Paint`，导致颜色、Shader 或 alpha 串到下一段。
2. `save()` 与 `restore()` 分支不配对，兄弟元素继承旋转或裁剪。
3. 在每帧创建 `Paint`、集合或装箱对象，引发 GC 抖动。
4. 忘记描边向路径两侧扩展，边缘被裁掉。
5. 使用 `Paint()` 后误以为默认已抗锯齿；应传 `ANTI_ALIAS_FLAG` 或设置 `isAntiAlias`。
6. 把 `setLayerType()` 当作普通优化开关；它改变合成策略，应基于测量和具体效果使用。

## 实践检查清单

- [ ] 每个局部变换/裁剪都有 `save` 与 `restoreToCount`。
- [ ] 每段绘制显式设置依赖的 Paint 状态。
- [ ] `onDraw()` 无不必要分配，尺寸计算在尺寸变化时缓存。
- [ ] 内容考虑 padding、描边半宽和密度。
- [ ] 在不同 density、硬件加速开关下验证视觉结果。

## 小结

Canvas 是带栈的坐标与裁剪上下文，Paint 是栈外的可变绘制参数。把二者状态边界写清楚，比任何“神奇修复”都更可靠。

## 延伸阅读

- [Canvas API](https://developer.android.com/reference/android/graphics/Canvas)
- [Paint API](https://developer.android.com/reference/android/graphics/Paint)
- [自定义绘制](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing)
