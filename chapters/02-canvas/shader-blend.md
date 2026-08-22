# Shader、混合与离屏图层

## 学习目标

- 理解 Shader 生成源颜色、BlendMode 组合源与目标的顺序。
- 正确配置渐变和 BitmapShader 的局部矩阵。
- 只在语义需要时使用 `saveLayer()`，并控制离屏范围。

## 像素管线

Shader 决定当前绘制操作每个位置的源颜色（source）；混合模式决定源颜色如何与已有目标像素（destination）组合。

```text
geometry + matrix
       │
       ▼
Shader → source S ─┐
                   ├─ BlendMode(S, D) → output
existing pixels D ─┘
       saveLayer creates a temporary D inside bounds
```

普通 SRC_OVER 使用预乘 alpha 可写为：

```text
Cₒ = Cₛ + (1-αₛ)C_d
αₒ = αₛ + (1-αₛ)α_d
```

`DST_IN` 保留“目标与源 alpha 重叠”的目标部分，常用于遮罩；它对源/目标顺序敏感。

## Shader 坐标

`LinearGradient(x0,y0,x1,y1,...)` 的端点位于创建时的局部坐标。Canvas 当前矩阵随后一起影响它。`BitmapShader.setLocalMatrix()` 是 Shader 自己的附加映射，适合把位图缩放/平移到目标几何，不必改动整个 Canvas。

## 完整 Kotlin 示例：圆形图片遮罩与渐变描边

```kotlin
package com.example.canvas

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.util.AttributeSet
import android.view.View
import com.example.R
import kotlin.math.max
import kotlin.math.min

class ShaderAvatarView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val bitmap: Bitmap = BitmapFactory.decodeResource(resources, R.drawable.avatar)
    private val bitmapShader = BitmapShader(bitmap, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP)
    private val shaderMatrix = Matrix()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val bounds = RectF()
    private var ringShader: LinearGradient? = null

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        val size = min(w - paddingLeft - paddingRight, h - paddingTop - paddingBottom).toFloat()
        val left = paddingLeft + (w - paddingLeft - paddingRight - size) / 2f
        val top = paddingTop + (h - paddingTop - paddingBottom - size) / 2f
        bounds.set(left, top, left + size, top + size)

        val s = max(size / bitmap.width, size / bitmap.height)
        val dx = bounds.left + (size - bitmap.width * s) / 2f
        val dy = bounds.top + (size - bitmap.height * s) / 2f
        shaderMatrix.setScale(s, s)
        shaderMatrix.postTranslate(dx, dy)
        bitmapShader.setLocalMatrix(shaderMatrix)

        ringShader = LinearGradient(
            bounds.left, bounds.top, bounds.right, bounds.bottom,
            intArrayOf(Color.CYAN, Color.MAGENTA, Color.YELLOW),
            null, Shader.TileMode.CLAMP
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val inset = 6f * resources.displayMetrics.density
        paint.style = Paint.Style.FILL
        paint.shader = bitmapShader
        canvas.drawCircle(bounds.centerX(), bounds.centerY(), bounds.width() / 2f - inset, paint)

        paint.shader = ringShader
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = inset
        canvas.drawCircle(bounds.centerX(), bounds.centerY(), bounds.width() / 2f - inset / 2f, paint)
        paint.shader = null
    }
}
```

该实现直接用 `BitmapShader` 裁成圆形，不需要离屏层。只有必须让多次绘制先成为一个整体，再与背景混合时，才使用 `saveLayer(bounds, paint)`。

## saveLayer 的语义

```kotlin
val checkpoint = canvas.saveLayer(layerBounds, null)
try {
    canvas.drawPath(contentPath, contentPaint) // temporary destination
    maskPaint.blendMode = android.graphics.BlendMode.DST_IN // API 29+
    try {
        canvas.drawPath(maskPath, maskPaint)    // source mask
    } finally {
        maskPaint.blendMode = null
    }
} finally {
    canvas.restoreToCount(checkpoint)           // composite layer back
}
```

`saveLayer()` 创建与 bounds 相关的离屏缓冲，层内最初透明。恢复时将整个层合成回父目标。若没有图层，`DST_IN` 可能连同 View 背后已经存在的像素一起参与，结果超出预期。旧 API 可使用 `PorterDuffXfermode`，但应单独封装兼容路径并验证硬件加速行为。

> **性能提示**：离屏缓冲近似占用 `width×height×4` 字节（具体格式和实现可能不同），全屏层同时增加填充和内存带宽。bounds 应尽可能紧，静态内容优先预合成或使用 Shader。

> **注意**：`saveLayer()` 不是“开启硬件加速”，也不是通用修复。它改变混合边界，并可能昂贵。

## 常见陷阱

1. 忘记绘制后将 `paint.shader`/`blendMode` 清空，污染后续操作。
2. 颠倒 SRC/DST，`DST_IN` 得到完全相反结果。
3. 为简单圆形裁图使用全屏 `saveLayer()`，浪费带宽。
4. Shader 创建在错误坐标系，View 缩放后渐变位置异常。
5. 认为透明色等于“擦除”；SRC_OVER 下透明源通常不会清掉目标。
6. 混用 `clipPath`、BlendMode 与图层却不明确各自边界。

## 实践检查清单

- [ ] 明确每次混合中的 source 与 destination。
- [ ] Shader 坐标和局部矩阵在尺寸变化时更新。
- [ ] 可用 Shader/裁剪实现时不创建离屏层。
- [ ] 必须 `saveLayer` 时使用紧致 bounds，并成对恢复。
- [ ] 在目标最低 API、硬件加速与透明背景下实测。

## 小结

Shader 负责“生成什么颜色”，BlendMode 负责“怎样与已有像素结合”，saveLayer 负责“混合在哪个隔离边界发生”。先明确三者职责，才能同时获得正确性与性能。

## 延伸阅读

- [Shader API](https://developer.android.com/reference/android/graphics/Shader)
- [BlendMode API](https://developer.android.com/reference/android/graphics/BlendMode)
- [Canvas.saveLayer](https://developer.android.com/reference/android/graphics/Canvas#saveLayer%28android.graphics.RectF,android.graphics.Paint%29)
- [硬件加速](https://developer.android.com/develop/ui/views/graphics/hardware-accel)
