# Draw：绘制遍历与顺序

布局完成后，每个 View 已有边界，绘制（draw）阶段把树转换为可提交的绘制命令。自定义控件不仅要会用 Canvas，更要知道背景、内容、子 View、前景与装饰出现的相对顺序，以及 Canvas 状态为何必须成对保存与恢复。

## 学习目标

读完本章，你应当能够：

- 描述 `View.draw()` 的概念绘制顺序；
- 区分 `draw()`、`onDraw()` 与 `dispatchDraw()` 的职责；
- 正确管理 Canvas 的坐标变换、裁剪和保存栈；
- 解释 ViewGroup 的子元素绘制顺序；
- 避免在高频绘制路径中分配对象或触发布局。

## 一、View.draw 的概念顺序

平台的具体优化会随版本和硬件加速状态变化，但从可覆盖的职责看，一次 `View.draw(canvas)` 可理解为：

```text
View.draw(canvas)
   |
   +--> 绘制背景 background
   +--> 保存 / 处理滚动相关变换（实现细节可能变化）
   +--> onDraw(canvas)          自身内容
   +--> dispatchDraw(canvas)    子 View（ViewGroup）
   +--> 绘制 fading edge 等装饰
   +--> 绘制前景 foreground / 默认焦点高亮
   v
完成当前节点及其子树
```

因此：

- 覆盖 `onDraw()`：绘制 View 自身内容；
- 覆盖 `dispatchDraw()`：容器在子 View 绘制前后增加效果；
- 一般不覆盖 `draw()`：它编排完整顺序，错误实现容易漏掉背景、子元素或前景；
- 覆盖 `draw()` 时必须非常明确调用 `super.draw(canvas)` 的位置与影响。

> **注意**：上图是面向应用开发的概念模型，不是对所有 Android 版本内部指令的逐行复刻。应依赖公开回调的相对职责，而非私有实现细节。

## 二、Canvas 是状态机，不是像素数组

传入的 `Canvas` 维护变换矩阵、裁剪区等状态。`translate()`、`rotate()`、`scale()` 和 `clipRect()` 会影响后续绘制。使用 `save()` 保存状态，并在结束时 `restoreToCount()`，避免污染后续兄弟内容。

```text
初始 Canvas 状态 S0
      |
      +-- save() -> checkpoint
      +-- translate / rotate / clip -> S1
      +-- draw...（按 S1 执行）
      +-- restoreToCount(checkpoint)
      v
恢复 S0，继续其他绘制
```

下面的 Kotlin View 在局部坐标中绘制刻度环，所有可复用对象在构造阶段创建，临时 Canvas 变换被正确恢复。

```kotlin
package com.example.customview.internals

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

    private val tickPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.DKGRAY
        strokeWidth = 2f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
    }

    var progressDegrees: Float = 0f
        set(value) {
            val normalized = value.coerceIn(0f, 360f)
            if (field == normalized) return
            field = normalized
            invalidate() // 尺寸未变，只需重画
        }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val contentWidth = width - paddingLeft - paddingRight
        val contentHeight = height - paddingTop - paddingBottom
        val radius = min(contentWidth, contentHeight) / 2f
        if (radius <= 0f) return

        val cx = paddingLeft + contentWidth / 2f
        val cy = paddingTop + contentHeight / 2f
        val checkpoint = canvas.save()
        try {
            canvas.translate(cx, cy)
            repeat(12) { index ->
                tickPaint.color = if (index * 30f <= progressDegrees) {
                    Color.rgb(30, 120, 230)
                } else {
                    Color.LTGRAY
                }
                canvas.drawLine(0f, -radius, 0f, -radius * 0.82f, tickPaint)
                canvas.rotate(30f)
            }
        } finally {
            canvas.restoreToCount(checkpoint)
        }
    }
}
```

对简单 View，框架通常已把 Canvas 映射到其局部坐标。绘制时用 `width/height` 和 padding 定义内容区，不要再次手动加上 `left/top`，否则会重复偏移。

