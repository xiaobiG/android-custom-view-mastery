# Layout：位置如何向下分配

测量回答“需要多大”，布局（layout）回答“放在哪里”。更准确地说，父级根据子级测量结果决定其四条边，再通过 `child.layout(left, top, right, bottom)` 把位置向下分配；子级边界确定后，几何信息便可用于绘制和命中测试。

## 学习目标

读完本章，你应当能够：

- 区分测量尺寸、布局边界与视觉变换属性；
- 描述 `layout()`、`setFrame()`、`onLayout()`、`onSizeChanged()` 的职责边界；
- 为自定义 ViewGroup 实现一致的测量和布局算法；
- 正确处理 padding、margin、RTL 与 GONE 子元素；
- 判断几何缓存应在何处更新。

其中 `setFrame()` 是把 `layout()` 传入的四条边真正写入 View 并触发尺寸相关回调的步骤，是理解“布局副作用”的关键，将在第二节单独展开。

## 一、布局阶段的核心数据

View 的 `left`、`top`、`right`、`bottom` 是相对父 View 内容坐标系的布局边界：

```text
父 View 局部坐标
(0,0)
  +-------------------------------------+
  | padding                             |
  |    (left, top)                      |
  |       +--------------------+        |
  |       |       child        |        |
  |       | width = right-left |        |
  |       +--------------------+        |
  |                     (right,bottom)  |
  +-------------------------------------+
```

`width = right - left`，`height = bottom - top`。测量后的 `measuredWidth` 通常用于决定布局宽度，但平台允许父级在布局时给出不同边界，因此不要把二者概念合并。

`translationX/Y`、`scaleX/Y`、`rotation` 属于绘制/属性变换，不会改写 `left/top/right/bottom`。`x` 通常等于 `left + translationX`，动画后的视觉位置与布局位置可能不同，事件命中和兄弟排布仍要明确使用哪套几何。

## 二、从根到子节点的 layout 流程

顶层遍历判断需要布局后，对根 View 调用 `layout()`。`View.layout()` 处理边界变化，并在适当情况下进入 `onLayout()`。对普通 View，通常无需覆盖 `onLayout()`；对 ViewGroup，`onLayout()` 是为每个可见子 View 分配边界的核心回调。

```text
ViewRootImpl 发起 layout 阶段
        |
        v
root.layout(l, t, r, b)
        |
        +--> 更新自身 frame
        +--> 尺寸变化时 onSizeChanged(...)
        v
ViewGroup.onLayout(...)
        |
        +--> childA.layout(...)
        |       +--> 若 childA 是容器，递归 onLayout
        +--> childB.layout(...)
        v
整棵树获得相对父级的几何边界
```

“位置向上确定”容易产生歧义：子 View 把测量结果返回给父级后，父级拥有更高层的布局决策权；真正的边界调用仍是从父向子传递。也就是说，**尺寸信息向父级汇总，位置决策由父级产生并向子级下发**。

### layout() 内部：setFrame() 更新四条边

`View.layout()` 不是直接给 `mLeft/mRight/mTop/mBottom` 赋值，而是先记录旧边界，再调用 `setFrame(left, top, right, bottom)`。`setFrame()` 负责比较新旧边界、写入四个字段，并在尺寸变化时触发 `onSizeChanged()`；`layout()` 随后根据 `setFrame()` 的返回值决定是否进入 `onLayout()`，并向注册了 `OnLayoutChangeListener` 的监听器派发新老边界。

```text
layout(l, t, r, b)
  ├─ 记录 oldL/oldT/oldR/oldB
  ├─ setFrame(l, t, r, b)
  │    ├─ 边界未变 → 返回 false
  │    └─ 边界变化 → 更新 mLeft/mTop/mRight/mBottom
  │         └─ 尺寸变化 → sizeChange → onSizeChanged
  ├─ changed（或需要重新布局）→ onLayout(...)
  └─ changed → 派发 OnLayoutChangeListener
```

两个对自定义控件重要的推论：

