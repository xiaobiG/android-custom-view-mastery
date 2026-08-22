# 尺寸、颜色与文字速查

## 1. 单位与密度

| 单位 | 含义 | 典型用途 | 注意 |
|---|---|---|---|
| px | 物理像素单位 | Canvas/API 最终参数 | 不直接写死视觉尺寸 |
| dp / dip | 密度无关像素 | 控件几何、间距、触摸目标 | `px = dp × density` |
| sp | 可缩放像素 | 用户可读文字 | `px = sp × scaledDensity` |
| pt/in/mm | 物理尺寸近似单位 | 打印或特殊场景 | 屏幕 UI 通常不用 |

```kotlin
val dm = resources.displayMetrics
val px = 12f * dm.density
val textPx = 16f * dm.scaledDensity
```

> **注意**：几何计算保留 `Float`；只在 API 需要 `Int` 时统一取整。不要用 `toInt()` 默默向零截断。

## 2. View 尺寸关系

```text
left/top/right/bottom：相对父容器的布局边界
width  = right - left
height = bottom - top
measuredWidth/Height：measure 阶段结果
x/y = left/top + translationX/Y：视觉属性位置
内容区 = [paddingLeft, paddingTop,
          width - paddingRight, height - paddingBottom]
```

| 需求 | 调用 | 是否触发布局 |
|---|---|---|
| 仅重绘全部 | `invalidate()` / `postInvalidateOnAnimation()` | 否 |
| 仅重绘局部 | `invalidate(dirtyRect)` | 否 |
| 尺寸/位置契约变化 | `requestLayout()` | 是 |
| 下一帧同步更新 | `postInvalidateOnAnimation()` | 否 |

## 3. Canvas 状态与坐标

```kotlin
val checkpoint = canvas.save()
try {
    canvas.translate(dx, dy)
    canvas.rotate(degrees, pivotX, pivotY)
    canvas.clipRect(clip)
    drawContent(canvas)
} finally {
    canvas.restoreToCount(checkpoint)
}
```

| 操作 | 作用 | 高频陷阱 |
|---|---|---|
| `translate` | 平移后续绘制坐标系 | 忘记 restore，污染后续绘制 |
| `scale` | 缩放；负值可翻转 | stroke/text 也随 Canvas 缩放 |
| `rotate` | 顺时针旋转（屏幕 y 向下） | pivot 坐标空间弄错 |
| `concat(matrix)` | 连接变换 | 乘法顺序不同，结果不同 |
| `clipRect/clipPath` | 收窄裁剪区域 | 不能靠后续 clip “扩大回来” |
| `saveLayer` | 创建离屏图层 | 显存/带宽昂贵，不应默认使用 |

坐标流：

```text
模型坐标 --Matrix--> View 内容坐标 --Canvas transform--> 设备像素
```

## 4. Paint 速查

| 属性/API | 用途 | 注意 |
|---|---|---|
| `style = FILL` | 填充几何 | strokeWidth 不生效 |
| `style = STROKE` | 描边 | 默认描边中心压在路径上 |
| `strokeWidth` | 线宽（px） | 0 表示 hairline，设备相关 |
| `strokeCap` | 线端：BUTT/ROUND/SQUARE | 会改变视觉长度 |
| `strokeJoin` | 连接：MITER/ROUND/BEVEL | 尖角受 miter 限制 |
| `isAntiAlias` | 几何抗锯齿 | 不是所有 Bitmap 缩放过滤 |
| `isFilterBitmap` | Bitmap 采样过滤 | 放缩图片时按质量需求设置 |
| `shader` | 渐变/纹理 | shader 有自己的 local matrix |
| `colorFilter` | 颜色过滤 | 与 alpha/混合叠加需实测 |
| `blendMode` | Porter-Duff/扩展混合 | API 与硬件支持需核对 |

> **性能提示**：复用 `Paint`、`Path`、`RectF`；不要在 `onDraw()` 内解码 Bitmap、创建 Typeface 或反复构造渐变。

## 5. 颜色与透明度

Android `ColorInt` 通常按 ARGB 表示：`0xAARRGGBB`。

