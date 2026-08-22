# 布局算法与自定义 LayoutParams

`onMeasure()` 决定“每个孩子多大”，`onLayout()` 决定“每个孩子在哪里”。真正可复用的容器不能把所有规则硬编码在类中，而要允许每个子 View 通过 `LayoutParams` 声明自己的布局意图，例如 margin、重力、是否另起一行或跨越几列。

## 学习目标

- 区分测量尺寸与布局边界，建立稳定的布局算法。
- 理解 `LayoutParams`、`MarginLayoutParams` 的职责与 margin 解析。
- 完整实现自定义 LayoutParams 的 XML/代码生成链。
- 正确处理 padding、margin、`GONE` 与 RTL（right-to-left）布局。
- 知道何时调用 `requestLayout()`，如何验证布局不变量。

## 1. `onLayout()` 的坐标契约

系统调用：

```kotlin
override fun onLayout(
    changed: Boolean,
    left: Int,
    top: Int,
    right: Int,
    bottom: Int
)
```

`left/top/right/bottom` 是当前 ViewGroup 在父坐标系中的位置，但给子 View 调用 `child.layout()` 时必须传**当前 ViewGroup 的局部坐标**。因此通常从 `paddingLeft`、`paddingTop` 开始，而不是从参数 `left`、`top` 开始。

```text
父坐标系
(0,0)
  └── ViewGroup: [left, top, right, bottom]
       局部坐标系 (0,0)
       ┌──────────────────────────┐
       │ paddingTop               │
       │   ┌──────────────────┐   │
       │   │ child.layout(...)│   │
       │   └──────────────────┘   │
       │             paddingBottom│
       └──────────────────────────┘
```

子 View 的边界满足：

```text
childRight  = childLeft + child.measuredWidth
childBottom = childTop  + child.measuredHeight
```

`changed` 只表示当前 ViewGroup 的边界是否相较上次发生变化，不表示所有子 View 都无需重新布局。只要系统进入 `onLayout()`，容器就应根据当前测量结果和 LayoutParams 正确摆放孩子。

## 2. 从最简单的纵向布局开始

下面的片段把可见子 View 从上到下排列：

```kotlin
import android.view.View
import android.view.ViewGroup

private fun ViewGroup.layoutChildrenVertically() {
    var y = paddingTop

    for (index in 0 until childCount) {
        val child = getChildAt(index)
        if (child.visibility == View.GONE) continue

        val lp = child.layoutParams as ViewGroup.MarginLayoutParams
        y += lp.topMargin

        val childLeft = paddingLeft + lp.leftMargin
        child.layout(
            childLeft,
            y,
            childLeft + child.measuredWidth,
            y + child.measuredHeight
        )

        y += child.measuredHeight + lp.bottomMargin
    }
}
```

这个算法隐含了三个不变量：下一项的起点不能早于上一项的底部；margin 不属于子 View 自身边界；padding 属于容器内部不可摆放区域。复杂布局也应先写出类似不变量，再实现循环。

> **注意**：不要在 `onLayout()` 中重新调用 `measure()` 来“修正”尺寸。布局依赖测量结果；若尺寸算法错误，应修复 `onMeasure()`，否则会打破遍历阶段和测量缓存的预期。

## 3. 为什么从 `MarginLayoutParams` 继承

`ViewGroup.LayoutParams` 只有 `width` 和 `height`。如果容器支持 `layout_margin`、`layout_marginStart` 等属性，自定义参数应继承 `ViewGroup.MarginLayoutParams`：

```kotlin
class LayoutParams : ViewGroup.MarginLayoutParams {
    var breakLine: Boolean = false

    constructor(width: Int, height: Int) : super(width, height)

    constructor(context: Context, attrs: AttributeSet?) : super(context, attrs) {
        // 若项目声明了 R.styleable.FlowLayout_Layout，
        // 可在这里读取 layout_breakLine，并在 finally 中 recycle。
    }

    constructor(source: ViewGroup.LayoutParams) : super(source)

    constructor(source: ViewGroup.MarginLayoutParams) : super(source)

    constructor(source: LayoutParams) : super(source) {
        breakLine = source.breakLine
    }
}
```

继承后不仅获得四个物理 margin，还获得 start/end margin 的解析能力。XML 自定义属性通常命名为 `layout_*`，因为它描述的是子 View 在该父容器中的规则，而不是子 View 自己的视觉属性。

若要从 XML 读取 `layout_breakLine`，资源声明类似：

