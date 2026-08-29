# 触摸事件分发机制

## 学习目标

- 建立从 `Activity`、`Window`、`ViewGroup` 到 `View` 的完整事件路径。
- 区分 `dispatchTouchEvent()`、`onInterceptTouchEvent()` 与 `onTouchEvent()` 的职责。
- 理解为什么 `ACTION_DOWN` 的返回值决定一整条手势序列的归属。
- 正确处理父容器中途拦截产生的 `ACTION_CANCEL`。
- 用日志和状态清理验证自定义控件的分发行为。

## 为什么“每个回调都收到了事件”仍然会出错

一次触摸不是互不相关的若干 `MotionEvent`，而是从 `ACTION_DOWN` 开始，到
`ACTION_UP` 或 `ACTION_CANCEL` 结束的**手势序列**（gesture stream）。系统为序列选择
一个触摸目标（touch target），后续事件通常沿同一路径送达。若只关心单个 `MOVE`，很容易
出现首帧跳变、子控件突然失去事件、按压态无法复位等问题。

`MotionEvent` 是平台类型 `android.view.MotionEvent`；本章所述基础分发 API 自 API 1
即可用，个别辅助 API 会单独标注。

## 三层职责

### `dispatchTouchEvent()`：路由

`Activity.dispatchTouchEvent()` 把事件交给窗口；窗口中的装饰视图最终让 View 树开始分发。
自定义 `ViewGroup` 可以重写 `dispatchTouchEvent()` 做观测或非常规路由，但通常不应复制
框架的目标管理逻辑。自定义 `View` 重写它也要谨慎：监听器调用顺序、禁用状态和点击语义
都由基类实现维护。

### `onInterceptTouchEvent()`：父容器是否截获

只有 `ViewGroup` 有该回调。返回 `true` 表示父容器希望由自己的 `onTouchEvent()` 处理；
返回 `false` 表示继续向命中的子树派发。典型策略是：`DOWN` 不拦截，移动超过阈值且方向
明确后再拦截。

### `onTouchEvent()`：目标消费

目标 View 在这里推进自己的手势状态。返回 `true` 表示消费当前事件。最关键的是
`ACTION_DOWN`：若一个 View 对 `DOWN` 返回 `false`，它通常不会成为本序列的触摸目标，
后续 `MOVE/UP` 不会再回来“补问”。

```text
InputDispatcher
      |
Activity.dispatchTouchEvent
      |
Window / DecorView
      |
Root ViewGroup.dispatchTouchEvent
      |-- onInterceptTouchEvent == true --> ViewGroup.onTouchEvent
      |
      `-- false --> Child.dispatchTouchEvent
                         |-- OnTouchListener.onTouch（先）
                         `-- View.onTouchEvent（监听器未消费时）
```

> **注意**：`View.OnTouchListener` 仅在 View 处于 enabled 状态时由
> `View.dispatchTouchEvent()` 调用。监听器返回 `true` 会阻止 `onTouchEvent()` 接收该事件。
> 不要同时在两处维护两套手势状态。

## `DOWN` 如何建立目标

以父容器 P 和子 View C 为例：

```text
时间       P.dispatch       P.intercept       C.dispatch / touch
DOWN  ---> 进入 ----------> false ----------> C.onTouchEvent = true
MOVE  ---> 已记录 C -------> false ----------> C.onTouchEvent = true
UP    ---> 已记录 C -------> false ----------> C.onTouchEvent = true
                                               序列结束，目标清空
```

若 C 对 `DOWN` 返回 `false`，分发会回退给 P 的 `onTouchEvent()`。P 若也返回 `false`，这条
序列在当前 View 树中无人处理。后续事件不会因某个控件后来“感兴趣”而重新命中。

命中测试使用父容器坐标，派发给子 View 时框架会转换坐标。不要缓存
`event.x/event.y` 并误当作屏幕坐标；跨 View 比较位置时应明确使用局部坐标或通过
`getLocationOnScreen()` 转换。

## 中途拦截与 `ACTION_CANCEL`

父容器可以先把 `DOWN` 给子控件，待移动超过阈值后决定滚动。此时框架必须终止子控件正在
进行的序列，因此向子控件发送 `ACTION_CANCEL`；导致取消的原始 `MOVE` 由父容器处理。

```text
事件        父容器判断                  子控件                    父容器处理
DOWN        不拦截  -------------------> DOWN
MOVE(小)    不拦截  -------------------> MOVE
MOVE(大)    拦截    -------------------> CANCEL
                `---------------------------------------------> MOVE
