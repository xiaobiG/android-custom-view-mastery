# 容器事件拦截：把手势所有权交给正确的一层

自定义 ViewGroup 经常同时包含可点击子项，并自己处理拖动、翻页或滚动。难点不是收到某个 `MotionEvent`，而是在一整条手势序列（gesture stream）中决定：事件继续交给原目标子 View，还是由父容器接管。

## 学习目标

- 理解 `dispatchTouchEvent()`、`onInterceptTouchEvent()`、`onTouchEvent()` 的分工。
- 掌握从 `ACTION_DOWN` 到 `ACTION_CANCEL` 的目标锁定和切换过程。
- 用触摸阈值（touch slop）避免把点击误判为拖动。
- 正确处理多指、父子冲突与 `requestDisallowInterceptTouchEvent()`。
- 建立可测试、可清理的事件状态机。

## 1. 三个入口各做什么

对于 ViewGroup：

- `dispatchTouchEvent()`：事件分发总入口，寻找或复用触摸目标。
- `onInterceptTouchEvent()`：父容器判断是否拦截；返回 `true` 表示想由自己接管。
- `onTouchEvent()`：当前 View 自己消费事件并维护手势状态。

大多数自定义容器不需要覆盖 `dispatchTouchEvent()`。优先把“是否接管”写在 `onInterceptTouchEvent()`，把“接管后如何拖动”写在 `onTouchEvent()`，可以保留系统已有的目标管理、取消事件与无障碍行为。

```text
ViewGroup.dispatchTouchEvent(event)
              │
              ▼
     onInterceptTouchEvent(event)?
         │ false             │ true
         ▼                   ▼
  child.dispatch...      ViewGroup.onTouchEvent
         │
         ├── 后续仍未拦截：继续给同一 child
         │
         └── 中途开始拦截：child 收 ACTION_CANCEL
                           父处理当前及后续事件
```

## 2. 一条事件序列中的所有权

一次触摸序列从 `ACTION_DOWN` 开始，以 `ACTION_UP` 或 `ACTION_CANCEL` 结束。`DOWN` 时系统命中测试并确定目标子 View。若父容器不拦截，后续事件通常继续发给这个目标，即使手指已经移出其边界。

父容器可以在 `MOVE` 判断用户已形成拖动并开始拦截。此时系统会向原目标子 View 发送 `ACTION_CANCEL`，让它清除按压、点击候选和局部手势状态。父容器必须能从当前事件开始工作，而不能假设自己一定通过 `onTouchEvent()` 收到过最初的 `DOWN`。

```text
时间 ─────────────────────────────────────────►
事件       DOWN       MOVE(小)      MOVE(大)       UP
父拦截     false      false         true           true
子收到     DOWN       MOVE          CANCEL         -
父触摸     -          -             MOVE           UP
```

> **注意**：不要在 `ACTION_DOWN` 无条件拦截，除非容器确实拥有整条手势。过早拦截会让 Button、CheckBox、可点击列表项都失去点击机会。

## 3. 用 touch slop 区分点击与拖动

手指按住时会有微小抖动。`ViewConfiguration.scaledTouchSlop` 给出系统建议阈值；只有主方向位移超过阈值，并且方向判断符合容器能力时才拦截。

下面是横向拖动容器的拦截骨架：