1. `setFrame()` 返回 `Boolean` 表示边界是否变化。尺寸变化才会触发 `onSizeChanged()`；只移动位置、尺寸不变时不会触发，因此不能用 `onSizeChanged()` 代替“每次边界变化都要更新的逻辑”。
2. 普通 View 的 `onLayout()` 是空实现，只有 ViewGroup 在这里排布子元素。自定义 View 通常不需要也不应该覆盖 `onLayout()`；需要监听边界变化时，注册 `OnLayoutChangeListener` 比拦截 `setFrame()` 更干净。

## 三、onSizeChanged 与几何缓存

当 View 的布局尺寸改变时，`onSizeChanged(w, h, oldw, oldh)` 是重建尺寸相关几何的理想位置。例如圆弧边界、静态 Path、渐变范围可在这里更新，而不是每次 `onDraw()` 重算。

```kotlin
package com.example.customview.internals

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

class RingView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 8f * resources.displayMetrics.density
    }
    private val arcBounds = RectF()

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        val contentLeft = paddingLeft.toFloat()
        val contentTop = paddingTop.toFloat()
        val contentRight = (w - paddingRight).toFloat()
        val contentBottom = (h - paddingBottom).toFloat()
        val diameter = min(contentRight - contentLeft, contentBottom - contentTop)
        val cx = (contentLeft + contentRight) / 2f
        val cy = (contentTop + contentBottom) / 2f
        val radius = (diameter - paint.strokeWidth).coerceAtLeast(0f) / 2f
        arcBounds.set(cx - radius, cy - radius, cx + radius, cy + radius)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (!arcBounds.isEmpty) {
            canvas.drawArc(arcBounds, -90f, 270f, false, paint)
        }
    }
}
```

若 padding、strokeWidth 等属性在尺寸不变时变化，也必须主动重建 `arcBounds`，不能只依赖 `onSizeChanged()`。可以抽取 `updateGeometry()`，由属性 setter 和 `onSizeChanged()` 共同调用。

## 四、自定义 ViewGroup 的布局算法

以下简化容器横向排列子 View，展示 measure 与 layout 必须采用同一空间模型。示例支持 margin，并使用相对 padding 处理 RTL 起点；为聚焦流程，未实现换行。

```kotlin
package com.example.customview.internals

import android.content.Context
import android.util.AttributeSet
import android.view.View
import android.view.ViewGroup
import androidx.core.view.MarginLayoutParamsCompat
import androidx.core.view.ViewCompat
import kotlin.math.max

class RowLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : ViewGroup(context, attrs) {

    override fun generateDefaultLayoutParams(): LayoutParams =
        MarginLayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT)

    override fun generateLayoutParams(attrs: AttributeSet): LayoutParams =
        MarginLayoutParams(context, attrs)

    override fun generateLayoutParams(p: LayoutParams): LayoutParams =
        MarginLayoutParams(p)

    override fun checkLayoutParams(p: LayoutParams): Boolean =
        p is MarginLayoutParams

    override fun onMeasure(widthSpec: Int, heightSpec: Int) {
        var usedWidth = paddingLeft + paddingRight
        var maxChildHeight = 0
        var childState = 0

        for (index in 0 until childCount) {
            val child = getChildAt(index)
            if (child.visibility == View.GONE) continue
            measureChildWithMargins(child, widthSpec, usedWidth, heightSpec, 0)
            val lp = child.layoutParams as MarginLayoutParams
            usedWidth += child.measuredWidth + lp.leftMargin + lp.rightMargin
            maxChildHeight = max(
                maxChildHeight,
                child.measuredHeight + lp.topMargin + lp.bottomMargin
            )
            childState = combineMeasuredStates(childState, child.measuredState)
        }

        setMeasuredDimension(
            resolveSizeAndState(usedWidth, widthSpec, childState),
            resolveSizeAndState(
                maxChildHeight + paddingTop + paddingBottom,
                heightSpec,
                childState shl MEASURED_HEIGHT_STATE_SHIFT
            )
        )
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val rtl = ViewCompat.getLayoutDirection(this) == ViewCompat.LAYOUT_DIRECTION_RTL
        var cursor = if (rtl) width - paddingRight else paddingLeft

        for (index in 0 until childCount) {
            val child = getChildAt(index)
            if (child.visibility == View.GONE) continue
            val lp = child.layoutParams as MarginLayoutParams
            val startMargin = MarginLayoutParamsCompat.getMarginStart(lp)
            val top = paddingTop + lp.topMargin

            if (rtl) {
                val right = cursor - startMargin
                child.layout(right - child.measuredWidth, top, right, top + child.measuredHeight)
                cursor = right - child.measuredWidth - MarginLayoutParamsCompat.getMarginEnd(lp)
            } else {
                val left = cursor + startMargin
                child.layout(left, top, left + child.measuredWidth, top + child.measuredHeight)
                cursor = left + child.measuredWidth + MarginLayoutParamsCompat.getMarginEnd(lp)
            }
        }
    }
}
```

