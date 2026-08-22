# 测量子 View：把父约束翻译成子约束

自定义 `ViewGroup` 的测量不是“问一遍子 View 有多大”，而是一次约束协商：父容器收到上层给出的 `MeasureSpec`，结合自己的内边距、子 View 的 `LayoutParams` 与外边距，为每个孩子生成新的 `MeasureSpec`，最后再把所有结果汇总成自己的尺寸。

## 学习目标

- 理解 `MeasureSpec`、`LayoutParams` 与父容器可用空间之间的关系。
- 能推导 `getChildMeasureSpec()` 对 `MATCH_PARENT`、`WRAP_CONTENT` 和固定尺寸的处理。
- 正确使用 `measureChildWithMargins()`，避免漏算 padding、margin 与已占空间。
- 会传播测量状态（measured state），而不只读取 `measuredWidth`。
- 能识别重复测量、错误规格与尺寸溢出等常见问题。

## 1. 测量是一棵向下约束、向上汇总的树

上层只给当前容器两个压缩后的整数：`widthMeasureSpec` 和 `heightMeasureSpec`。每个规格由模式（mode）和尺寸（size）组成：

- `EXACTLY`：必须采用给定尺寸，常见于固定值或上层已经确定的 `MATCH_PARENT`。
- `AT_MOST`：不能超过给定尺寸，常见于 `WRAP_CONTENT`。
- `UNSPECIFIED`：上层不施加该方向的上限，滚动容器内部较常见。

```text
祖先 MeasureSpec
       │
       ▼
┌─────────────────────────────┐
│ 自定义 ViewGroup.onMeasure  │
│  1. 扣除 padding / 已占空间 │
│  2. 读取 child LayoutParams │
│  3. 生成 child MeasureSpec  │
└──────────────┬──────────────┘
               │ 向下传约束
               ▼
        child.measure(...)
               │ 向上返回
               ▼
 measuredWidth / measuredHeight / measuredState
               │
               ▼
     resolveSizeAndState()
```

> **注意**：`MeasureSpec` 的 size 是约束边界，不等于内容天然想要的大小。把 `MeasureSpec.getSize()` 无条件当成最终尺寸，会让 `WRAP_CONTENT` 退化为占满父容器。

## 2. `getChildMeasureSpec()` 如何完成约束翻译

`ViewGroup.getChildMeasureSpec(parentSpec, padding, childDimension)` 的三个输入分别是：

1. 父方向上的 `MeasureSpec`；
2. 该方向已不能给孩子使用的空间，例如父 padding、子 margin、前序元素占用；
3. 子 `LayoutParams` 中对应的 `width` 或 `height`。

概念上先计算：

```text
available = max(0, parentSize - padding)
```

再根据父模式与子尺寸组合产生子规格。下面是常用组合的结果摘要：

| 父规格 | 子固定尺寸 `n` | 子 `MATCH_PARENT` | 子 `WRAP_CONTENT` |
|---|---|---|---|
| `EXACTLY(P)` | `EXACTLY(n)` | `EXACTLY(available)` | `AT_MOST(available)` |
| `AT_MOST(P)` | `EXACTLY(n)` | `AT_MOST(available)` | `AT_MOST(available)` |
| `UNSPECIFIED` | `EXACTLY(n)` | `UNSPECIFIED(0)`* | `UNSPECIFIED(0)`* |

`*` 实际 size 还会受平台兼容行为影响；算法应依赖 mode 语义，不要依赖 `UNSPECIFIED` 中的 size。

这里有两个容易误解的点：

- 子 View 声明固定尺寸时，父容器通常会生成 `EXACTLY(n)`；固定尺寸表达的是子 View 的布局契约。
- 当父容器自己只是 `AT_MOST` 时，它尚未确定最终大小，因此子 View 的 `MATCH_PARENT` 不能凭空得到一个确定结果，通常仍是 `AT_MOST`。部分系统容器会在父尺寸确定后进行第二次测量来兑现 `MATCH_PARENT`。

以下代码演示一个只容纳单个子 View 的容器如何直接生成规格：