```xml
<resources>
    <declare-styleable name="FlowLayout_Layout">
        <attr name="layout_breakLine" format="boolean" />
    </declare-styleable>
</resources>
```

读取代码为：

```kotlin
constructor(context: Context, attrs: AttributeSet?) : super(context, attrs) {
    val array = context.obtainStyledAttributes(
        attrs,
        R.styleable.FlowLayout_Layout
    )
    try {
        breakLine = array.getBoolean(
            R.styleable.FlowLayout_Layout_layout_breakLine,
            false
        )
    } finally {
        array.recycle()
    }
}
```

> **性能提示**：`TypedArray` 来自池，必须及时 `recycle()`。参数只需在构造时解析一次；不要在 `onMeasure()` 或 `onLayout()` 中重复读取 XML 属性。

## 4. LayoutParams 生成链必须完整

子 View 的参数来源不止 XML。inflate、代码动态添加、从另一个父容器移动过来，都会走不同入口。一个支持自定义参数的 ViewGroup 通常覆盖四个方法：

```kotlin
override fun generateDefaultLayoutParams(): LayoutParams =
    LayoutParams(
        ViewGroup.LayoutParams.WRAP_CONTENT,
        ViewGroup.LayoutParams.WRAP_CONTENT
    )

override fun generateLayoutParams(attrs: AttributeSet): LayoutParams =
    LayoutParams(context, attrs)

override fun generateLayoutParams(params: ViewGroup.LayoutParams): LayoutParams =
    when (params) {
        is LayoutParams -> LayoutParams(params)
        is MarginLayoutParams -> LayoutParams(params)
        else -> LayoutParams(params)
    }

override fun checkLayoutParams(params: ViewGroup.LayoutParams): Boolean =
    params is LayoutParams
```

```text
XML inflate ─────────────► generateLayoutParams(attrs)
addView(child) 无参数 ───► generateDefaultLayoutParams()
addView(child, oldParams) ► checkLayoutParams(oldParams)
                              │ false
                              ▼
                         generateLayoutParams(oldParams)
```

复制构造器不能只复制 `width`/`height`。从同类参数复制时要保留自定义字段；从 `MarginLayoutParams` 转换时要保留 margin。否则动态移动 View 后，布局会悄悄变化。

在 Kotlin 中，内部类名也叫 `LayoutParams` 时，方法签名很容易因遮蔽而写错。建议对参数类型显式写 `ViewGroup.LayoutParams`，对返回值保留自定义 `LayoutParams`，让意图一眼可见。

## 5. 修改参数为什么要 `requestLayout()`

会影响位置或尺寸的参数变化必须触发新的测量/布局：

```kotlin
fun View.setBreakLine(value: Boolean) {
    val lp = layoutParams as? FlowLayout.LayoutParams ?: return
    if (lp.breakLine == value) return
    lp.breakLine = value
    layoutParams = lp // View.setLayoutParams() 会请求重新布局
}
```

若直接改字段：

```kotlin
(view.layoutParams as FlowLayout.LayoutParams).breakLine = true
view.requestLayout()
```

仅影响绘制颜色的字段通常调用 `invalidate()`；影响几何关系的字段调用 `requestLayout()`。若两者都影响，需要两条路径都覆盖，虽然一次后续布局往往也会带来绘制。

## 6. RTL：不要把“开始”永远写成“左”

RTL 布局下，逻辑起点（start）在右侧，终点（end）在左侧。需要区分：

- 物理方向：`left/right`，适合绝对坐标、已解析后的最终边界。
- 逻辑方向：`start/end`，适合表达阅读顺序和用户界面语义。

在 XML 中优先提供 `layout_marginStart`/`layout_marginEnd`。框架在布局方向解析阶段会把相对 margin 解析到 `leftMargin`/`rightMargin`，因此 `onLayout()` 使用已解析的物理 margin 是可行的。若算法直接以逻辑方向工作，则使用 `MarginLayoutParamsCompat`：

```kotlin
import androidx.core.view.MarginLayoutParamsCompat
import androidx.core.view.ViewCompat

val isRtl = ViewCompat.getLayoutDirection(this) == ViewCompat.LAYOUT_DIRECTION_RTL
val startMargin = MarginLayoutParamsCompat.getMarginStart(lp)
val endMargin = MarginLayoutParamsCompat.getMarginEnd(lp)
```

横向布局可以维护一个逻辑游标：

