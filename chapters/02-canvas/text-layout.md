# 文字测量与排版

## 学习目标

- 区分基线、字形边界、advance 与 `FontMetrics`。
- 用 `StaticLayout` 完成多行、换行、对齐与省略。
- 正确处理字体缩放、RTL、复杂脚本和无障碍。

## 文字不是从左上角绘制

`drawText(text, x, baseline, paint)` 的 y 是基线（baseline），不是顶部。`FontMetrics` 的值相对基线，典型顺序如下：

```text
 top      ─────────────────────  most conservative top
 ascent   ────────┐  Á
 baseline ────────┼──Hello──────── y = 0
 descent  ────────┘       g
 bottom   ─────────────────────  most conservative bottom
          x → glyph shapes; advance may differ from visible bounds
```

常见关系：

```text
height = descent - ascent
```

将单行文字视觉上按字体度量垂直居中于 `centerY`：

```text
baseline = centerY - (ascent + descent) / 2
```

`measureText()` 返回水平方向 advance，不等于字形可见像素包围盒；斜体、组合音标可能伸出 advance。不要用字符个数乘平均宽度。

## 单行绘制与字体缩放

文字大小通常用 sp：`px=sp×scaledDensity`。当系统字体大小改变时 `scaledDensity` 会变化；自定义 View 应重新布局，而不是只重绘，因为行高和换行都可能变化。

## 完整 Kotlin 示例：RTL 感知的多行文本 View

```kotlin
package com.example.canvas

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.text.TextUtils
import android.util.AttributeSet
import android.view.View
import kotlin.math.ceil
import kotlin.math.max

class ParagraphView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val textPaint = TextPaint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(35, 39, 47)
        textSize = 16f * resources.displayMetrics.scaledDensity
    }
    private var layout: StaticLayout? = null
    var text: CharSequence = ""
        set(value) {
            field = value
            requestLayout()
            invalidate()
        }

    private fun makeLayout(contentWidth: Int): StaticLayout {
        val textDirection = if (layoutDirection == LAYOUT_DIRECTION_RTL) {
            android.text.TextDirectionHeuristics.FIRSTSTRONG_RTL
        } else {
            android.text.TextDirectionHeuristics.FIRSTSTRONG_LTR
        }
        return StaticLayout.Builder
            .obtain(text, 0, text.length, textPaint, max(0, contentWidth))
            .setAlignment(Layout.Alignment.ALIGN_NORMAL)
            .setIncludePad(false)
            .setLineSpacing(0f, 1.15f)
            .setMaxLines(4)
            .setEllipsize(TextUtils.TruncateAt.END)
            .setTextDirection(textDirection)
            .build()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredWidth = ceil(Layout.getDesiredWidth(text, textPaint).toDouble()).toInt() +
            paddingLeft + paddingRight
        val measuredW = resolveSize(desiredWidth, widthMeasureSpec)
        val contentW = max(0, measuredW - paddingLeft - paddingRight)
        layout = makeLayout(contentW)
        val desiredH = (layout?.height ?: 0) + paddingTop + paddingBottom
        setMeasuredDimension(measuredW, resolveSize(desiredH, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val checkpoint = canvas.save()
        try {
            canvas.translate(paddingLeft.toFloat(), paddingTop.toFloat())
            layout?.draw(canvas)
        } finally {
            canvas.restoreToCount(checkpoint)
        }
    }

    override fun onRtlPropertiesChanged(layoutDirection: Int) {
        super.onRtlPropertiesChanged(layoutDirection)
        requestLayout()
    }
}
```

示例最低需要 API 23 的 `StaticLayout.Builder`。`ALIGN_NORMAL` 是相对段落方向的起始侧，不等同于固定 LEFT；代码根据 View 的布局方向选择 `FIRSTSTRONG_LTR` 或 `FIRSTSTRONG_RTL`，仅影响没有强方向字符时的回退方向。产品若有明确 locale 或上下文，应选择匹配的 `TextDirectionHeuristic`。

## 复杂文本与布局边界

文本塑形（text shaping）会把 Unicode 序列映射为字形：连字、阿拉伯文连接、印度文字重排、emoji ZWJ 序列都说明“一个 code point 对应一个字形”不成立。切片、省略和光标移动应避免按 `Char` 任意截断。

`StaticLayout` 负责断行、双向文本和行度量。宽度变化、文字、字号、Typeface、locale、行距或 layout direction 变化都应重建。不要在 `onDraw()` 每帧构建布局。

> **无障碍提示**：Canvas 绘出的文字不会自动成为独立无障碍节点。若它只是 View 标签，应设置 `contentDescription` 或提供可访问文本；若多段内容可独立交互，应通过虚拟节点暴露语义与边界。

> **性能提示**：缓存 `StaticLayout`，仅在影响排版的输入变化时重建。长文本可在后台准备数据，但创建和使用与 View 状态相关的布局时要保证线程与字体资源安全。

## 常见陷阱

1. 把 y 当文字顶部，导致裁切或垂直偏移。
2. 用 `measureText()` 作为可见字形边界或多行高度。
3. 只 `invalidate()` 不 `requestLayout()`，字体变大后高度不变。
4. 用 LEFT/RIGHT 实现逻辑起止对齐，RTL 下反向。
5. 在 `onDraw()` 创建 `StaticLayout`，造成每帧分配。
6. 按 UTF-16 `Char` 截断 emoji/组合字符，显示破碎。

## 实践检查清单

- [ ] 单行垂直定位基于 `FontMetrics` 和基线。
- [ ] 多行文本由 `StaticLayout` 测量并绘制。
- [ ] 文字大小使用 scaledDensity，字体缩放后重新测量。
- [ ] RTL、混合方向文本、emoji 和长词均已测试。
- [ ] Canvas 文本提供对应无障碍语义。

## 小结

文字绘制的核心单位是基线、字形和段落，而不是左上角矩形和字符数。单行用 FontMetrics，多行交给 StaticLayout，并把方向、字体缩放和语义当作基本输入。

## 延伸阅读

- [Paint.FontMetrics](https://developer.android.com/reference/android/graphics/Paint.FontMetrics)
- [StaticLayout](https://developer.android.com/reference/android/text/StaticLayout)
- [TextPaint](https://developer.android.com/reference/android/text/TextPaint)
- [支持不同语言和文化](https://developer.android.com/training/basics/supporting-devices/languages)
