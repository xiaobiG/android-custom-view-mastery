# 滑动冲突与状态机

## 学习目标

- 用显式状态机代替散落的布尔变量。
- 使用 `ViewConfiguration.scaledTouchSlop` 区分抖动与有意拖动。
- 按位移方向和控件边界决定父子事件所有权。
- 正确使用拦截与 `requestDisallowInterceptTouchEvent()`。
- 处理 `CANCEL`、多指变化和手势反向等异常路径。

## 冲突的本质：两个控件争夺同一序列

典型场景是竖向滚动容器内嵌横向轮播，或可缩放画布放在可滚动页面中。父子都能理解
`MOVE`，但一条手势序列最终需要清晰的所有者。解决冲突不是比较“谁更优先”，而是设计
**仲裁条件**：移动是否越过阈值、主方向是什么、当前控件还能否继续滚动。

## 从点击候选到拖动：显式状态机

推荐至少定义四种状态：

```text
            DOWN
  IDLE --------------> POSSIBLE
                          |  位移 <= touchSlop
                          |  保持点击候选
                          |
            主方向水平   v
              +------ DRAGGING ------+
              |                       |
              +-- UP --> IDLE         +-- CANCEL --> IDLE

  POSSIBLE -- UP --> CLICK --> performClick() --> IDLE
  POSSIBLE -- CANCEL ---------------------------> IDLE
```

状态转换必须集中完成。进入 `DRAGGING` 时取消按压态；终态统一复位。若使用
`VelocityTracker`、自动滚动或长按任务，也应绑定到状态进入/退出。

## `touchSlop` 不是装饰性常量

`ViewConfiguration.get(context).scaledTouchSlop`（平台 API）是系统按设备密度和输入特性
配置的移动阈值。判断方向前先越过该阈值，能避免手指微抖导致父子反复争抢。

方向锁定常用两种规则：

- 简单锁定：`abs(dx) > abs(dy)` 判定水平。
- 带偏置锁定：`abs(dx) > abs(dy) * 1.2f`，减少对角线误判。

锁定后不要每帧重新分类，否则手势会在横向与竖向之间振荡。

## 外部拦截法：父容器作最终仲裁

下面的 `ViewGroup` 只在横向移动越过阈值后拦截。代码使用平台类型
`android.view.ViewConfiguration`、`MotionEvent`；最低 API 由应用自身决定，这些 API 自早期
版本可用。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.ViewConfiguration
import android.widget.FrameLayout
import kotlin.math.abs

class HorizontalDragLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : FrameLayout(context, attrs) {

    private enum class State { IDLE, POSSIBLE, DRAGGING }

    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop
    private var state = State.IDLE
    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f

    override fun onInterceptTouchEvent(ev: MotionEvent): Boolean {
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                state = State.POSSIBLE
                downX = ev.x
                downY = ev.y
                lastX = ev.x
                // 必须让 super 看见 DOWN，以建立它自己的分发状态。
                super.onInterceptTouchEvent(ev)
                return false
            }
            MotionEvent.ACTION_MOVE -> {
                if (state == State.POSSIBLE) {
                    val dx = ev.x - downX
                    val dy = ev.y - downY
                    if (abs(dx) > touchSlop && abs(dx) > abs(dy) * 1.2f) {
                        state = State.DRAGGING
                        lastX = ev.x // 接管帧只定锚，避免内容突然跳动
                        return true
                    }
                }
                return state == State.DRAGGING
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                state = State.IDLE
                return false
            }
        }
        return false
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> return true
            MotionEvent.ACTION_MOVE -> {
                if (state == State.DRAGGING) {
                    val delta = lastX - event.x
                    scrollBy(delta.toInt(), 0)
                    lastX = event.x
                }
                return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                state = State.IDLE
                return true
            }
        }
        return super.onTouchEvent(event)
    }
}
```

父容器从“不拦截”改为“拦截”时，框架给原子目标发送 `CANCEL`。父容器的第一帧若直接使用
`downX` 计算增量，内容会一次跳过阈值距离；接管时重置 `lastX` 可避免跳变。

```text
DOWN: 父记录起点 -> 子成为目标
MOVE: 未过阈值   -> 子继续
MOVE: 水平锁定   -> 子收到 CANCEL，父记录新锚点
MOVE:            -> 父按相邻两帧 delta 拖动
UP/CANCEL:       -> 父清理状态
```

## 内部协商法：子控件请求父容器暂不拦截

当子控件更了解“还能否滚动”时，可在子控件内调用
`requestDisallowInterceptTouchEvent(true)`。例如横向内容在中间区域应保有事件；到左边界且
继续向右拖时，可以释放给祖先。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import androidx.core.view.ViewCompat
import kotlin.math.abs

/** AndroidX：ViewCompat；其余为平台类型。 */
class DirectionLockView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val slop = ViewConfiguration.get(context).scaledTouchSlop
    private var downX = 0f
    private var downY = 0f
    private var horizontalLocked = false

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                horizontalLocked = false
                parent?.requestDisallowInterceptTouchEvent(true)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = event.x - downX
                val dy = event.y - downY
                if (!horizontalLocked && abs(dx) > slop && abs(dx) > abs(dy)) {
                    horizontalLocked = true
                }

                val direction = if (dx > 0f) -1 else 1
                val canContinue = ViewCompat.canScrollHorizontally(this, direction)
                val keepForChild = horizontalLocked && canContinue
                parent?.requestDisallowInterceptTouchEvent(keepForChild)
                return true
            }
            MotionEvent.ACTION_UP -> {
                parent?.requestDisallowInterceptTouchEvent(false)
                if (!horizontalLocked) performClick()
                reset()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                parent?.requestDisallowInterceptTouchEvent(false)
                reset()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun reset() {
        horizontalLocked = false
    }
}
```