```kotlin
import androidx.annotation.ColorInt
import androidx.core.graphics.ColorUtils
import kotlin.math.roundToInt

@ColorInt
fun withAlpha(@ColorInt color: Int, alpha: Float): Int =
    ColorUtils.setAlphaComponent(color, (alpha.coerceIn(0f, 1f) * 255).roundToInt())
```

| 概念 | 结论 |
|---|---|
| alpha | 0 全透明，255 不透明 |
| View alpha | 作用于整个 View 合成结果，可能涉及图层 |
| Paint alpha | 只作用于该次 Paint 绘制 |
| 预乘 alpha | Bitmap/渲染常以内存中的预乘分量处理；不要手算后重复预乘 |
| 颜色空间 | 广色域/线性运算不能等同于简单 sRGB 通道计算 |
| 对比度 | 不以“看起来差不多”为验收，使用 Accessibility Scanner/自动检查并人工验证 |

## 6. Path 与 RectF

| API | 语义 |
|---|---|
| `moveTo` | 移动当前点，不画线 |
| `lineTo` | 当前点到目标点直线 |
| `quadTo` | 二次贝塞尔：1 控制点 |
| `cubicTo` | 三次贝塞尔：2 控制点 |
| `close` | 当前轮廓闭合到起点 |
| `reset` | 清空并保留内部存储，适合复用 |
| `rewind` | 清空路径并保留数据结构；语义也用于复用 |
| `PathMeasure` | 长度、位置、切线与分段 |

`RectF` 使用 `[left, top, right, bottom]`。确保 `left <= right`、`top <= bottom`；负宽高不会自动“修好”。旋转矩形经 `Matrix.mapRect()` 后得到轴对齐包围盒。

## 7. 文字基线与测量

```text
top      ─────────── FontMetrics.top
ascent   ─────────── FontMetrics.ascent
baseline ─────────── drawText(x, baseline, paint)
descent  ─────────── FontMetrics.descent
bottom   ─────────── FontMetrics.bottom
```

垂直居中单行文字：

```kotlin
val fm = paint.fontMetrics
val baseline = centerY - (fm.ascent + fm.descent) / 2f
canvas.drawText(text, centerX, baseline, paint)
```

| 需求 | 首选 |
|---|---|
| 单行宽度 | `paint.measureText(text)` |
| 精确字形边界 | `paint.getTextBounds(...)`（边界不等同排版 advance） |
| ascent/descent | `paint.fontMetrics` |
| 多行、换行、span | `StaticLayout` / `Layout` |
| 双向文字 | 平台文字布局；不要手工反转字符串 |
| 可变字体/字距 | TextPaint + 平台布局，按目标 API 验证 |

> **无障碍提示**：Canvas 画出的文字不会自动成为可聚焦语义节点。重要内容应提供 content description、可访问状态；多个交互区域应暴露虚拟节点。

## 8. Bitmap 与 Drawable

- 依据目标显示尺寸解码，避免把超大原图常驻内存。
- `Drawable.setBounds()` 后再 `draw(canvas)`；Stateful Drawable 同步 `drawableState`。
- 回调型 Drawable 设置/清理 `callback`，在 View 生命周期结束时释放关联。
- 不在 `onDraw()` 里做磁盘 I/O 或同步网络访问。
- Bitmap 池、手工 `recycle()` 与共享引用容易冲突；遵循所用图片库的所有权规则。
- 硬件 Bitmap、软件 Canvas、像素读取之间存在限制，跨路径前先查 API 契约。

## 9. 快速选择

| 场景 | 推荐 |
|---|---|
| 简单形状 | Canvas + 复用 Paint |
| XML 可配置图形 | Shape/Vector Drawable |
| 多行文字 | StaticLayout |
| 大量可变对象 | 模型裁剪 + 局部失效 + 分层缓存 |
| 缩放/平移编辑器 | 单一 content-to-view Matrix + 逆变换命中 |
| 复杂遮罩/混合 | 先验证 blendMode；必要时最小范围 `saveLayer` |
| 动态效果 | ValueAnimator/physics + `postInvalidateOnAnimation()` |

## 延伸阅读

- [Canvas API](https://developer.android.com/reference/android/graphics/Canvas)
- [Paint API](https://developer.android.com/reference/android/graphics/Paint)
- [Matrix API](https://developer.android.com/reference/android/graphics/Matrix)
- [自定义绘制](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing)
