# 实战：可用的 FlowLayout

FlowLayout（流式布局）按顺序横向摆放子 View，当前行放不下时自动换行。标签云、筛选条件、可变宽按钮组都适合这种布局。它看似只是“宽度相加”，实际上集中考验了子 View 测量、margin、自定义 LayoutParams、RTL、空容器与边界规格处理。

本章给出一个接近可直接放入 Android 工程的 Kotlin 实现。它只依赖 Android SDK，不依赖项目自定义资源；可选的 XML 自定义属性会单独说明。

## 学习目标

- 把“逐项装箱、超宽换行”转换成确定的测量与布局算法。
- 正确实现支持 margin 的 LayoutParams 生成链。
- 在 `EXACTLY`、`AT_MOST`、`UNSPECIFIED` 下得到合理尺寸。
- 支持 LTR 与 RTL，并保证测量、布局使用同一换行规则。
- 为 FlowLayout 设计覆盖边界的自动化测试。

## 1. 先定义行为契约

本实现采用以下规则：

1. `GONE` 子 View 不参与测量和布局，`INVISIBLE` 正常占位。
2. 子 View 外边距计入行宽和行高。
3. `horizontalSpacing` 只出现在同一行相邻可见子 View 之间，不出现在行首尾。
4. `verticalSpacing` 只出现在相邻非空行之间。
5. 某个子 View 含 margin 后仍宽于可用行宽时，它单独占一行；不强行裁剪，最终裁剪与状态由父约束决定。
6. `LayoutParams.breakLine = true` 时，该子 View 在当前行非空的情况下另起一行。
7. RTL 只改变每行的摆放起点和方向，不改变子 View 的逻辑遍历顺序与换行结果。

```text
可用宽度 = measuredWidth - paddingLeft - paddingRight

LTR:
┌────────────────────────────────────┐
│ padding [A]--h--[BBBB]--h--[C]     │ 行 1
│         [DDDDDD]--h--[E]           │ 行 2
└────────────────────────────────────┘
                 ↑ 行间 verticalSpacing

RTL:
┌────────────────────────────────────┐
│     [C]--h--[BBBB]--h--[A] padding │ 行 1
│           [E]--h--[DDDDDD] padding │ 行 2
└────────────────────────────────────┘
```

## 2. 完整 Kotlin 类

文件可保存为 `FlowLayout.kt`。若项目最低 API 很低也无需额外兼容库；`layoutDirection` 与相对 margin 的解析由 View 系统处理。