MOVE/UP     已由父容器接管 -----------------------------------> MOVE/UP
```

`CANCEL` 与 `UP` 都是终态，但语义不同：`UP` 可以确认点击、提交拖动；`CANCEL` 只能回滚或
停止。窗口失焦、系统手势接管、父容器拦截等都可能产生取消。

### 拦截一旦发生，整条序列不再重复询问

`ViewGroup.dispatchTouchEvent()` 只有在“`ACTION_DOWN` 或已有触摸目标”时才会调用
`onInterceptTouchEvent()`。一旦父容器在 `DOWN` 返回 `true`，子 target 收到 `CANCEL` 并从
链表移除，`mFirstTouchTarget` 置空；后续 `MOVE/UP` 到达时既不满足 `DOWN` 也没有目标，直接
走父容器自身的 `onTouchEvent()`，不再询问是否拦截。也就是说，“拦截”是一次决策，整条序列生效：

```text
场景 A：DOWN 就被拦截
DOWN : onInterceptTouchEvent = true
       -> 子 target 收到 CANCEL，mFirstTouchTarget 置空
       -> 父容器 onTouchEvent 消费 DOWN
MOVE : 不是 DOWN 且 mFirstTouchTarget == null
       -> 跳过 onInterceptTouchEvent，直接父容器 onTouchEvent
UP   : 同上，父容器 onTouchEvent 结束序列

场景 B：DOWN 放行，MOVE 才拦截
DOWN : onInterceptTouchEvent = false -> 记录子 target
MOVE : onInterceptTouchEvent = true
       -> 子 target 收到 CANCEL，mFirstTouchTarget 置空
       -> 父容器 onTouchEvent 消费本次 MOVE
后续 : 同场景 A，不再询问 onInterceptTouchEvent
```

最小验证容器：在 `DOWN` 拦截，日志应只有一条 `intercept` 记录，其余事件全部落在
`onTouchEvent`：

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.util.Log
import android.view.MotionEvent
import android.view.ViewGroup

/** 平台 API：ViewGroup、MotionEvent、Log。 */
class InterceptOnceGroup @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : ViewGroup(context, attrs) {

    override fun onInterceptTouchEvent(ev: MotionEvent): Boolean {
        // 拦截后 MOVE/UP 不会再进入本回调
        Log.d("InterceptOnce", "intercept ${ev.actionName()} 被调用")
        return ev.actionMasked == MotionEvent.ACTION_DOWN
    }

    override fun onTouchEvent(ev: MotionEvent): Boolean {
        Log.d("InterceptOnce", "onTouchEvent ${ev.actionName()} 接管")
        return true // 消费整条序列
    }

    // 空容器，仅演示分发；无需布局子 View
    override fun onLayout(
        changed: Boolean, l: Int, t: Int, r: Int, b: Int,
    ) = Unit

    private fun MotionEvent.actionName(): String = when (actionMasked) {
        MotionEvent.ACTION_DOWN -> "DOWN"
        MotionEvent.ACTION_MOVE -> "MOVE"
        MotionEvent.ACTION_UP -> "UP"
        MotionEvent.ACTION_CANCEL -> "CANCEL"
        else -> actionMasked.toString()
    }
}
```

下面的 `DragHandleView` 从子 View 一侧处理同一条序列的 DOWN/MOVE/UP/CANCEL：

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import kotlin.math.hypot

/** 平台 API：View、MotionEvent（API 1）。 */
class DragHandleView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var downX = 0f
    private var downY = 0f
    private var dragging = false
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop.toFloat()

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                dragging = false
                isPressed = true
                parent?.requestDisallowInterceptTouchEvent(false)
                return true // 声明接收这一整条序列
            }
            MotionEvent.ACTION_MOVE -> {
                dragging = hypot(event.x - downX, event.y - downY) > touchSlop
                // 更新预览位置；不要在此确认业务操作
                return true
            }
            MotionEvent.ACTION_UP -> {
                val wasClick = !dragging
                resetGesture()
                if (wasClick) performClick()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                resetGesture() // 不调用 performClick，不提交拖动
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick() // 保留点击监听与无障碍事件
        return true
    }

    private fun resetGesture() {
        isPressed = false
        dragging = false
    }
}
```

> **无障碍提示**：触摸点击最终调用 `performClick()`，并在重写中调用
> `super.performClick()`。这让 `OnClickListener`、键盘点击和无障碍服务共享同一语义。

## 一个可观测但不篡改路由的容器

调试时应记录 `actionMasked`、目标类名和返回值，而不是只打印进入回调。下面的容器保留
`super` 的真实分发行为：

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.util.Log
import android.view.MotionEvent
import android.widget.FrameLayout

/** 平台 API：FrameLayout、MotionEvent、Log。 */
class DispatchTraceLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : FrameLayout(context, attrs) {

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        val handled = super.dispatchTouchEvent(ev)
        Log.d("DispatchTrace", "dispatch ${ev.actionName()} -> $handled")
        return handled
    }

    override fun onInterceptTouchEvent(ev: MotionEvent): Boolean {
        val intercepted = super.onInterceptTouchEvent(ev)
        Log.d("DispatchTrace", "intercept ${ev.actionName()} -> $intercepted")
        return intercepted
    }

    private fun MotionEvent.actionName(): String = when (actionMasked) {
        MotionEvent.ACTION_DOWN -> "DOWN"
        MotionEvent.ACTION_MOVE -> "MOVE"
        MotionEvent.ACTION_UP -> "UP"
        MotionEvent.ACTION_CANCEL -> "CANCEL"
        MotionEvent.ACTION_POINTER_DOWN -> "POINTER_DOWN"
        MotionEvent.ACTION_POINTER_UP -> "POINTER_UP"
        else -> actionMasked.toString()
    }
}
```