```kotlin
import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.ViewConfiguration
import android.view.ViewGroup
import kotlin.math.abs

abstract class HorizontalDragLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : ViewGroup(context, attrs, defStyleAttr) {

    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop
    private var activePointerId = MotionEvent.INVALID_POINTER_ID
    private var initialX = 0f
    private var initialY = 0f
    private var lastX = 0f
    private var dragging = false

    override fun onInterceptTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                activePointerId = event.getPointerId(0)
                initialX = event.x
                initialY = event.y
                lastX = event.x
                dragging = false

                // 若仍有未结束动画，可在这里停止；若要立即接管，
                // 由动画状态决定 dragging，而不是无条件返回 true。
            }

            MotionEvent.ACTION_MOVE -> {
                val index = event.findPointerIndex(activePointerId)
                if (index == -1) return false

                val dx = event.getX(index) - initialX
                val dy = event.getY(index) - initialY
                if (abs(dx) > touchSlop && abs(dx) > abs(dy)) {
                    dragging = canStartHorizontalDrag(dx)
                    if (dragging) {
                        lastX = event.getX(index)
                        parent?.requestDisallowInterceptTouchEvent(true)
                    }
                }
            }

            MotionEvent.ACTION_POINTER_UP -> switchActivePointer(event)

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL -> resetTouch()
        }
        return dragging
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                activePointerId = event.getPointerId(0)
                initialX = event.x
                initialY = event.y
                lastX = event.x
                return true
            }

            MotionEvent.ACTION_MOVE -> {
                val index = event.findPointerIndex(activePointerId)
                if (index == -1) return false
                val x = event.getX(index)

                if (!dragging) {
                    val dxFromDown = x - initialX
                    val dyFromDown = event.getY(index) - initialY
                    if (abs(dxFromDown) > touchSlop &&
                        abs(dxFromDown) > abs(dyFromDown) &&
                        canStartHorizontalDrag(dxFromDown)
                    ) {
                        dragging = true
                        parent?.requestDisallowInterceptTouchEvent(true)
                    }
                }

                if (dragging) {
                    val dx = x - lastX
                    dragBy(dx)
                    lastX = x
                }
                return true
            }

            MotionEvent.ACTION_POINTER_UP -> {
                switchActivePointer(event)
                return true
            }

            MotionEvent.ACTION_UP -> {
                val wasDragging = dragging
                if (wasDragging) finishDrag(cancelled = false)
                resetTouch()
                if (!wasDragging) performClick()
                return true
            }

            MotionEvent.ACTION_CANCEL -> {
                if (dragging) finishDrag(cancelled = true)
                resetTouch()
                return true
            }
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()

    private fun switchActivePointer(event: MotionEvent) {
        val liftedIndex = event.actionIndex
        if (event.getPointerId(liftedIndex) != activePointerId) return

        val replacementIndex = if (liftedIndex == 0) 1 else 0
        if (replacementIndex < event.pointerCount) {
            activePointerId = event.getPointerId(replacementIndex)
            lastX = event.getX(replacementIndex)
            initialX = lastX
            initialY = event.getY(replacementIndex)
        } else {
            activePointerId = MotionEvent.INVALID_POINTER_ID
        }
    }

    private fun resetTouch() {
        dragging = false
        activePointerId = MotionEvent.INVALID_POINTER_ID
    }

    protected abstract fun canStartHorizontalDrag(dx: Float): Boolean
    protected abstract fun dragBy(dx: Float)
    protected abstract fun finishDrag(cancelled: Boolean)
}
```

这是机制骨架，不规定滚动存储方式。实际容器可在 `dragBy()` 中限制边界，在 `finishDrag()` 中结合 `VelocityTracker` 决定吸附或惯性滚动。

代码在 `UP` 调用 `performClick()` 是为了保留 View 的点击语义；生产控件通常只在未拖动且确实判定为点击时调用，可用一个单独的 `wasDragging` 或点击候选标志区分。若 ViewGroup 本身不可点击，则可不声明点击行为，但可点击子 View 仍应得到完整序列。

## 4. 为什么 `ACTION_DOWN` 特别重要

若 View 的 `onTouchEvent()` 在 `DOWN` 返回 `false`，它通常不会继续收到同一序列的后续事件。因此父容器一旦决定自己是触摸目标，就应在 `DOWN` 返回 `true`。

另一方面，`onInterceptTouchEvent(DOWN)` 通常返回 `false`，但仍应在这里初始化：

- 主指针 ID；
- 初始坐标；
- 是否正在拖动；
- 速度跟踪器；
- 需要中止的旧滚动动画。

这样父容器在后续 `MOVE` 拦截时拥有判断所需的初始信息。新序列开始时必须清掉上一序列状态，避免一次缺失的 `CANCEL` 让下一次触摸继承旧标志。

## 5. 多指不能只记 pointer index

`MotionEvent` 中：

- pointer ID 在一根手指存续期间稳定；
- pointer index 只是当前事件数组下标，会随着手指抬起而变化。

因此保存 `activePointerId`，每次通过 `findPointerIndex(id)` 查当前下标。活动手指抬起时选择替代指针，并重置 `lastX/lastY`，否则下一次位移会突然跳跃。

```text
事件 1: index 0 -> id 7, index 1 -> id 12
id 7 抬起
事件 2: index 0 -> id 12

保存 index 1：下一事件越界
保存 id 12：findPointerIndex(12) 得到新的 index 0
```

若 `findPointerIndex()` 返回 `-1`，应安全结束或忽略当前分支，不能继续 `getX(-1)`。

## 6. `requestDisallowInterceptTouchEvent()` 的边界

子 View 或内层容器可调用：

```kotlin
parent.requestDisallowInterceptTouchEvent(true)
```

它请求祖先在当前序列中不要拦截，常用于内层已经识别出自己可处理的滚动方向。请求会沿父链上传。它不是永久设置，新 `DOWN` 到来后应重新判断。

典型嵌套策略：

1. `DOWN` 允许孩子先成为目标；
2. 位移未超过 slop 时不争抢；
3. 内层能沿该方向继续滚动，则禁止祖先拦截；
4. 内层到达边界且产品规则允许外层接管，则解除禁止；
5. 对复杂连续滚动优先考虑 AndroidX Nested Scrolling 协议，而不是手工在中途反复抢事件。