```kotlin
package com.example.widget

import android.content.Context
import android.util.AttributeSet
import android.view.View
import android.view.ViewGroup
import kotlin.math.max

class FlowLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : ViewGroup(context, attrs, defStyleAttr) {

    /** 同一行相邻可见子 View 之间的像素间距。 */
    var horizontalSpacing: Int = 0
        set(value) {
            val safeValue = value.coerceAtLeast(0)
            if (field == safeValue) return
            field = safeValue
            requestLayout()
        }

    /** 相邻非空行之间的像素间距。 */
    var verticalSpacing: Int = 0
        set(value) {
            val safeValue = value.coerceAtLeast(0)
            if (field == safeValue) return
            field = safeValue
            requestLayout()
        }

    class LayoutParams : MarginLayoutParams {
        /** true 表示当前子 View 在当前行非空时强制另起一行。 */
        var breakLine: Boolean = false

        constructor(width: Int, height: Int) : super(width, height)

        constructor(context: Context, attrs: AttributeSet?) : super(context, attrs)

        constructor(source: ViewGroup.LayoutParams) : super(source)

        constructor(source: MarginLayoutParams) : super(source)

        constructor(source: LayoutParams) : super(source) {
            breakLine = source.breakLine
        }
    }

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

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val widthMode = MeasureSpec.getMode(widthMeasureSpec)
        val widthSize = MeasureSpec.getSize(widthMeasureSpec)

        // UNSPECIFIED 表示横向没有上限，不应按 size=0 换行。
        val lineLimit = if (widthMode == MeasureSpec.UNSPECIFIED) {
            Int.MAX_VALUE
        } else {
            (widthSize - paddingLeft - paddingRight).coerceAtLeast(0)
        }

        var lineWidth = 0
        var lineHeight = 0
        var maxLineWidth = 0
        var contentHeight = 0
        var hasItemInLine = false
        var hasCompletedLine = false
        var childState = 0

        for (index in 0 until childCount) {
            val child = getChildAt(index)
            if (child.visibility == View.GONE) continue

            measureChildWithMargins(
                child,
                widthMeasureSpec,
                0,
                heightMeasureSpec,
                0
            )
            childState = combineMeasuredStates(childState, child.measuredState)

            val lp = child.layoutParams as LayoutParams
            val childWidth = lp.leftMargin + child.measuredWidth + lp.rightMargin
            val childHeight = lp.topMargin + child.measuredHeight + lp.bottomMargin
            val spacingBefore = if (hasItemInLine) horizontalSpacing else 0
            val mustWrap = hasItemInLine &&
                (lp.breakLine || lineWidth + spacingBefore + childWidth > lineLimit)

            if (mustWrap) {
                maxLineWidth = max(maxLineWidth, lineWidth)
                if (hasCompletedLine) contentHeight += verticalSpacing
                contentHeight += lineHeight
                hasCompletedLine = true

                lineWidth = childWidth
                lineHeight = childHeight
                hasItemInLine = true
            } else {
                lineWidth += spacingBefore + childWidth
                lineHeight = max(lineHeight, childHeight)
                hasItemInLine = true
            }
        }

        if (hasItemInLine) {
            maxLineWidth = max(maxLineWidth, lineWidth)
            if (hasCompletedLine) contentHeight += verticalSpacing
            contentHeight += lineHeight
        }

        val desiredWidth = max(
            suggestedMinimumWidth,
            paddingLeft + maxLineWidth + paddingRight
        )
        val desiredHeight = max(
            suggestedMinimumHeight,
            paddingTop + contentHeight + paddingBottom
        )

        setMeasuredDimension(
            resolveSizeAndState(desiredWidth, widthMeasureSpec, childState),
            resolveSizeAndState(
                desiredHeight,
                heightMeasureSpec,
                childState shl MEASURED_HEIGHT_STATE_SHIFT
            )
        )
    }

    override fun onLayout(
        changed: Boolean,
        left: Int,
        top: Int,
        right: Int,
        bottom: Int
    ) {
        val availableWidth =
            (right - left - paddingLeft - paddingRight).coerceAtLeast(0)
        val isRtl = layoutDirection == LAYOUT_DIRECTION_RTL

        var cursor = if (isRtl) right - left - paddingRight else paddingLeft
        var lineTop = paddingTop
        var lineWidth = 0
        var lineHeight = 0
        var hasItemInLine = false

        for (index in 0 until childCount) {
            val child = getChildAt(index)
            if (child.visibility == View.GONE) continue

            val lp = child.layoutParams as LayoutParams
            val childWidthWithMargins =
                lp.leftMargin + child.measuredWidth + lp.rightMargin
            val childHeightWithMargins =
                lp.topMargin + child.measuredHeight + lp.bottomMargin
            val spacingBefore = if (hasItemInLine) horizontalSpacing else 0
            val mustWrap = hasItemInLine &&
                (lp.breakLine ||
                    lineWidth + spacingBefore + childWidthWithMargins > availableWidth)

            if (mustWrap) {
                lineTop += lineHeight + verticalSpacing
                cursor = if (isRtl) {
                    right - left - paddingRight
                } else {
                    paddingLeft
                }
                lineWidth = 0
                lineHeight = 0
                hasItemInLine = false
            }

            val actualSpacing = if (hasItemInLine) horizontalSpacing else 0
            if (isRtl) {
                cursor -= actualSpacing
                val childRight = cursor - lp.rightMargin
                val childLeft = childRight - child.measuredWidth
                val childTop = lineTop + lp.topMargin
                child.layout(
                    childLeft,
                    childTop,
                    childRight,
                    childTop + child.measuredHeight
                )
                cursor -= childWidthWithMargins
            } else {
                cursor += actualSpacing
                val childLeft = cursor + lp.leftMargin
                val childTop = lineTop + lp.topMargin
                child.layout(
                    childLeft,
                    childTop,
                    childLeft + child.measuredWidth,
                    childTop + child.measuredHeight
                )
                cursor += childWidthWithMargins
            }

            lineWidth += actualSpacing + childWidthWithMargins
            lineHeight = max(lineHeight, childHeightWithMargins)
            hasItemInLine = true
        }
    }
}
```

