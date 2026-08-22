# 速度、惯性与边缘效果

## 学习目标

- 使用 `VelocityTracker` 以正确的单位和活动 pointer ID 计算速度。
- 用 `OverScroller` 驱动可中断、可约束的惯性滚动。
- 理解 `computeScroll()` 只推进动画，不自动移动内容。
- 通过 `EdgeEffect` 表达越界反馈，并处理版本差异。
- 在新手势、取消和脱离窗口时释放所有瞬态资源。

## 从拖动到 fling 的流水线

惯性滚动（fling）由三个独立环节组成：采样速度、求解随时间衰减的位置、逐帧应用位置。
`VelocityTracker` 不负责动画，`OverScroller` 不负责绘制，View 也不会自动采用 scroller 的
坐标。

```text
MotionEvent 序列
  | DOWN: obtain tracker，停止旧 fling
  | MOVE: addMovement，直接拖动
  | UP: computeCurrentVelocity(1000)
  v
VelocityTracker -> x/yVelocity（px/s）
  |
  v
OverScroller.fling(start, velocity, bounds)
  |
  `-> computeScrollOffset() -> currX/currY -> 应用 -> 请求下一帧
```

平台类型：`android.view.VelocityTracker`、`android.widget.OverScroller`、
`android.widget.EdgeEffect`。它们不是 AndroidX 类型。

## 正确计算速度

`computeCurrentVelocity(units, maxVelocity)` 中 `units=1000` 表示每秒像素；若误传 `1`，
速度会小 1000 倍。多指场景应读取活动 ID 对应的 `getXVelocity(id)` / `getYVelocity(id)`。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.VelocityTracker
import android.view.View
import android.view.ViewConfiguration
import android.widget.OverScroller
import kotlin.math.abs

class FlingStripView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val scroller = OverScroller(context)
    private val config = ViewConfiguration.get(context)
    private val minVelocity = config.scaledMinimumFlingVelocity
    private val maxVelocity = config.scaledMaximumFlingVelocity

    private var tracker: VelocityTracker? = null
    private var activeId = MotionEvent.INVALID_POINTER_ID
    private var lastX = 0f
    private var contentX = 0
    private var maxContentX = 0 // 布局/数据变化时更新

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!scroller.isFinished) {
                    // 先保留当前视觉位置；abortAnimation() 会把 scroller 跳到 finalX。
                    setContentX(scroller.currX)
                    scroller.abortAnimation()
                }
                tracker?.recycle()
                tracker = VelocityTracker.obtain().also { it.addMovement(event) }
                activeId = event.getPointerId(0)
                lastX = event.x
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                tracker?.addMovement(event)
                val index = event.findPointerIndex(activeId)
                if (index >= 0) {
                    val x = event.getX(index)
                    scrollModelBy((lastX - x).toInt())
                    lastX = x
                }
                return true
            }
            MotionEvent.ACTION_POINTER_UP -> {
                tracker?.addMovement(event)
                switchActivePointerIfNeeded(event)
                return true
            }
            MotionEvent.ACTION_UP -> {
                tracker?.addMovement(event)
                tracker?.computeCurrentVelocity(1000, maxVelocity.toFloat())
                val fingerVelocity = tracker?.getXVelocity(activeId) ?: 0f
                if (abs(fingerVelocity) >= minVelocity) {
                    // 内容滚动方向与手指速度方向相反。
                    startFling((-fingerVelocity).toInt())
                }
                finishGesture()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                finishGesture() // 取消时不启动 fling
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun startFling(contentVelocityX: Int) {
        scroller.fling(
            contentX, 0,
            contentVelocityX, 0,
            0, maxContentX,
            0, 0
        )
        postInvalidateOnAnimation() // View API 16
    }

    override fun computeScroll() {
        if (scroller.computeScrollOffset()) {
            setContentX(scroller.currX)
            postInvalidateOnAnimation()
        }
    }

    private fun scrollModelBy(dx: Int) = setContentX(contentX + dx)

    private fun setContentX(value: Int) {
        contentX = value.coerceIn(0, maxContentX)
        invalidate()
    }

    private fun switchActivePointerIfNeeded(event: MotionEvent) {
        val upIndex = event.actionIndex
        if (event.getPointerId(upIndex) != activeId) return
        val replacement = (0 until event.pointerCount).firstOrNull { it != upIndex }
        if (replacement != null) {
            activeId = event.getPointerId(replacement)
            lastX = event.getX(replacement)
            tracker?.clear() // 新活动指针不继承旧指针速度历史
            tracker?.addMovement(event) // 以当前事件作为新活动指针的速度起点
        }
    }

    private fun finishGesture() {
        tracker?.recycle()
        tracker = null
        activeId = MotionEvent.INVALID_POINTER_ID
    }

    override fun onDetachedFromWindow() {
        scroller.abortAnimation()
        finishGesture()
        super.onDetachedFromWindow()
    }
}
```

> **注意**：`OverScroller.abortAnimation()` 会直接结束到最终位置；若只想停止在当前视觉位置，
> 应在中断前先把 `currX/currY` 同步到模型，再调用 `abortAnimation()`。

## `computeScroll()` 的逐帧协议

调用 `fling()` 只初始化参数，不会开启线程或自动修改 `scrollX`。每帧：

```text
Choreographer / draw traversal
          |
          v
View.computeScroll()
          |
          +-- computeScrollOffset() == false --> 结束
          |
          `-- true -> 读取 currX/currY
                    -> 写入模型或 scrollTo
                    -> postInvalidateOnAnimation()
                    -> 下一帧再次进入
