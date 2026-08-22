# Measure：约束如何向下传递

测量（measure）不是让 View 随意报告“我想要多大”，而是父子之间的一轮约束协商：父级把可用空间编码成 `MeasureSpec` 传下去，子级计算测量尺寸，父级再利用结果安排整体。掌握位编码和约束生成规则，才能写出在不同容器中都正确的控件。

## 学习目标

读完本章，你应当能够：

- 解码 `MeasureSpec` 的模式与尺寸位；
- 解释 `EXACTLY`、`AT_MOST`、`UNSPECIFIED` 的真实含义；
- 描述父布局参数如何转换为子约束；
- 正确处理 padding、建议最小尺寸与测量状态；
- 编写不违反父约束的 `onMeasure()`；
- 判断何时需要 `requestLayout()`。

## 一、MeasureSpec 的位编码

`MeasureSpec` 是一个 `Int`，高 2 位存模式，低 30 位存尺寸。使用公开的 `View.MeasureSpec.getMode()`、`getSize()` 和 `makeMeasureSpec()` 操作它，不要在业务代码中手写掩码。

```text
31          30 29                                      0
+--------------+----------------------------------------+
| mode (2 bits)| size (30 bits)                         |
+--------------+----------------------------------------+

UNSPECIFIED = 00......
EXACTLY     = 01......
AT_MOST     = 10......
```

尺寸单位是像素。三种模式描述的是父级约束，而不是 XML 属性的同义词：

- `EXACTLY`：结果必须是给定尺寸；常见于固定值或某些 `match_parent` 场景；
- `AT_MOST`：结果不能超过给定尺寸；常见于 `wrap_content`；
- `UNSPECIFIED`：父级不对这一维设置上限；滚动方向的测量中可能出现。

> **注意**：不能只根据 `layout_width="wrap_content"` 推断一定收到 `AT_MOST`。父容器负责生成子 MeasureSpec，不同容器与自身约束会影响结果。

## 二、父子约束怎样传递

ViewRootImpl 从窗口可用区域形成顶层约束。每个 ViewGroup 在 `onMeasure()` 中结合以下信息生成子约束：

- 自己收到的 MeasureSpec；
- 自己的 padding；
- 子 View 的 `LayoutParams` 与 margin；
- 已被其他子元素占用或容器算法保留的空间。

```text
窗口可用尺寸
      |
      v
父 View 收到 parentSpec
      |
      +-- 扣除 padding / margin / 已占空间
      +-- 读取 child.layoutParams
      v
getChildMeasureSpec(...) -> childSpec
      |
      v
child.measure(childSpec)
      |
      v
child.measuredWidth / measuredHeight / state
      |
      v
父 View 合并结果并 setMeasuredDimension(...)
```

一个常见但不完整的映射如下：

| 父约束 | 子参数 | 典型子约束 |
|---|---|---|
| `EXACTLY S` | 固定 `d` | `EXACTLY d` |
| `EXACTLY S` | `match_parent` | `EXACTLY 可用空间` |
| `EXACTLY S` | `wrap_content` | `AT_MOST 可用空间` |
| `AT_MOST S` | 固定 `d` | `EXACTLY d` |
| `AT_MOST S` | `match_parent` | 常为 `AT_MOST 可用空间` |
| `AT_MOST S` | `wrap_content` | `AT_MOST 可用空间` |
| `UNSPECIFIED` | `wrap_content` | `UNSPECIFIED` |

表格用于建立直觉，最终以父容器实现和 `ViewGroup.getChildMeasureSpec()` 契约为准。margin 与 padding 会减少可分配空间，结果尺寸也不能为负。

## 三、onMeasure 的职责

自定义 View 的 `onMeasure()` 应：

1. 计算内容期望尺寸；
2. 加上 padding，并考虑建议最小尺寸；
3. 用父约束解析宽高；
4. 通过 `setMeasuredDimension()` 提交结果。

`measuredWidth`/`measuredHeight` 是测量结果；`width`/`height` 是布局完成后的实际边界，两者所处阶段不同。一般不要在 `onMeasure()` 依赖尚未布局的 `width`。

```kotlin
package com.example.customview.internals

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import kotlin.math.max

class LabelChipView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 16f * resources.displayMetrics.scaledDensity
    }

    var label: String = "Measure"
        set(value) {
            if (field == value) return
            field = value
            requestLayout() // 文本宽度可能改变期望尺寸
            invalidate()
        }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val font = paint.fontMetrics
        val contentWidth = paint.measureText(label).toInt()
        val contentHeight = (font.descent - font.ascent).toInt()

        val desiredWidth = max(
            suggestedMinimumWidth,
            contentWidth + paddingLeft + paddingRight
        )
        val desiredHeight = max(
            suggestedMinimumHeight,
            contentHeight + paddingTop + paddingBottom
        )

        setMeasuredDimension(
            resolveSizeAndState(desiredWidth, widthMeasureSpec, 0),
            resolveSizeAndState(desiredHeight, heightMeasureSpec, 0)
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val baseline = paddingTop - paint.fontMetrics.ascent
        canvas.drawText(label, paddingLeft.toFloat(), baseline, paint)
    }
}
```