> **注意**：示例中的间距单位是像素（px），因为 View 内部最终都使用像素。业务代码设置固定间距时应从 `dp` 转换，或增加自定义 XML dimension 属性，不要把裸整数误当 dp。

常用转换函数：

```kotlin
import android.content.Context
import kotlin.math.roundToInt

fun Context.dp(value: Int): Int =
    (value * resources.displayMetrics.density).roundToInt()
```

这里直接使用当前 `Context` 的 `resources.displayMetrics`，能让测试和配置上下文保持一致；
调用时写作 `context.dp(8)`，不要使用进程全局的 `Resources.getSystem()`。

## 3. 测量算法逐步拆解

### 3.1 可用行宽

父宽度有上限时：

```text
lineLimit = max(0, parentWidthSize - paddingLeft - paddingRight)
```

宽度为 `UNSPECIFIED` 时使用 `Int.MAX_VALUE` 表达“不因父上限换行”。若错误地使用规格中的 size（通常为 0），每个孩子都会被拆成单独一行。

### 3.2 单项占用

FlowLayout 的换行判断必须包含 margin：

```text
childWidth  = leftMargin + measuredWidth + rightMargin
childHeight = topMargin + measuredHeight + bottomMargin
candidate   = lineWidth + spacingBefore + childWidth
```

`spacingBefore` 只在当前行已有元素时出现。这样行首没有多余空白，空容器也不会产生负间距补偿。

### 3.3 提交一行

换行时，旧行先提交到汇总结果，再用当前孩子开启新行：

```text
maxLineWidth = max(maxLineWidth, lineWidth)
contentHeight += [非首行 ? verticalSpacing : 0] + lineHeight
lineWidth = childWidth
lineHeight = childHeight
```

遍历结束后还要提交最后一行。漏掉这一步会让单行布局测得高度为 0。

### 3.4 父尺寸与状态

期望尺寸包含 padding，并至少达到 `suggestedMinimumWidth/Height`。最终通过 `resolveSizeAndState()` 尊重父规格，并传播所有子 View 的 measured state。

`measureChildWithMargins()` 在宽度受限时可能把 `MATCH_PARENT` 子 View 测成整行可用宽；它通常会独占一行。若产品希望 `MATCH_PARENT` 表示“当前行剩余宽度”，则需要先确定该行已有占用，再用剩余宽度构造精确规格重测，这是另一份布局契约，不应暗中混入当前实现。

## 4. 为什么 onMeasure 与 onLayout 看起来重复

两个阶段都执行相同换行判定，是为了不存储临时行对象，避免每次布局分配集合。关键不是消除代码相似，而是保证规则一致：

```text
同一可用宽度
+ 同一可见性规则
+ 同一 margin 与 spacing
+ 同一 breakLine 条件
= 同一行划分
```

若未来加入每行居中、行内重力或基线对齐，建议在测量阶段缓存每行的起止 index、宽和高，并在规格、子数量或 LayoutParams 变化时重建。不要只改 `onLayout()` 的换行公式，否则测量高度与实际布局会分叉。

> **性能提示**：当前实现的测量和布局均为 O(n)，不为每行创建集合，适合几十到数百个轻量标签。若子项达到数千个，应考虑 RecyclerView、自定义 LayoutManager 或虚拟化方案；FlowLayout 会创建、测量并布局所有子 View。

## 5. RTL 与 margin 的处理

测量只关心总宽度，所以 LTR/RTL 的行划分相同。布局时：

- LTR 游标从 `paddingLeft` 开始递增；
- RTL 游标从 `width - paddingRight` 开始递减；
- 使用框架已根据布局方向解析后的 `leftMargin/rightMargin`。

在 RTL 下，第一个逻辑子 View 被放到最右侧，随后元素向左排列。遍历顺序没有反转，因此焦点和无障碍顺序仍与子树逻辑顺序一致。

如果需要让“数据列表最后一项”出现在右侧，那是业务顺序反转，不是 RTL 镜像，应在数据层明确处理。