```kotlin
import android.content.Context
import android.util.AttributeSet
import android.view.View
import android.view.ViewGroup

class SingleChildLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : ViewGroup(context, attrs, defStyleAttr) {

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val child = (0 until childCount)
            .map(::getChildAt)
            .firstOrNull { it.visibility != View.GONE }

        if (child == null) {
            setMeasuredDimension(
                resolveSize(suggestedMinimumWidth, widthMeasureSpec),
                resolveSize(suggestedMinimumHeight, heightMeasureSpec)
            )
            return
        }

        val lp = child.layoutParams as MarginLayoutParams
        val horizontalUsed = paddingLeft + paddingRight +
            lp.leftMargin + lp.rightMargin
        val verticalUsed = paddingTop + paddingBottom +
            lp.topMargin + lp.bottomMargin

        val childWidthSpec = getChildMeasureSpec(
            widthMeasureSpec,
            horizontalUsed,
            lp.width
        )
        val childHeightSpec = getChildMeasureSpec(
            heightMeasureSpec,
            verticalUsed,
            lp.height
        )
        child.measure(childWidthSpec, childHeightSpec)

        val desiredWidth = maxOf(
            suggestedMinimumWidth,
            paddingLeft + paddingRight + lp.leftMargin +
                child.measuredWidth + lp.rightMargin
        )
        val desiredHeight = maxOf(
            suggestedMinimumHeight,
            paddingTop + paddingBottom + lp.topMargin +
                child.measuredHeight + lp.bottomMargin
        )
        val state = child.measuredState

        setMeasuredDimension(
            resolveSizeAndState(desiredWidth, widthMeasureSpec, state),
            resolveSizeAndState(
                desiredHeight,
                heightMeasureSpec,
                state shl MEASURED_HEIGHT_STATE_SHIFT
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
        for (index in 0 until childCount) {
            val child = getChildAt(index)
            if (child.visibility == View.GONE) continue
            val lp = child.layoutParams as MarginLayoutParams
            val childLeft = paddingLeft + lp.leftMargin
            val childTop = paddingTop + lp.topMargin
            child.layout(
                childLeft,
                childTop,
                childLeft + child.measuredWidth,
                childTop + child.measuredHeight
            )
        }
    }

    override fun generateDefaultLayoutParams(): LayoutParams =
        MarginLayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT)

    override fun generateLayoutParams(attrs: AttributeSet): LayoutParams =
        MarginLayoutParams(context, attrs)

    override fun generateLayoutParams(params: LayoutParams): LayoutParams =
        when (params) {
            is MarginLayoutParams -> MarginLayoutParams(params)
            else -> MarginLayoutParams(params)
        }

    override fun checkLayoutParams(params: LayoutParams): Boolean =
        params is MarginLayoutParams
}
```

## 3. `measureChildWithMargins()`：少写重复而危险的算术

当容器支持 margin 时，优先使用：

```kotlin
measureChildWithMargins(
    child,
    parentWidthMeasureSpec,
    widthUsed,
    parentHeightMeasureSpec,
    heightUsed
)
```

它会读取孩子的 `MarginLayoutParams`，把父 padding、子 margin 和 `widthUsed`/`heightUsed` 一并作为已用空间，再调用 `getChildMeasureSpec()`。前提是容器确实返回 `MarginLayoutParams` 或其子类；否则会发生类型转换异常。

`widthUsed`、`heightUsed` 不是孩子的 margin，也不是父 padding。它们表示除这些常规占用外，当前算法还要保留的空间。例如横向线性容器测量第 3 个孩子时，可以把前两个孩子已经占用的宽度作为 `widthUsed`。而 FlowLayout 每个孩子只受整行宽度上限约束，通常传 `0`，再由容器自行决定是否换行。

```kotlin
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
}
```

> **性能提示**：不要为了“保险”连续调用两次 `child.measure()`。测量可能触发文字排版、图片尺寸计算等工作。只有算法真的依赖第一次结果来确定第二次精确规格时，才进行第二轮测量，并记录为什么需要它。

## 4. 汇总尺寸时不要丢掉测量状态

`getMeasuredWidthAndState()` 与 `getMeasuredHeightAndState()` 的高位包含状态位。最常见的是 `MEASURED_STATE_TOO_SMALL`：子 View 接受了尺寸，但希望告诉上层“空间小于期望”。直接累加 `measuredWidth` 不会自动把这个信号传回祖先。

标准汇总模式如下：

```kotlin
var childState = 0
var maxChildWidth = 0
var totalHeight = 0

for (index in 0 until childCount) {
    val child = getChildAt(index)
    if (child.visibility == View.GONE) continue

    measureChildWithMargins(child, widthMeasureSpec, 0, heightMeasureSpec, 0)
    val lp = child.layoutParams as ViewGroup.MarginLayoutParams

    maxChildWidth = maxOf(
        maxChildWidth,
        child.measuredWidth + lp.leftMargin + lp.rightMargin
    )
    totalHeight += child.measuredHeight + lp.topMargin + lp.bottomMargin
    childState = combineMeasuredStates(childState, child.measuredState)
}

val desiredWidth = maxOf(
    suggestedMinimumWidth,
    paddingLeft + paddingRight + maxChildWidth
)
val desiredHeight = maxOf(
    suggestedMinimumHeight,
    paddingTop + paddingBottom + totalHeight
)

setMeasuredDimension(
    resolveSizeAndState(desiredWidth, widthMeasureSpec, childState),
    resolveSizeAndState(
        desiredHeight,
        heightMeasureSpec,
        childState shl View.MEASURED_HEIGHT_STATE_SHIFT
    )
)
```