`resolveSizeAndState()` 在满足约束的同时保留 `MEASURED_STATE_TOO_SMALL` 等状态信息。自定义 ViewGroup 合并子状态时可使用 `combineMeasuredStates()`；解析高度时，要将 `measuredState` 中编码的高度状态左移 `MEASURED_HEIGHT_STATE_SHIFT` 后传入，平台容器源码可作为参考。

## 四、测量可能发生多次

父容器可能先以探索性约束测量子元素，再根据剩余空间二次测量。例如权重、比例、基线或依赖所有子尺寸的算法都可能导致重复。`onMeasure()` 必须是快速、确定且无外部副作用的计算。

```text
第一次 measure: 收集自然尺寸
        |
        v
父容器计算剩余空间 / 比例
        |
        v
第二次 measure: 分配精确尺寸
        |
        v
父容器提交最终测量结果
```

不要在 `onMeasure()` 发网络请求、修改业务状态、启动动画，或假设一次遍历只调用一次。缓存只有在输入（MeasureSpec、文字、样式、padding 等）一致且失效规则完整时才安全。

## 五、自定义 ViewGroup 的约束原则

容器应使用 `measureChildWithMargins()`、`getChildMeasureSpec()` 等平台辅助方法，避免遗漏父约束、padding、margin 和 `LayoutParams`。如果容器支持 margin，必须返回 `MarginLayoutParams` 或其子类，并在测量和布局阶段一致处理。

父容器最终尺寸通常来自：所有子结果 + 自身 padding + 建议最小尺寸，再受自己的父约束解析。容器不能简单把最大子尺寸相加或取最大值；算法应与布局策略一致，例如横向排列求宽度和、高度最大值，流式布局按行累计。

> **性能提示**：复杂 ViewGroup 的二次测量可能成倍放大成本。先用 trace 确认瓶颈，再优化算法；不要为了避免合法二次测量而返回错误尺寸。

## 六、常见陷阱

1. **忽略 MeasureSpec 模式，只取 size**：在 `AT_MOST` 下错误占满空间，在 `UNSPECIFIED` 下得到 0 或异常值。
2. **`wrap_content` 仍调用 `super.onMeasure()` 且无最小背景**：自定义 View 可能表现得像填满上限或没有期望尺寸。
3. **忘记 padding/最小尺寸**：内容被裁切，也破坏背景 Drawable 的最小尺寸语义。
4. **直接返回超过 `AT_MOST` 上限的值**：违反父子契约。
5. **在 onMeasure 依赖 `width`**：那是上一轮布局值或尚为 0。
6. **属性影响尺寸却只 `invalidate()`**：像素重画了，但布局没有重新协商。
7. **在测量中分配大量对象或产生副作用**：重复测量时放大卡顿和错误。

## 七、实践检查清单

- [ ] 我通过 `getMode()` / `getSize()` 解码，而非手写魔法位运算。
- [ ] 期望尺寸包含内容、padding 和建议最小尺寸。
- [ ] `EXACTLY` 严格采用父级指定尺寸。
- [ ] `AT_MOST` 不超过上限，`UNSPECIFIED` 使用合理自然尺寸。
- [ ] 影响尺寸的属性调用 `requestLayout()`，并在需要时 `invalidate()`。
- [ ] `onMeasure()` 无业务副作用，允许同一遍历中多次调用。
- [ ] 自定义 ViewGroup 一致处理 margin、padding 与测量状态。
- [ ] 已测试固定 dp、`wrap_content`、`match_parent` 和滚动父容器。

## 小结

MeasureSpec 用高 2 位编码模式、低 30 位编码尺寸，承载父级对子级的约束。父容器结合自己的约束、padding、margin 和子布局参数生成子 MeasureSpec；子 View 计算自然需求后，在约束内提交测量结果。正确测量的关键不是记映射表，而是始终尊重“父给约束、子回结果”的协议。

## 官方延伸阅读

- [View.MeasureSpec](https://developer.android.com/reference/android/view/View.MeasureSpec)
- [View.onMeasure](https://developer.android.com/reference/android/view/View#onMeasure(int,%20int))
- [ViewGroup.getChildMeasureSpec](https://developer.android.com/reference/android/view/ViewGroup#getChildMeasureSpec(int,%20int,%20int))
- [Custom view measurement](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing#override_onmeasure)
- [ViewGroup source (AOSP)](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/ViewGroup.java)