> **注意**：示例中的 `direction` 是“内容希望滚动的方向”，与手指位移符号相反。边界判断
> 必须根据具体滚动实现校准，不能机械复制。

## 决策表：方向还不够

真实控件通常要同时考虑方向与边界：

```text
条件                              所有者
未越过 touchSlop                  保持现有目标（点击候选）
水平占优，子控件还能水平滚动      子控件
水平占优，子控件已到对应边界      父容器或更外层祖先
竖直占优                          竖向父容器
双指缩放已开始                    可缩放子控件，禁止祖先拦截
收到 UP / CANCEL                  无，全部状态复位
```

边界释放也要避免抖动。较稳妥的做法是在一条序列内锁定方向，但允许根据边界**单向释放**；
释放给父容器后不要再夺回当前序列。

## 与点击、长按和速度的协作

- 越过 `touchSlop` 时设置 `isPressed = false`，取消点击候选。
- 若投递了延迟长按任务，进入拖动或收到 `CANCEL` 时移除回调。
- `VelocityTracker` 应从 `DOWN` 开始收集，在 `UP` 计算，在 `CANCEL` 只回收。
- 新 `DOWN` 到来时停止旧的 fling，避免动画与手指同时修改同一滚动位置。

> **性能提示**：`MOVE` 频率可能高于显示帧率。不要在每次移动中分配对象、启动新动画或
> 请求整棵树重新布局；优先更新字段并调用 `postInvalidateOnAnimation()`。

## 常见陷阱

1. **用固定像素阈值**：不同密度、设备类型上的手感不一致。
2. **每个 MOVE 都重新判方向**：对角线移动造成所有权振荡。
3. **只在 UP 复位**：被父容器或系统取消后控件永远停在拖动态。
4. **接管首帧仍以 DOWN 为锚**：画面瞬移一个 `touchSlop` 以上的距离。
5. **无条件禁止父拦截**：子控件到边界后页面仍无法滚动。
6. **把滚动能力与手指方向混淆**：`canScrollHorizontally(direction)` 的方向是内容滚动方向。
7. **拦截 DOWN**：子控件连点击和方向判断机会都没有。

## 验证方法

可在开发构建中绘制起点、当前点和锁定方向，并记录每次状态转换。至少测试：短点击、慢速
越阈值、快速斜划、边界向外拖、移动后返回起点、父容器中途拦截以及系统取消。

## 实践检查清单

- [ ] 状态名称和转换条件写在同一处，可画出完整状态图。
- [ ] 阈值来自 `scaledTouchSlop`，方向只锁定一次。
- [ ] 接管时重置相邻帧锚点，避免首帧跳变。
- [ ] 子控件仅在确有能力处理时禁止父拦截。
- [ ] `UP` 与 `CANCEL` 都清理状态；仅 `UP` 可能确认点击或 fling。
- [ ] 边界、斜划、反向和多指场景均经过实机验证。

## 小结

滑动冲突应被建模为序列所有权的状态机：先保留点击候选，越过系统阈值后锁定方向，再结合
滚动边界选择父或子。拦截法由父容器仲裁，禁止拦截法由子控件提供能力信息。无论采用哪种，
`CANCEL` 清理、接管帧重置和单序列稳定性都是可靠手感的基础。

## 延伸阅读

- [ViewConfiguration](https://developer.android.com/reference/android/view/ViewConfiguration)
- [ViewGroup requestDisallowInterceptTouchEvent](https://developer.android.com/reference/android/view/ViewGroup#requestDisallowInterceptTouchEvent(boolean))
- [Manage touch events in a ViewGroup](https://developer.android.com/develop/ui/views/touch-and-input/gestures/viewgroup)