```

边界来自内容尺寸而非 View 尺寸。例如横向内容宽 `contentWidth`、可视宽
`width-paddingLeft-paddingRight`，则 `maxX=max(0, contentWidth-viewportWidth)`。数据或尺寸
变化时应重算，并约束当前位置。

## 越界与 `EdgeEffect`

`EdgeEffect` 是平台边缘反馈对象。传统 API 使用 `onPull(deltaDistance, displacement)`；
API 31 新增 `onPullDistance()`，它返回实际消费的归一化距离，便于精确协商。`deltaDistance`
通常是拖动像素除以对应 View 尺寸。

```kotlin
import android.graphics.Canvas
import android.os.Build
import android.widget.EdgeEffect
import androidx.core.view.ViewCompat

private lateinit var topEdge: EdgeEffect
private lateinit var bottomEdge: EdgeEffect

private fun pullTop(deltaY: Float, touchX: Float, width: Int, height: Int) {
    if (height <= 0 || width <= 0) return
    val distance = deltaY / height
    val displacement = (touchX / width).coerceIn(0f, 1f)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) { // API 31
        topEdge.onPullDistance(distance, displacement)
    } else {
        @Suppress("DEPRECATION")
        topEdge.onPull(distance, displacement) // 双参数重载 API 21
    }
    ViewCompat.postInvalidateOnAnimation(this) // AndroidX Core
}

private fun releaseEdges() {
    topEdge.onRelease()
    bottomEdge.onRelease()
}

private fun drawVerticalEdges(canvas: Canvas) {
    var needsFrame = false
    if (!topEdge.isFinished) {
        val save = canvas.save()
        topEdge.setSize(width, height)
        needsFrame = topEdge.draw(canvas) || needsFrame
        canvas.restoreToCount(save)
    }
    if (!bottomEdge.isFinished) {
        val save = canvas.save()
        canvas.rotate(180f, width / 2f, height / 2f)
        bottomEdge.setSize(width, height)
        needsFrame = bottomEdge.draw(canvas) || needsFrame
        canvas.restoreToCount(save)
    }
    if (needsFrame) ViewCompat.postInvalidateOnAnimation(this)
}
```

以上片段应放进 View 类，`topEdge/bottomEdge` 在构造时以 `EdgeEffect(context)` 初始化，
`drawVerticalEdges()` 从 `onDraw()` 或 `dispatchDraw()` 调用。真实项目要按 padding 与内容区调整
画布变换。

拖动到顶部还继续向下时拉伸 top edge；到达底部还继续向上时拉伸 bottom edge。在
`UP/CANCEL` 调用 `onRelease()`。fling 撞边可使用 `onAbsorb(abs(velocity))` 表达冲击；不要在
每一帧反复 absorb。

```text
拖动未越界 -> 内容消费全部 delta
拖动越界   -> 内容消费到边界 + EdgeEffect 消费剩余距离
松手       -> EdgeEffect.onRelease()
fling 撞边 -> 停止/回弹 + EdgeEffect.onAbsorb(速度)
绘制返回 true -> 请求下一帧，直到 isFinished
```

## 速度方向、坐标方向与符号

手指向上速度为负，但内容通常应向下（滚动位置增大），所以常见实现对
`fingerVelocity` 取负后传入 scroller。不要凭经验反号：明确记录“手指位移”“内容位移”与
“滚动位置”三者正方向，再以慢速拖动和 fling 连续性验证。松手瞬间不应反向。

## 生命周期与动画竞争

- 新 `DOWN`：先采纳当前动画位置，再停止旧 fling。
- `CANCEL`：回收 tracker、释放 edge，不启动惯性。
- `onDetachedFromWindow()`：停止 scroller，回收 tracker，取消所有帧回调。
- 内容范围改变：重算边界，必要时停止或重新约束动画。
- 用户重新触摸：手指拥有最高优先级，不让旧动画继续写同一字段。

> **性能提示**：`VelocityTracker.obtain()` 应每序列一次并在终态 `recycle()`；不要在每个
> `MOVE` 创建 tracker。`computeScroll()` 内避免布局和对象分配。

## 常见陷阱

1. **忘记 `addMovement(DOWN)`**：速度历史缺少起点。
2. **使用默认 pointer 速度**：多指切换后读到非活动指针。
3. **单位传 1 而非 1000**：惯性几乎不可见。
4. **调用 fling 后不请求帧**：`computeScroll()` 不会持续推进。
5. **读取 `currX` 但不应用**：求解器在动，画面没动。
6. **边界为负**：内容小于视口时 scroller 参数无效；用 `max(0, ...)`。
7. **CANCEL 也启动 fling**：系统接管后控件仍自行运动。
8. **脱离窗口后继续调度**：造成无意义工作或状态泄漏。

## 实践检查清单

- [ ] tracker 从 `DOWN` 收集到 `UP`，终态均回收。
- [ ] 速度单位是 px/s，并按活动 pointer ID 读取。
- [ ] fling 速度方向与松手前内容运动连续。
- [ ] 每个有效 scroller 帧都应用位置并请求下一帧。
- [ ] 边界由内容与视口尺寸计算，尺寸变化后重新约束。
- [ ] EdgeEffect 在拖动越界、释放、撞边和绘制阶段均正确推进。
- [ ] 新触摸与 `onDetachedFromWindow()` 能停止旧动画。

## 小结

自然惯性来自清晰的分工：`VelocityTracker` 测量，`OverScroller` 求解，View 逐帧应用，
`EdgeEffect` 反馈越界。把单位、pointer ID、符号和边界写清，再处理所有终态和生命周期，
就能得到可中断且不跳变的滚动体验。

## 延伸阅读

- [Track movement](https://developer.android.com/develop/ui/views/touch-and-input/gestures/movement)
- [OverScroller](https://developer.android.com/reference/android/widget/OverScroller)
- [EdgeEffect](https://developer.android.com/reference/android/widget/EdgeEffect)
