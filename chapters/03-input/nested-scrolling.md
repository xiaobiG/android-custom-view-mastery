# 嵌套滑动协议

## 学习目标

- 理解嵌套滑动（nested scrolling）不是事件转发，而是滚动增量协商。
- 掌握 pre-scroll、自消费、post-scroll 三阶段。
- 区分触摸与非触摸两类滚动。
- 实现 AndroidX `NestedScrollingChild3` 与 `NestedScrollingParent3`。
- 正确处理 consumed 数组、窗口偏移、开始与停止协议。

## 为什么拦截机制不够

传统触摸分发要求一条序列主要由一个目标处理。但协同滚动常希望同一帧的位移由多个层级
分摊：AppBar 先折叠 20 px，列表再滚 30 px；列表到顶后，下拉剩余量交给刷新容器。若靠
中途拦截，子控件收到 `CANCEL`，很难连续传递速度和剩余距离。

嵌套滑动不改变 `MotionEvent` 的目标。子控件仍处理事件，只是把计算出的 `dx/dy` 通过
AndroidX Core 协议与祖先协商。

```text
触摸事件 -> NestedScrollingChild 计算 dy=50
                     |
                     | dispatchNestedPreScroll(50)
                     v
              Parent 预消费 20
                     |
                     v
              Child 消费 25
                     |
                     | dispatchNestedScroll(
                     |   childConsumed=25,
                     |   childUnconsumed=5)
                     v
              Parent 后消费剩余 5

总账：20 + 25 + 5 = 50
```

## 协议生命周期

一次嵌套滚动有明确的握手与终止：

```text
Child                       Parent
  | startNestedScroll         |
  |-------------------------->| onStartNestedScroll: 是否接受轴/类型
  |<--------------------------| true
  |                            | onNestedScrollAccepted
  | dispatchNestedPreScroll -->| 预消费
  | 本地消费                   |
  | dispatchNestedScroll ----->| 后消费未消费量
  | ... 每帧重复               |
  | stopNestedScroll --------->| onStopNestedScroll
```

轴使用 `ViewCompat.SCROLL_AXIS_HORIZONTAL` / `SCROLL_AXIS_VERTICAL`；类型使用
`ViewCompat.TYPE_TOUCH` 与 `ViewCompat.TYPE_NON_TOUCH`。这些常量与下文接口均来自
AndroidX Core，不是平台 `View` API。

- `TYPE_TOUCH`：手指拖动期间。
- `TYPE_NON_TOUCH`：fling、程序滚动等不由当前手指直接驱动的阶段。

一个 View 可同时存在两类嵌套滚动，因此停止时必须传入对应 type。

## 三阶段记账

假设子控件准备按 `dy` 滚动：

1. **pre-scroll**：祖先先消费，例如折叠工具栏。
2. **child consume**：子控件消费剩余量，受自身边界约束。
3. **post-scroll**：把子已消费与仍未消费量报告给祖先，例如触发下拉或边缘反馈。

`consumed[0]` 是 x，`consumed[1]` 是 y。数组是累加账本，不要把祖先写入值误当成新的总位移。
`NestedScrollingChild3.dispatchNestedScroll(..., consumed)` 的最后一个数组允许祖先报告它在
post 阶段继续消费了多少。

> **注意**：整数像素协议会产生浮点余数。手势计算若使用 Float，应保留 remainder，下一帧
> 再与新 delta 合并，避免慢速拖动的亚像素位移永久丢失。

## 实现 `NestedScrollingChild3`

下面的纵向 View 展示完整的 Child3 委托和每帧流水线。需要依赖
`androidx.core:core-ktx`（版本由项目依赖目录统一管理）。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.view.NestedScrollingChild3
import androidx.core.view.NestedScrollingChildHelper
import androidx.core.view.ViewCompat

class NestedPanView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs), NestedScrollingChild3 {

    private val childHelper = NestedScrollingChildHelper(this)
    private val parentConsumed = IntArray(2)
    private val parentOffset = IntArray(2)
    private val postConsumed = IntArray(2)

    private var lastY = 0f
    private var nestedYOffset = 0
    private var contentY = 0
    private var maxContentY = 0