## 三、背景、内容、子 View 与前景

如果希望效果位于内容后面，在 `onDraw()` 中先画装饰再画主体；若希望容器装饰覆盖子 View，可在 `dispatchDraw()` 的 `super.dispatchDraw(canvas)` 之后绘制。

```kotlin
class OverlayContainer(context: android.content.Context) :
    android.widget.FrameLayout(context) {

    private val overlayPaint = android.graphics.Paint().apply {
        color = 0x33000000
    }

    override fun dispatchDraw(canvas: android.graphics.Canvas) {
        super.dispatchDraw(canvas) // 先画子 View
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), overlayPaint)
    }
}
```

若希望装饰在子 View 后面，应在 `super.dispatchDraw()` 前画。背景和 foreground 由 `draw()` 的框架顺序处理；把所有东西塞进 `onDraw()` 可能得不到想要的层级。

对 ViewGroup，还要注意默认情况下 `setWillNotDraw(true)` 可能跳过容器的 `onDraw()`；若容器自身需要在 `onDraw()` 绘制，可调用 `setWillNotDraw(false)`。但仅在 `dispatchDraw()` 画覆盖层不一定需要改变此标记。

## 四、子 View 的绘制顺序

默认情况下，ViewGroup 通常按子元素绘制顺序处理，后绘制者覆盖先绘制者。`elevation`/Z、`translationZ`、自定义 drawing order、动画与容器实现都可能影响最终顺序。不要仅凭 XML 顺序推断所有场景。

```text
父背景
   |
   +--> child A
   +--> child B（可覆盖 A）
   +--> child C（可覆盖 A/B）
   |
父前景 / 覆盖装饰
```

需要稳定层级时，明确设计 Z/elevation 与子顺序，并在目标 API 和硬件加速环境中验证。触摸命中顺序与视觉 Z 的关系也应做交互测试，不能只看截图。

## 五、软件绘制与硬件加速边界

在硬件加速下，`onDraw()` 更接近记录绘制命令，后续由渲染线程和 GPU 管线处理；它不意味着所有 API 都“在 GPU 上立即画完”。软件层、硬件层与 `setLayerType()` 有各自的兼容性、内存和更新成本。

### setLayerType：三种绘制目标

`setLayerType(type, paint)` 控制 View 绘制到哪里：

- `LAYER_TYPE_NONE`（默认）：直接绘制到父层，无额外缓冲，开销最小。
- `LAYER_TYPE_SOFTWARE`：内容渲染进软件位图，每次失效都会重建。适合硬件加速不支持的效果（如某些复杂 `saveLayer`/Xfermode 组合）或截图场景；内存与更新成本高，不宜常驻。
- `LAYER_TYPE_HARDWARE`：内容记录为 GPU 层。用于动画期间提升渲染质量（如对含阴影、圆角的内容做旋转/透明时，避免每帧重绘整棵子树）；代价是显存占用、纹理上传与失效区域重建。

判断是否值得用图层：内容基本静态、动画只做整体变换（alpha/旋转/缩放/平移）时，硬件层通常划算；内容每帧变化或尺寸巨大时，重建图层可能比直接绘制更贵。`ViewPropertyAnimator.withLayer()`（API 16）能在动画期间临时启用硬件层、结束后恢复 `NONE`，是低成本尝试图层的入口。

> **性能提示**：不要为了“更快”常驻开启硬件层。图层适合特定动画或复用场景，内容频繁变化时重建图层可能更贵。先用 Perfetto、GPU 渲染分析和过度绘制工具验证。

高频路径的原则：

- 复用 Paint、Path、Rect/RectF、着色器和临时数组；
- 把尺寸相关计算移到 `onSizeChanged()`；
- 避免在 `onDraw()` 格式化字符串、创建集合或加载 Bitmap；
- 控制 saveLayer，离屏缓冲可能带来显著成本；
- 缩小失效区域只能作为优化，并需考虑硬件渲染实现和祖先变换。