> **注意**：`requestDisallowInterceptTouchEvent(true)` 是请求祖先不要调用常规拦截判断，不等于子 View 必然消费成功，也不应被用来掩盖方向判定缺失。

## 7. 方向、边界与接管条件

仅判断 `abs(dx) > touchSlop` 不够。一个横向分页容器嵌套横向列表时，还应判断：

- 横向位移是否明显大于纵向位移；
- 当前拖动方向；
- 内层子 View 是否能继续滚动；
- 外层自身是否已到边界。

可用 `ViewCompat.canScrollHorizontally(child, direction)` 辅助判断。注意 direction 的语义：负数询问是否能向起始/左方向滚动，正数询问是否能向结束/右方向滚动；还要结合实际内容方向验证。

```text
MOVE
 │
 ├─ 未超过 slop ─────────────► 保持点击候选
 │
 ├─ 纵向更明显 ──────────────► 不拦截横向手势
 │
 ├─ 子 View 能沿该方向滚动 ──► 子 View 保持所有权
 │
 └─ 子 View 到边界且父可滚动 ─► 父拦截并接管
```

## 8. CANCEL 与生命周期清理

`ACTION_CANCEL` 与 `ACTION_UP` 都结束当前序列，但语义不同：

- `UP`：用户正常抬起，可以提交点击、吸附或 fling；
- `CANCEL`：序列被系统或祖先终止，应回滚按压状态，不应提交点击。

在两条路径都要回收或清空：

- `VelocityTracker.recycle()`；
- 活动 pointer ID；
- dragging、pressed 等标志；
- 仅属于本次手势的 Runnable 或临时动画。

如果容器启动长生命周期动画或注册监听器，还应在 `onDetachedFromWindow()` 中停止动画、移除回调：

```kotlin
override fun onDetachedFromWindow() {
    scroller.abortAnimation()
    removeCallbacks(settleRunnable)
    velocityTracker?.recycle()
    velocityTracker = null
    super.onDetachedFromWindow()
}
```

> **无障碍提示**：触摸手势不能成为唯一入口。可滑动/翻页容器应提供可点击控件、键盘操作或无障碍滚动 action，并正确更新可滚动状态。覆盖 `onTouchEvent()` 的可点击 View 应调用 `performClick()`，以保留无障碍服务和测试框架的点击语义。

## 9. 常见陷阱

1. **在 DOWN 就拦截全部事件**：孩子永远无法点击。
2. **超过 1 像素就拖动**：手指抖动导致点击频繁取消；应使用 touch slop。
3. **拦截后依赖父曾收到触摸 DOWN**：父的 `onTouchEvent()` 可能从 MOVE 才开始，初始状态应在拦截阶段准备。
4. **忽略 CANCEL**：pressed、dragging 或 tracker 泄漏到下一序列。
5. **保存 pointer index**：第二根手指或主指抬起后坐标错乱。
6. **父子双方同时移动内容**：没有明确所有权或嵌套滚动协议，位移被消费两次。
7. **只返回 true，不实际消费**：事件被父抢走但界面不响应，子项也被取消。
8. **手势中途调用 `performClick()`**：点击应在合法的 UP 路径提交，CANCEL 不提交。
9. **只做触摸测试**：鼠标、键盘、TalkBack 操作无法完成同一任务。

## 实践检查清单

- [ ] DOWN 初始化状态，但不无条件拦截可点击孩子。
- [ ] 位移超过 touch slop 且方向匹配后才接管。
- [ ] 父接管时子 View 能收到并正确处理 CANCEL。
- [ ] UP 与 CANCEL 都清理状态，只有正常路径提交动作。
- [ ] 使用 pointer ID，并处理 `ACTION_POINTER_UP`。
- [ ] `findPointerIndex()` 的 `-1` 分支安全。
- [ ] 父子同向滚动时考虑边界或 Nested Scrolling。
- [ ] 可点击语义通过 `performClick()` 暴露。
- [ ] 覆盖点击、短滑、斜滑、多指、系统取消和嵌套边界测试。
- [ ] detach 时停止动画、回调并回收跟踪器。

## 小结

事件拦截是手势所有权的状态机。让孩子先获得 DOWN，在位移超过阈值、方向正确且父容器确实能够处理时再拦截，是大多数滚动容器的可靠起点。配合 CANCEL 清理、稳定的 pointer ID、边界判断和无障碍替代入口，才能避免“偶尔点不动”和“嵌套滑动抢事件”这类最难复现的问题。

## 延伸阅读

- [管理 ViewGroup 中的触摸事件](https://developer.android.com/develop/ui/views/touch-and-input/gestures/viewgroup)
- [MotionEvent API](https://developer.android.com/reference/android/view/MotionEvent)
- [ViewConfiguration API](https://developer.android.com/reference/android/view/ViewConfiguration)
- [Nested scrolling](https://developer.android.com/reference/androidx/core/view/NestedScrollingParent3)