## 6. 可选：从 XML 读取属性

为保持主类可复制，完整代码没有引用项目的 `R.styleable`。实际项目可声明：

```xml
<resources>
    <declare-styleable name="FlowLayout">
        <attr name="horizontalSpacing" format="dimension" />
        <attr name="verticalSpacing" format="dimension" />
    </declare-styleable>

    <declare-styleable name="FlowLayout_Layout">
        <attr name="layout_breakLine" format="boolean" />
    </declare-styleable>
</resources>
```

然后在 ViewGroup 构造器中读取全局间距，在 `LayoutParams(context, attrs)` 中读取 `layout_breakLine`。所有 `TypedArray` 都必须在 `finally` 中 `recycle()`。读取构造阶段可直接写 backing field，避免尚未完成初始化时多余 `requestLayout()`。

XML 使用示意：

```xml
<com.example.widget.FlowLayout
    android:id="@+id/flow"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:padding="16dp">

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_marginEnd="8dp"
        android:text="Android" />

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        app:layout_breakLine="true"
        android:text="新的一行" />
</com.example.widget.FlowLayout>
```

若未实现 `R.styleable` 解析，仍可在代码中设置：

```kotlin
val params = FlowLayout.LayoutParams(
    ViewGroup.LayoutParams.WRAP_CONTENT,
    ViewGroup.LayoutParams.WRAP_CONTENT
).apply {
    breakLine = true
    marginStart = context.dp(8)
}
child.layoutParams = params
```

## 7. 边界行为

### 空容器

`maxLineWidth` 与 `contentHeight` 都为 0，最终尺寸只包含 padding 与 suggested minimum。不会凭空加入行间距。

### 单个超宽孩子

行为空时不触发换行，孩子被放在第一行并可能超出可用宽度。父容器在受限规格下仍采用规定宽度，子 measured state 可报告过小。是否裁剪取决于 `clipChildren` 等设置。生产组件也可选择用更严格规格重测，但必须把该行为写入契约。

### 零可用宽度

当父宽度不大于左右 padding 时，可用宽度为 0。第一个孩子仍进入第一行，后续孩子各自换行。算法不会出现负数或无限循环。

### 强制换行

`breakLine` 只在当前行非空时生效。第一个可见孩子设置它不会制造空白首行；连续多个 `breakLine` 子项会各占一行。

### 高度受限

所有子 View 仍会完成布局，ViewGroup 最终高度受 `EXACTLY/AT_MOST` 限制。超出底部的内容可能被裁剪；FlowLayout 本身不滚动。需要滚动时可放入合适的滚动容器，并验证 `UNSPECIFIED` 高度测量。

## 8. 测试策略

推荐把尺寸明确的测试 View 加入容器，在 Robolectric 或 instrumented test 中调用 `measure()`、`layout()` 后断言边界。以下伪代码展示核心场景；具体测试 runner 依项目配置选择。

```kotlin
private fun exact(size: Int): Int = View.MeasureSpec.makeMeasureSpec(
    size,
    View.MeasureSpec.EXACTLY
)

private fun atMost(size: Int): Int = View.MeasureSpec.makeMeasureSpec(
    size,
    View.MeasureSpec.AT_MOST
)

@Test
fun wrapsSecondChildWhenLineIsFull() {
    val flow = FlowLayout(context).apply {
        horizontalSpacing = 10
        verticalSpacing = 6
        setPadding(5, 7, 5, 7)
    }
    flow.addView(FixedSizeView(context, 60, 20))
    flow.addView(FixedSizeView(context, 50, 30))

    flow.measure(exact(120), atMost(200))
    flow.layout(0, 0, flow.measuredWidth, flow.measuredHeight)

    val first = flow.getChildAt(0)
    val second = flow.getChildAt(1)
    assertEquals(7, first.top)
    assertEquals(first.bottom + 6, second.top)
    assertEquals(7 + 20 + 6 + 30 + 7, flow.measuredHeight)
}
```

测试辅助 View 可按给定期望尺寸解析规格：

```kotlin
class FixedSizeView(
    context: Context,
    private val desiredWidth: Int,
    private val desiredHeight: Int
) : View(context) {
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(
            resolveSize(desiredWidth, widthMeasureSpec),
            resolveSize(desiredHeight, heightMeasureSpec)
        )
    }
}
```