该示例仍有工程边界：当父宽度不足时不会换行；高度没有垂直对齐策略；测量时按物理 margin 累计而布局按 start/end 读取，生产实现应彻底统一相对方向语义。示例的价值是暴露布局责任，而不是提供完整 FlowLayout。

> **注意**：`GONE` 子 View 通常不参与测量和布局；`INVISIBLE` 仍占据空间，只是不绘制自身内容。

## 五、布局、重布局与属性动画

尺寸、LayoutParams、padding 或影响期望尺寸的内容变化，应调用 `requestLayout()`。它把“布局可能失效”沿父链上报，下一次遍历可能重新 measure/layout。单纯颜色变化不需要重布局。

若只做短期视觉移动，`translationX/Y` 通常避免触发布局；但不要用它掩盖真实排布变化。其他子节点不会因为某个 View 的 translation 自动重新让位，无障碍边界和命中逻辑也需要实际验证。

> **性能提示**：频繁改变会影响父子排布的属性可能导致整棵子树反复测量与布局。动画优先考虑不改变布局边界的属性，但正确性和语义优先于“少 layout”。

## 六、常见陷阱

1. **在 `onLayout()` 调用 `requestLayout()`**：容易形成重复遍历甚至布局循环。
2. **测量与布局算法不一致**：测量声称一套尺寸，布局却占用另一套空间。
3. **遗漏 margin 或 padding**：子 View 重叠、越界或内容贴边。
4. **只按 LTR 放置**：RTL 下顺序、起点和 margin 语义错误。
5. **把 translation 当布局坐标**：兄弟布局和视觉位置脱节。
6. **每帧在 onDraw 重建静态几何**：应在尺寸或相关属性变化时更新。
7. **布局 GONE 子元素**：浪费成本并违背常见容器语义。

## 七、实践检查清单

- [ ] 我能区分 measuredWidth、width、left 和 x。
- [ ] 父容器只在 `onLayout()` 中依据测量结果为子 View 分配边界。
- [ ] 测量与布局使用一致的 padding、margin 和排列规则。
- [ ] `GONE` 与 `INVISIBLE` 的空间语义符合预期。
- [ ] RTL 使用 start/end 语义并经过实测。
- [ ] 尺寸相关几何在 `onSizeChanged()` 或统一更新函数中缓存。
- [ ] 真实排布变化调用 `requestLayout()`，纯视觉变化不滥用它。

## 小结

布局阶段由父级消费子级测量结果、决定四条边并向下调用 `layout()`。ViewGroup 的 `onLayout()` 是排列算法所在；普通 View 则应把尺寸相关几何更新放在 `onSizeChanged()`。区分布局边界和视觉变换，并让 measure 与 layout 共用同一空间模型，是避免错位与重复遍历的关键。

## 官方延伸阅读

- [View.layout](https://developer.android.com/reference/android/view/View#layout(int,%20int,%20int,%20int))
- [View.onSizeChanged](https://developer.android.com/reference/android/view/View#onSizeChanged(int,%20int,%20int,%20int))
- [ViewGroup.onLayout](https://developer.android.com/reference/android/view/ViewGroup#onLayout(boolean,%20int,%20int,%20int,%20int))
- [Support different layout directions](https://developer.android.com/training/basics/supporting-devices/languages#CreateLayout)
- [ViewGroup.LayoutParams](https://developer.android.com/reference/android/view/ViewGroup.LayoutParams)