    init {
        isNestedScrollingEnabled = true
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                lastY = event.y
                nestedYOffset = 0
                startNestedScroll(
                    ViewCompat.SCROLL_AXIS_VERTICAL,
                    ViewCompat.TYPE_TOUCH
                )
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                var dy = (lastY - event.y).toInt()

                parentConsumed.fill(0)
                parentOffset.fill(0)
                if (dispatchNestedPreScroll(
                        0, dy, parentConsumed, parentOffset,
                        ViewCompat.TYPE_TOUCH
                    )) {
                    dy -= parentConsumed[1]
                    // 祖先滚动可能使本 View 在窗口中移动，修正触摸锚点。
                    lastY = event.y - parentOffset[1]
                    nestedYOffset += parentOffset[1]
                } else {
                    lastY = event.y
                }

                val oldY = contentY
                contentY = (contentY + dy).coerceIn(0, maxContentY)
                val consumedByMe = contentY - oldY
                val unconsumed = dy - consumedByMe
                if (consumedByMe != 0) invalidate()

                parentOffset.fill(0)
                postConsumed.fill(0)
                dispatchNestedScroll(
                    0, consumedByMe,
                    0, unconsumed,
                    parentOffset,
                    ViewCompat.TYPE_TOUCH,
                    postConsumed
                )
                // 若继续以事件局部坐标计算，应累计 post 阶段的窗口移动。
                lastY -= parentOffset[1]
                nestedYOffset += parentOffset[1]
                return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                stopNestedScroll(ViewCompat.TYPE_TOUCH)
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    // NestedScrollingChild3 的 API 全部委托给 helper。
    override fun setNestedScrollingEnabled(enabled: Boolean) =
        childHelper.setNestedScrollingEnabled(enabled)

    override fun isNestedScrollingEnabled(): Boolean =
        childHelper.isNestedScrollingEnabled

    override fun startNestedScroll(axes: Int): Boolean =
        childHelper.startNestedScroll(axes)

    override fun startNestedScroll(axes: Int, type: Int): Boolean =
        childHelper.startNestedScroll(axes, type)

    override fun stopNestedScroll() = childHelper.stopNestedScroll()

    override fun stopNestedScroll(type: Int) = childHelper.stopNestedScroll(type)

    override fun hasNestedScrollingParent(): Boolean =
        childHelper.hasNestedScrollingParent()

    override fun hasNestedScrollingParent(type: Int): Boolean =
        childHelper.hasNestedScrollingParent(type)

    override fun dispatchNestedScroll(
        dxConsumed: Int,
        dyConsumed: Int,
        dxUnconsumed: Int,
        dyUnconsumed: Int,
        offsetInWindow: IntArray?
    ): Boolean = childHelper.dispatchNestedScroll(
        dxConsumed, dyConsumed, dxUnconsumed, dyUnconsumed, offsetInWindow
    )

    override fun dispatchNestedScroll(
        dxConsumed: Int,
        dyConsumed: Int,
        dxUnconsumed: Int,
        dyUnconsumed: Int,
        offsetInWindow: IntArray?,
        type: Int
    ): Boolean = childHelper.dispatchNestedScroll(
        dxConsumed, dyConsumed, dxUnconsumed, dyUnconsumed, offsetInWindow, type
    )

    override fun dispatchNestedScroll(
        dxConsumed: Int,
        dyConsumed: Int,
        dxUnconsumed: Int,
        dyUnconsumed: Int,
        offsetInWindow: IntArray?,
        type: Int,
        consumed: IntArray
    ) = childHelper.dispatchNestedScroll(
        dxConsumed, dyConsumed, dxUnconsumed, dyUnconsumed,
        offsetInWindow, type, consumed
    )

    override fun dispatchNestedPreScroll(
        dx: Int,
        dy: Int,
        consumed: IntArray?,
        offsetInWindow: IntArray?
    ): Boolean = childHelper.dispatchNestedPreScroll(dx, dy, consumed, offsetInWindow)

    override fun dispatchNestedPreScroll(
        dx: Int,
        dy: Int,
        consumed: IntArray?,
        offsetInWindow: IntArray?,
        type: Int
    ): Boolean = childHelper.dispatchNestedPreScroll(
        dx, dy, consumed, offsetInWindow, type
    )

    override fun dispatchNestedFling(
        velocityX: Float,
        velocityY: Float,
        consumed: Boolean
    ): Boolean = childHelper.dispatchNestedFling(velocityX, velocityY, consumed)

    override fun dispatchNestedPreFling(
        velocityX: Float,
        velocityY: Float
    ): Boolean = childHelper.dispatchNestedPreFling(velocityX, velocityY)

    override fun onDetachedFromWindow() {
        stopNestedScroll(ViewCompat.TYPE_TOUCH)
        stopNestedScroll(ViewCompat.TYPE_NON_TOUCH)
        super.onDetachedFromWindow()
    }
}
```

`offsetInWindow` 表示嵌套调用前后该 View 在窗口坐标中的位置变化，并非祖先消费量。若父容器
折叠导致子 View 位置改变而不修正触摸锚点，下一帧会把窗口移动误算成手指移动。

> **注意**：示例为突出协议而省略 `touchSlop`、活动 pointer ID 与 fling。生产控件应结合前
> 几章的状态机和多指处理。

## 实现 `NestedScrollingParent3`

父容器通过 `NestedScrollingParentHelper` 记录接受的轴。下面只在纵向接受，pre 阶段先折叠
头部，post 阶段在子控件到边界后继续展开或处理剩余量。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.View
import android.widget.FrameLayout
import androidx.core.view.NestedScrollingParent3
import androidx.core.view.NestedScrollingParentHelper
import androidx.core.view.ViewCompat

class CollapsingHeaderLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : FrameLayout(context, attrs), NestedScrollingParent3 {

    private val parentHelper = NestedScrollingParentHelper(this)
    private var collapse = 0
    private var maxCollapse = 0

    override fun onStartNestedScroll(
        child: View,
        target: View,
        axes: Int,
        type: Int
    ): Boolean = axes and ViewCompat.SCROLL_AXIS_VERTICAL != 0

    override fun onNestedScrollAccepted(
        child: View,
        target: View,
        axes: Int,
        type: Int
    ) = parentHelper.onNestedScrollAccepted(child, target, axes, type)

    override fun onStopNestedScroll(target: View, type: Int) =
        parentHelper.onStopNestedScroll(target, type)

    override fun onNestedPreScroll(
        target: View,
        dx: Int,
        dy: Int,
        consumed: IntArray,
        type: Int
    ) {
        // dy > 0：内容向上，优先折叠头部。
        if (dy > 0 && collapse < maxCollapse) {
            val used = dy.coerceAtMost(maxCollapse - collapse)
            setCollapse(collapse + used)
            consumed[1] += used // 必须累加，不能覆盖祖先已有账目
        }
    }

    override fun onNestedScroll(
        target: View,
        dxConsumed: Int,
        dyConsumed: Int,
        dxUnconsumed: Int,
        dyUnconsumed: Int,
        type: Int,
        consumed: IntArray
    ) {
        // dyUnconsumed < 0：子已到顶部，向下剩余量用于展开头部。
        if (dyUnconsumed < 0 && collapse > 0) {
            val used = dyUnconsumed.coerceAtLeast(-collapse) // 负数
            setCollapse(collapse + used)
            consumed[1] += used
        }
    }

    private fun setCollapse(value: Int) {
        collapse = value.coerceIn(0, maxCollapse)
        // 例如 translationY 或布局偏移；真实实现同步头部与内容位置。
        invalidate()
    }

    override fun getNestedScrollAxes(): Int = parentHelper.nestedScrollAxes

    override fun onNestedPreFling(
        target: View,
        velocityX: Float,
        velocityY: Float
    ): Boolean = false // 本容器不提前接管 fling

    override fun onNestedFling(
        target: View,
        velocityX: Float,
        velocityY: Float,
        consumed: Boolean
    ): Boolean = false // 本容器未另外启动 fling

    // Parent2/Parent 的旧签名转发到 typed 版本，兼容旧调用方。
    override fun onStartNestedScroll(child: View, target: View, axes: Int): Boolean =
        onStartNestedScroll(child, target, axes, ViewCompat.TYPE_TOUCH)

    override fun onNestedScrollAccepted(child: View, target: View, axes: Int) =
        onNestedScrollAccepted(child, target, axes, ViewCompat.TYPE_TOUCH)

    override fun onStopNestedScroll(target: View) =
        onStopNestedScroll(target, ViewCompat.TYPE_TOUCH)

    override fun onNestedPreScroll(
        target: View,
        dx: Int,
        dy: Int,
        consumed: IntArray
    ) = onNestedPreScroll(target, dx, dy, consumed, ViewCompat.TYPE_TOUCH)

    override fun onNestedScroll(
        target: View,
        dxConsumed: Int,
        dyConsumed: Int,
        dxUnconsumed: Int,
        dyUnconsumed: Int
    ) {
        val ignored = IntArray(2)
        onNestedScroll(
            target, dxConsumed, dyConsumed, dxUnconsumed, dyUnconsumed,
            ViewCompat.TYPE_TOUCH, ignored
        )
    }

    override fun onNestedScroll(
        target: View,
        dxConsumed: Int,
        dyConsumed: Int,
        dxUnconsumed: Int,
        dyUnconsumed: Int,
        type: Int
    ) {
        val ignored = IntArray(2)
        onNestedScroll(
            target, dxConsumed, dyConsumed, dxUnconsumed, dyUnconsumed,
            type, ignored
        )
    }
}
```

示例旧签名中临时数组只为教学清晰；生产代码应复用字段数组，避免滚动期间分配。

## fling 与 `TYPE_NON_TOUCH`

触摸 `UP` 后若要惯性滚动，先结束 `TYPE_TOUCH`，再以 `TYPE_NON_TOUCH` 开启新的嵌套会话。
可按以下顺序：

```text
UP
 |-- dispatchNestedPreFling(velocity)
 |      `-- true：祖先接管，不启动本地 fling
 |
 |-- 本地能否消费？
 |-- dispatchNestedFling(velocity, consumed=本地是否会 fling)
 |-- startNestedScroll(axes, TYPE_NON_TOUCH)
 `-- 每个 scroller 帧走 pre -> 本地 -> post
     动画结束时 stopNestedScroll(TYPE_NON_TOUCH)
```

`dispatchNestedPreFling/dispatchNestedFling` 没有 type 参数，是早期协议的一部分；真正逐帧分配
fling 位移时仍应使用 `TYPE_NON_TOUCH`。父容器不要把非触摸滚动误当成手指拖动，例如不要
在 fling 期间显示仅属于直接触摸的按压反馈。

## Child3 / Parent3 相比旧版本解决了什么

旧 post-scroll 只能报告子控件的 consumed/unconsumed，父亲消费剩余量后不易继续向更上层
精确记账。Parent3 的 `consumed` 数组允许当前父级累加 post 消费，Child3 则接收该数组，
从而让多层祖先保持守恒。

```text
Child3 未消费 30
   -> Parent3 A 消费 10，consumed += 10
      -> Parent3 B 再消费 15，consumed += 15
最终仍未消费 5 -> EdgeEffect / 忽略
```

一个同时作为 Parent3 与 Child3 的中间容器，需要先处理本层，再把剩余量继续向祖先分发；
它不能只实现接口而不转发，否则协议在该层断裂。

## 常见陷阱

1. **把嵌套滑动当 MotionEvent 转发**：协议传的是滚动增量和消费账目。
2. **忽略 `startNestedScroll()` 返回值**：没有祖先接受时仍假定数组被写入。
3. **复用数组前不清零**：上一帧 consumed 泄漏到下一帧。
4. **覆盖 consumed 而非累加**：多层父容器记账错误。
5. **忽略 offsetInWindow**：折叠布局时拖动跳变。
6. **fling 仍标成 TYPE_TOUCH**：父容器无法区分直接与非直接输入。
7. **动画结束忘记 stop**：祖先保留错误的嵌套状态。
8. **Parent 接受所有轴**：无关横向滚动也被截入协议。

> **性能提示**：`IntArray(2)` 应作为字段复用；嵌套回调发生在高频滚动路径，避免日志拼接、
> 对象分配和 `requestLayout()` 风暴。

## 实践检查清单

- [ ] 每次会话 start/stop 成对，触摸与非触摸 type 分开。
- [ ] 只接受控件真正支持的轴。
- [ ] 每帧按 pre、本地、post 顺序处理，消费总量守恒。
- [ ] consumed 数组使用前清零，父级用 `+=` 累加。
- [ ] View 在窗口中移动时使用 offsetInWindow 修正触摸锚点。
- [ ] fling 先询问 pre-fling，再以 TYPE_NON_TOUCH 逐帧协商。
- [ ] `UP`、`CANCEL`、动画结束和脱离窗口均停止对应会话。
- [ ] 多层 Parent3 场景验证最终未消费量与 EdgeEffect 行为。

## 小结

嵌套滑动把“谁拥有事件”转化为“每层消费多少位移”。Child3 发起会话，Parent3 按轴和类型
接受，随后每帧按 pre、本地、post 记账。正确区分 type、累加 consumed、处理窗口偏移并在
所有终态 stop，才能让工具栏、列表、刷新容器和边缘反馈在多层结构中连续协作。

## 延伸阅读

- [NestedScrollingChild3](https://developer.android.com/reference/androidx/core/view/NestedScrollingChild3)
- [NestedScrollingParent3](https://developer.android.com/reference/androidx/core/view/NestedScrollingParent3)
- [NestedScrollingChildHelper](https://developer.android.com/reference/androidx/core/view/NestedScrollingChildHelper)
- [Nested scrolling](https://developer.android.com/develop/ui/views/touch-and-input/gestures/scroll)