```text
LTR:  start ──► [A] [B] [C] ──► end
RTL:  end   ◄── [C] [B] [A] ◄── start

LTR cursor 起于 paddingLeft，逐渐增大
RTL cursor 起于 width-paddingRight，逐渐减小
```

LTR 的子边界：

```kotlin
val childLeft = cursor + lp.leftMargin
val childRight = childLeft + child.measuredWidth
cursor += lp.leftMargin + child.measuredWidth + lp.rightMargin
```

RTL 的子边界：

```kotlin
val childRight = cursor - lp.rightMargin
val childLeft = childRight - child.measuredWidth
cursor -= lp.rightMargin + child.measuredWidth + lp.leftMargin
```

使用 `width` 而不是 `right - left` 也可得到容器局部宽度。方向变化会触发重新布局；若缓存了行信息或逻辑坐标，应在布局方向变化时失效缓存。

> **无障碍提示**：RTL 不只是镜像坐标。视觉顺序、键盘焦点顺序和无障碍遍历顺序应保持一致。若视觉上从右向左排列，却通过手工索引强制从左向右聚焦，TalkBack 与键盘用户会感到跳跃。

## 7. 自定义参数的边界设计

一个好的 LayoutParams 应只描述单个孩子相对父容器的规则。以下字段适合放进去：

- `breakLine`：当前孩子是否强制另起一行；
- `columnSpan`：孩子跨越多少列；
- `gravity`：孩子在分配区域中的对齐方式；
- `ignoreFlow`：是否退出正常流布局。

以下状态通常属于父容器，而不是 LayoutParams：

- 全局行间距、列间距；
- 当前滚动偏移；
- 已计算出的行列表缓存；
- 全局最大列数。

参数要有安全默认值并校验范围。例如 `columnSpan.coerceAtLeast(1)`。如果非法值应立即暴露开发错误，也可在 setter 中 `require()`；不要让错误拖到 `onLayout()` 才表现为坐标越界。

## 8. 常见陷阱

1. **只覆盖 `generateLayoutParams(attrs)`**：XML 正常，动态 `addView()` 却得到错误参数类型。
2. **复制时丢字段**：margin 或自定义 `breakLine` 在移动 View 后消失。
3. **支持 margin 却继承基础 LayoutParams**：`layout_margin*` 无法按预期解析，`measureChildWithMargins()` 还会转换失败。
4. **在子坐标中加父的 `left/top`**：容器不在原点时出现双重偏移。
5. **把 margin 算进 child 边界**：margin 是边界外间隔，不能扩大 `child.layout()` 的矩形。
6. **只测 LTR**：硬编码左起点，阿拉伯语、希伯来语环境下顺序错误。
7. **直接改参数不请求布局**：数据已经变化，屏幕仍保持旧位置。
8. **`onLayout()` 中创建大量临时集合**：布局频繁发生时增加 GC 压力；可在测量阶段复用缓存，或采用无分配遍历。

## 实践检查清单

- [ ] `onLayout()` 使用父容器局部坐标。
- [ ] padding、四向 margin 与子测量尺寸分别处理。
- [ ] `GONE` 不占空间，`INVISIBLE` 仍占空间。
- [ ] 覆盖 default、XML、copy、check 四个 LayoutParams 入口。
- [ ] 复制构造器保留 margin 和全部自定义字段。
- [ ] 几何参数变化触发 `requestLayout()`。
- [ ] LTR/RTL 均测试，start/end margin 行为正确。
- [ ] 空容器、单子 View、超大子 View 和动态 add/remove 均无越界。
- [ ] 视觉顺序与焦点、无障碍遍历顺序一致。

## 小结

布局算法的核心不是循环调用 `child.layout()`，而是维护清晰的坐标不变量。`MarginLayoutParams` 让子 View 能声明容器相关规则，完整的生成链保证 XML 与动态添加行为一致，RTL 处理则要求算法从“固定左起”升级为“逻辑起点”。把参数契约和坐标契约写清楚，容器才能真正用于组件库和动态界面。

## 延伸阅读

- [ViewGroup.LayoutParams](https://developer.android.com/reference/android/view/ViewGroup.LayoutParams)
- [ViewGroup.MarginLayoutParams](https://developer.android.com/reference/android/view/ViewGroup.MarginLayoutParams)
- [支持不同语言和文化](https://developer.android.com/training/basics/supporting-devices/languages)
- [MarginLayoutParamsCompat](https://developer.android.com/reference/androidx/core/view/MarginLayoutParamsCompat)