日志中的顺序比某一行返回值更重要。尤其要确认：谁消费了 `DOWN`、父容器何时首次返回
`true`、子控件是否收到 `CANCEL`、终态后状态是否清空。

## `requestDisallowInterceptTouchEvent()` 的边界

子 View 可调用 `parent.requestDisallowInterceptTouchEvent(true)` 请求祖先暂不拦截。请求会
沿父链传播，常用于子控件已判定自己正在水平拖动时。但它不是永久锁：新的 `DOWN` 会重置
相关状态，而且父容器仍能在 `dispatchTouchEvent()` 层做特殊处理。正常控件应遵守该请求，
子控件也应只在手势意图明确时提出，结束后恢复为 `false`。

机制上，请求落实为 `ViewGroup` 的内部标志 `FLAG_DISALLOW_INTERCEPT`：置位后
`dispatchTouchEvent()` 中 `disallowIntercept = true`，直接跳过 `onInterceptTouchEvent()`。
但 `ACTION_DOWN` 进入容器时框架会先执行 `resetTouchState()`，无条件清除
`FLAG_DISALLOW_INTERCEPT`（AOSP `ViewGroup` 行为）。因此：

- 请求只对**当前一条手势序列**有效，下一次 `DOWN` 到来即失效，必须重新请求；
- 子 View 应在 `DOWN` 回调里建立请求，而不是只在首次手势时设置一次。

```text
手势序列 1                      手势序列 2
DOWN -> 子请求 disallow         DOWN -> resetTouchState() 清除标志
MOVE -> 父不拦截（标志生效）     子未重新请求 -> 父可正常询问拦截
UP   -> 序列结束
```

`DragHandleView` 示例中在 `DOWN` 里调用 `requestDisallowInterceptTouchEvent(false)` 是在
复位上一次的占用：即使不显式复位，下一条 `DOWN` 也会自动清除该标志。

## 常见陷阱

1. **在 `MOVE` 才返回 true**：由于 `DOWN` 未消费，控件通常根本收不到该 `MOVE`。
2. **父容器在 `DOWN` 就拦截**：子控件失去点击机会，也无法根据方向协商冲突。
3. **忽略 `CANCEL`**：按压态、拖动标记、速度追踪器或动画一直残留。
4. **监听器和 `onTouchEvent()` 双写状态**：监听器的返回值改变后，事件链会断在不同位置。
5. **直接调用 `onTouchEvent()` 转发**：绕过命中、坐标变换、监听器与目标管理；应使用
   `dispatchTouchEvent()`，多数时候更应交给 `super`。
6. **把 `ACTION_POINTER_UP` 当成序列结束**：它只表示某个非最后手指抬起。

## 实践检查清单

- [ ] `DOWN` 的消费方明确，并能解释后续事件为何到达它。
- [ ] `UP` 和 `CANCEL` 都释放按压态、追踪器和临时资源。
- [ ] 父容器只在意图明确后拦截，并用 `touchSlop` 抑制抖动。
- [ ] 点击路径调用 `performClick()`，取消路径不提交业务操作。
- [ ] 日志同时记录动作、回调层级和返回值。
- [ ] 多指动作使用 `actionMasked`，不直接比较编码后的 `action`。

## 小结

分发不是“事件冒泡”，而是从 `DOWN` 建立目标、在同一序列中维持归属，必要时以
`CANCEL` 完成所有权转移。`dispatchTouchEvent()` 负责路由，
`onInterceptTouchEvent()` 负责父容器决策，`onTouchEvent()` 负责消费。只要先明确序列所有权
和终态清理，大多数事件丢失问题都能被系统化定位。

## 延伸阅读

- [Manage touch events in a ViewGroup](https://developer.android.com/develop/ui/views/touch-and-input/gestures/viewgroup)
- [View#dispatchTouchEvent](https://developer.android.com/reference/android/view/View#dispatchTouchEvent(android.view.MotionEvent))
- [MotionEvent](https://developer.android.com/reference/android/view/MotionEvent)