至少覆盖以下矩阵：

| 场景 | 关键断言 |
|---|---|
| 空容器 + padding | 尺寸为 padding/suggested minimum，不含间距 |
| 一行刚好放下 | 不换行，行间距为 0 |
| 加 spacing 后放不下 | 在正确元素前换行 |
| margin 导致换行 | margin 被计入测量和坐标 |
| `breakLine` | 非首项另起一行，不产生空首行 |
| `GONE` / `INVISIBLE` | 前者不占位，后者占位 |
| `AT_MOST` 宽高 | wrap_content 不超过父上限 |
| `UNSPECIFIED` 宽 | 所有普通孩子保持同一行 |
| 超宽单项 | 无死循环，尺寸和裁剪契约一致 |
| RTL | 首项贴右侧起点，margin 与换行不变 |
| 动态改 spacing | `requestLayout()` 后重新测量布局 |
| 复制 LayoutParams | margin 与 `breakLine` 都保留 |

验证 RTL 时可设置：

```kotlin
flow.layoutDirection = View.LAYOUT_DIRECTION_RTL
```

并断言第一个孩子的 `right` 靠近 `flow.width - flow.paddingRight`，第二个孩子位于它左侧。不要只比较截图；边界断言能更快指出 margin、spacing 还是方向游标出了问题。

> **无障碍提示**：标签若可点击，应保持足够触摸尺寸、清晰的文本或 `contentDescription`，并让逻辑子 View 顺序与视觉阅读顺序一致。FlowLayout 只负责几何排列，不应吞掉子 View 的点击事件。

## 9. 常见陷阱

1. **只在 `onLayout()` 换行**：父测得一行高度，实际却摆成多行，底部被裁切。
2. **忘记提交最后一行**：单行高度变为 0，多行丢最后一行。
3. **间距算在行首/行尾**：`wrap_content` 比视觉内容多出一截。
4. **忽略 margin**：测量认为放得下，布局后实际重叠或越界。
5. **把 `UNSPECIFIED` size=0 当上限**：所有孩子被错误换行。
6. **超宽孩子前创建空行**：只有当前行非空时才允许换行。
7. **测量与布局使用不同条件**：高度、行数和真实坐标不一致。
8. **RTL 只反转列表**：margin、起始 padding 和焦点顺序仍可能错误；应反转坐标推进方向。
9. **每帧创建行集合**：标签较多时造成不必要分配；除非高级对齐确实需要缓存。
10. **用 FlowLayout 承载海量元素**：它不回收子 View，数据量大时应使用虚拟化容器。

## 实践检查清单

- [ ] 明确定义 `GONE`、间距、margin、超宽项和强制换行语义。
- [ ] `onMeasure()` 与 `onLayout()` 使用同一换行公式。
- [ ] 宽度 `UNSPECIFIED` 时不错误换行。
- [ ] 汇总 suggested minimum 与 measured state。
- [ ] 覆盖完整的自定义 LayoutParams 生成链。
- [ ] spacing setter 校验输入并调用 `requestLayout()`。
- [ ] LTR 与 RTL 使用正确的游标和物理 margin。
- [ ] 空容器、零可用宽、超宽项不会产生负尺寸或死循环。
- [ ] 自动化测试覆盖尺寸、坐标、换行和动态变化。
- [ ] 海量数据场景评估 RecyclerView 或虚拟化实现。

## 小结

一个可用的 FlowLayout 需要让测量与布局共享同一套行划分语义：先把子尺寸、margin 与相邻间距组成候选宽度，超出上限时提交旧行，最后再提交尾行。完整 LayoutParams 生成链保证动态和 XML 场景一致，双向游标保证 RTL 正确，边界测试则把“看起来能用”提升为可维护的组件契约。

## 延伸阅读

- [创建自定义 ViewGroup](https://developer.android.com/develop/ui/views/layout/custom-views/custom-components#custom-viewgroup)
- [ViewGroup API](https://developer.android.com/reference/android/view/ViewGroup)
- [支持 RTL 布局](https://developer.android.com/training/basics/supporting-devices/languages)
- [测试 Android 应用](https://developer.android.com/training/testing)