为什么高度要左移？`child.measuredState` 同时编码宽、高两个方向的状态；`resolveSizeAndState()` 的第三个参数期望当前方向的状态位。平台约定通过 `MEASURED_HEIGHT_STATE_SHIFT` 把高度状态移动到对应位置。

还要把 `suggestedMinimumWidth` / `suggestedMinimumHeight` 纳入期望尺寸。它们不仅来自 `minWidth`、`minHeight`，还可能来自背景 Drawable 的最小尺寸。

## 5. 测量顺序与多轮测量

简单容器可以一次遍历完成，但以下情况往往需要明确的第二阶段：

- 父容器是 `WRAP_CONTENT`，子 View 又要求在某方向 `MATCH_PARENT`；
- 多列布局需要先找到列宽，再用精确列宽重测孩子；
- 宽度决定文字折行，而文字折行后的高度又决定整行高度；
- 权重（weight）布局要先测非权重项，再分配剩余空间。

```text
第一轮：获取天然需求 / 固定项尺寸
           │
           ▼
      计算父最终尺寸与剩余空间
           │
           ▼
第二轮：只重测依赖最终结果的孩子
           │
           ▼
      汇总状态并 setMeasuredDimension
```

第二轮应使用新的、可解释的规格，而不是机械重复第一次调用。若容器对孩子测量结果有缓存，也必须在 `requestLayout()`、LayoutParams 变化或规格变化时失效。

## 6. 常见陷阱

1. **忽略 `GONE`**：`GONE` 子 View 通常既不测量也不占布局空间；`INVISIBLE` 仍需占空间。
2. **把 margin 计两次**：使用 `measureChildWithMargins()` 后，又把 margin 传进 `widthUsed`，会让约束过小。
3. **忘记父 padding**：手写 `MeasureSpec.makeMeasureSpec()` 时尤其常见。
4. **给负数可用空间**：扣减后应以 0 为下限；框架辅助方法会处理，手写算法也要处理。
5. **强制采用父 size**：无论 mode 都 `setMeasuredDimension(size, size)`，会破坏 `WRAP_CONTENT` 和 `UNSPECIFIED`。
6. **漏掉最小尺寸与状态**：背景被裁切、上层收不到 `TOO_SMALL` 信号。
7. **测量阶段修改子树**：在 `onMeasure()` 中频繁 add/remove View 或改 LayoutParams，容易触发新的布局请求和抖动。
8. **把测量尺寸当最终坐标**：`measuredWidth` 是测量结果，真正位置应在 `onLayout()` 中通过 `layout()` 确定。

> **无障碍提示**：尺寸过小不仅是视觉问题。可点击目标应留出足够触摸区域；若视觉元素必须很小，可由父容器设置 `TouchDelegate` 扩大命中范围，但不要制造相互重叠、难以预测的点击区域。

## 实践检查清单

- [ ] 对 `EXACTLY`、`AT_MOST`、`UNSPECIFIED` 都有明确处理。
- [ ] `MATCH_PARENT`、`WRAP_CONTENT`、固定尺寸均经过测试。
- [ ] 支持 margin 时覆盖了 LayoutParams 生成链。
- [ ] padding、margin、间距和额外已占空间没有漏算或重复计算。
- [ ] 跳过 `GONE`，但保留 `INVISIBLE` 的空间。
- [ ] 汇总 `combineMeasuredStates()`，并正确移动高度状态。
- [ ] 使用 `resolveSizeAndState()` 与 suggested minimum。
- [ ] 只有算法需要时才二次测量。
- [ ] 测试了空容器、单个超大子 View、多子 View 和最小尺寸背景。

## 小结

子 View 测量的本质是约束翻译。`getChildMeasureSpec()` 负责把父规格、已占空间和子尺寸声明组合起来；`measureChildWithMargins()` 提供了支持 margin 的可靠默认实现；`combineMeasuredStates()` 与 `resolveSizeAndState()` 则完成结果和状态的向上传递。只要明确每个数字代表“上限、固定值还是已占空间”，复杂容器的测量就能从猜测变成可验证的算法。

## 延伸阅读

- [ViewGroup：自定义 ViewGroup](https://developer.android.com/develop/ui/views/layout/custom-views/custom-components#custom-viewgroup)
- [View.MeasureSpec API](https://developer.android.com/reference/android/view/View.MeasureSpec)
- [ViewGroup.getChildMeasureSpec](https://developer.android.com/reference/android/view/ViewGroup#getChildMeasureSpec(int,int,int))
- [ViewGroup.measureChildWithMargins](https://developer.android.com/reference/android/view/ViewGroup#measureChildWithMargins(android.view.View,int,int,int,int))