> **无障碍提示**：Canvas 上画出的文字和图形不会自动成为语义节点。可操作的绘制区域需要内容描述、点击语义，复杂控件则需要虚拟无障碍节点。

## 六、Outline 与圆形裁剪

硬件加速下，View 的边界形状由 `Outline` 描述，驱动阴影、点击区域和裁剪。相关 API 为 API 21+：

- `setOutlineProvider(provider)`：用 `ViewOutlineProvider` 提供轮廓；
- `clipToOutline = true`：把 View 内容裁剪到轮廓范围，是硬件裁剪，无需离屏缓冲；
- 内置形状：`ViewOutlineProvider.BACKGROUND` 跟随 background 的圆角/圆形，`PADDED_BOUNDS`/`BOUNDS` 为矩形；自定义则实现 `getOutline()`。

圆形头像是最常见的用法：

```kotlin
imageView.outlineProvider = object : ViewOutlineProvider() {
    override fun getOutline(view: View, outline: Outline) {
        val size = min(view.width, view.height)
        val left = (view.width - size) / 2f
        val top = (view.height - size) / 2f
        outline.setOval(left, top, left + size, top + size)
    }
}
imageView.clipToOutline = true
```

要点：

- 阴影来自 `elevation` 且由 outline 驱动，透明区域不会投射阴影；
- `clipToOutline` 依赖当前 outline 生效，修改轮廓会触发失效，频繁改动不划算；
- 它和 `canvas.clipPath()` 不是一回事：前者是硬件裁剪路径，后者走绘制命令，成本与兼容性不同。

> **性能提示**：能用 `clipToOutline` 的圆角/圆形裁剪优先用它，避免在 `onDraw()` 里做离屏缓冲或复杂 `clipPath`。

## 七、常见陷阱

1. **覆盖 `draw()` 却不调用 super**：背景、内容、子 View 或前景消失。
2. **Canvas 变换不恢复**：后续绘制全部偏移、缩放或被裁剪。
3. **在局部 Canvas 再加 `left/top`**：内容产生双重偏移。
4. **在 `onDraw()` 创建大量对象**：持续帧中引发 GC 抖动。
5. **在绘制中修改布局或调用 `requestLayout()`**：造成下一轮遍历甚至循环。
6. **误以为 ViewGroup 一定调用 onDraw**：`willNotDraw` 优化可能跳过它。
7. **把硬件层当万能优化**：可能增加显存、上传和失效成本。

## 八、实践检查清单

- [ ] 我能说明 background、onDraw、dispatchDraw 和 foreground 的相对职责。
- [ ] Canvas 的每次临时变换或裁剪都通过 save/restore 限定范围。
- [ ] `onDraw()` 中没有可避免的对象分配、I/O 或业务状态修改。
- [ ] 内容坐标以 View 局部坐标和 padding 为基础。
- [ ] 容器覆盖层放在 `super.dispatchDraw()` 的正确一侧。
- [ ] 子 View 重叠时已验证绘制顺序、Z 与触摸行为。
- [ ] 自定义绘制内容已补充必要的无障碍语义。

## 小结

`View.draw()` 组织背景、自身内容、子 View 和前景；`onDraw()` 专注自身内容，`dispatchDraw()` 负责子树绘制。Canvas 是带变换与裁剪状态的命令记录入口，必须管理保存栈。把几何计算移出高频路径、复用对象并基于证据选择图层，才能同时保持顺序正确与帧稳定。

## 官方延伸阅读

- [View.draw](https://developer.android.com/reference/android/view/View#draw(android.graphics.Canvas))
- [Canvas](https://developer.android.com/reference/android/graphics/Canvas)
- [Custom drawing](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing)
- [Hardware acceleration](https://developer.android.com/develop/ui/views/graphics/hardware-accel)
- [Reduce overdraw](https://developer.android.com/topic/performance/rendering/overdraw)
