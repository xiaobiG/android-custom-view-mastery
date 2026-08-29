# 标准手势识别器

> 本章定位：掌握 `GestureDetector` 与 `ScaleGestureDetector` 的回调语义、触发顺序，
> 学会把它们透传进自定义 View 的 `onTouchEvent`，并避开"与滑动冲突、DOWN 返回时机、
> 多指状态错乱"三类高频陷阱。

## 学习目标

- 说清 `OnGestureListener` 六个回调与 `OnDoubleTapListener` 三个回调的触发条件与顺序。
- 知道 `GestureDetectorCompat`/`ScaleGestureDetectorCompat` 各自补了哪些旧版本差异。
- 用 `detector.onTouchEvent(event)` 与自定义 View 的 `onTouchEvent` 正确协作。
- 区分缩放焦点、Span 与 `onScaleBegin/onScale/onScaleEnd` 的职责。
- 针对滑动冲突、DOWN 返回时机、多指状态给出可测试的解决方案。

## 为什么需要标准识别器

手写状态机识别点击、双击、长按、拖动、fling、双指缩放，本质是在重造轮子，而且很容易
漏掉边界：`ACTION_CANCEL`、活动指针切换、双击窗口、速度阈值。平台在
`android.view` 提供了两个经过打磨的识别器：

- **`GestureDetector`**（API 1 起）：识别单指为主的点击/长按/拖动/fling/双击；
- **`ScaleGestureDetector`**（API 8 起）：识别双指缩放，内部处理跨度、焦点与指针增减。

它们不改变事件分发，只是"解释器"：你把每个 `MotionEvent` 喂给它，它回调语义化事件。
阈值（touch slop、长按超时、最小 fling 速度）都来自 `ViewConfiguration`，不要自行写死。

## 核心机制：回调语义与顺序

### `GestureDetector.OnGestureListener`

| 回调 | 触发时机 | 签名要点 | 返回值含义 |
|---|---|---|---|
| `onDown(e)` | 手势序列的第一击 `DOWN` | 所有手势的起点 | 返回 `true` 表示消费本序列 |
| `onShowPress(e)` | 按下后短暂停留、未移动未抬起 | 用于按压反馈（如按下高亮） | `void` |
| `onSingleTapUp(e)` | `UP` 时判定为单击 | 立即回调，不等待双击窗口 | 是否消费 |
| `onScroll(e1, e2, dx, dy)` | 移动超过 slop 后每个 `MOVE` | `e1` 是 `DOWN` 事件，`e2` 是当前事件，`dx/dy` 是**距上一次回调**的增量 | 是否消费 |
| `onLongPress(e)` | 长按超时且未超过 slop | 触发后本次 `UP` 不再报点击 | `void` |
| `onFling(e1, e2, vx, vy)` | `UP` 时速度达到最小阈值 | `vx/vy` 是 px/s 的速度估计 | 是否消费 |

### `GestureDetector.OnDoubleTapListener`

| 回调 | 触发时机 |
|---|---|
| `onSingleTapConfirmed(e)` | **双击判定窗口结束后**仍确认是单击；注册了双击监听才可能触发 |
| `onDoubleTap(e)` | 双击的第二击 `DOWN` 到来且时序符合双击条件 |
| `onDoubleTapEvent(e)` | 双击手势期间的 `DOWN`/`MOVE`/`UP` 全量事件 |

> **注意**：`onSingleTapUp` 在 `UP` 时立即回调，适合做即时反馈；`onSingleTapConfirmed`
> 会延迟一个双击窗口（数百毫秒），适合需要"确认不是双击"的业务。注册了双击监听后，
> 第一击的 `UP` 是否同时触发 `onSingleTapUp`、以及长按后单击确认是否被抑制，在
> API 19 前后有过调整；对兼容性敏感的功能应以目标版本源码/文档为准。

### 典型时序

```text
ACTION_DOWN ────────► onDown(e) ──────────────┐
    │                                          │
    ├─ 未移动且 TAP_TIMEOUT 到 ──► onShowPress(e)
    │                                          │
    ├─ 未移动且 LONGPRESS_TIMEOUT 到 ──► onLongPress(e)
    │                                       （后续 UP 不再报点击）
ACTION_MOVE 超过 touch slop ──► onScroll(e1, e2, dx, dy) 反复触发
    │
ACTION_UP
    ├─ 速度 >= 最小 fling 阈值 ──► onFling(e1, e2, vx, vy)
    ├─ 未触发长按/滚动、仍在 tap 区域：
    │     ├─ 未注册双击监听 ──► onSingleTapUp(e)
    │     └─ 注册了双击监听：
    │           ├─ 本次为双击第二击 ──► onDoubleTap(e) + onDoubleTapEvent(e)
    │           └─ 窗口结束仍无第二击 ──► onSingleTapConfirmed(e)
ACTION_CANCEL ──► 全部判定作废（不回调任何点击类方法）
```

> **注意**：官方文档特别强调，`SimpleOnGestureListener` 的所有方法默认返回 `false`，
> 只有 `onDown` 返回 `true` 时，系统才会认为你要消费整个手势；否则 `onScroll`、
> `onFling` 等后续回调不会被调用。只在确实想忽略整个手势时才返回 `false`。

## 与自定义 View 协作模式

标准接入方式是把每个事件**原样透传**给 detector，并让 `onTouchEvent` 的返回值与
detector 消费情况一致。下面示例同时处理单指拖动/fling 与双指缩放：

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import androidx.core.view.GestureDetectorCompat

class GestureView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val gestureDetector: GestureDetectorCompat = GestureDetectorCompat(
        context,
        object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent): Boolean = true

            override fun onScroll(
                e1: MotionEvent,
                e2: MotionEvent,
                distanceX: Float,
                distanceY: Float
            ): Boolean {
                // 注意：distance 是"上一帧到现在"的增量，直接反号加到平移量即可。
                panBy(-distanceX, -distanceY)
                return true
            }

            override fun onFling(
                e1: MotionEvent,
                e2: MotionEvent,
                velocityX: Float,
                velocityY: Float
            ): Boolean {
                startFling(velocityX, velocityY)
                return true
            }

            override fun onSingleTapUp(e: MotionEvent): Boolean {
                performClick() // 点击必须走 performClick，保证无障碍事件
                return true
            }
        }
    )

    private val scaleDetector = ScaleGestureDetector(
        context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScaleBegin(detector: ScaleGestureDetector): Boolean = true

            override fun onScale(detector: ScaleGestureDetector): Boolean {
                // scaleFactor 是相邻两帧的倍率，不是累计倍率。
                scaleBy(
                    factor = detector.scaleFactor,
                    focusX = detector.focusX,
                    focusY = detector.focusY
                )
                return true
            }
        }
    )

    override fun onTouchEvent(event: MotionEvent): Boolean {
        // DOWN 必须返回 true，否则本 View 拿不到后续 MOVE/UP。
        if (event.actionMasked == MotionEvent.ACTION_DOWN) return true

        // 双指阶段交给缩放识别器；单指阶段交给手势识别器。
        if (event.pointerCount > 1) {
            scaleDetector.onTouchEvent(event)
        } else {
            gestureDetector.onTouchEvent(event)
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun panBy(dx: Float, dy: Float) { /* 更新模型平移，invalidate() */ }
    private fun scaleBy(factor: Float, focusX: Float, focusY: Float) { /* 更新缩放 */ }
    private fun startFling(vx: Float, vy: Float) { /* 启动 OverScroller 惯性 */ }
}
```

要点：

- `gestureDetector.onTouchEvent(event)` 的返回值与 `onTouchEvent` 的消费语义解耦：
  这里统一返回 `true`，是因为 View 需要整段手势；在需要"让父容器有机会拦截"的场景，
  返回值应交给事件仲裁逻辑决定（见常见陷阱）。
- `ScaleGestureDetector` 要在**每个**事件上调用，尤其是 `POINTER_DOWN/UP`，否则它的
  指针集合会错位。
- 点击走 `performClick()`，`override` 里必须调用 `super.performClick()`，以产生
  无障碍点击事件。

## `GestureDetectorCompat` 与 `ScaleGestureDetectorCompat`

两者都在 `androidx.core`（`androidx.core:core`）：

- **`GestureDetectorCompat`**：对平台 `GestureDetector` 的包装。API 17 及以上用带
  `ignoreMultitouch=true` 的四参构造器创建，使**第二个手指落下不会重置/干扰**当前
  手势；更早的 API 用无该参数的三参构造器。这样多指误触不会把单指滚动变成乱跳。
- **`ScaleGestureDetectorCompat`**：把 API 19 引入的 **quick scale**（双击后滑动即缩放）
  能力以一致的方式暴露出来，`setQuickScaleEnabled(detector, true)` 可按需开关。
  注意 quick scale 在 targetSdk 19+ 时默认启用。

> **注意**：Compat 的动机是"旧 API 的行为补齐与一致化"，不代表平台类已废弃。
> 若 `minSdk` 较高（如 23+）且不关心这些修复，直接用平台类也可行；引入依赖前，
> 按 `androidx.core` 的发布说明核验其 `minSdk`/`compileSdk` 要求与项目一致。

### `ScaleGestureDetector` 的关键状态

- **Span**：各指针两两距离的平均值，`getCurrentSpan()` 返回，`getCurrentSpanX/Y()` 返回
  轴向分量；`getPreviousSpan()` 是上一事件的值。缩放判定以 span 变化为输入。
- **焦点**：`getFocusX()/getFocusY()` 是指针中点，缩放时应以此为 pivot，避免内容偏离
  手指中心。
- **`minSpan`**：`setMinSpan(int)` 设定触发缩放的最小跨度，单位与喂给
  `onTouchEvent` 的事件坐标一致（通常是 View 局部坐标 px）。跨度小于它就不会开始
  缩放，可用于避免误触。
- **生命周期**：`onScaleBegin` 返回 `false` 会**取消**本次缩放（后续 `onScale` 不再
  调用）；`onScale` 返回 `true` 表示消费；手势结束回调 `onScaleEnd`。
- **`isInProgress()`**：判断当前是否处于缩放手势中，常用于手势仲裁。

## 常见陷阱

### 陷阱一：与滑动冲突

症状：View 自己识别滚动/fling，但外层 `RecyclerView`/`ScrollView` 也抢着滚动，或反
过来——View 抢走了父容器的滑动。

根因：`onDown` 返回 `true` 只代表"View 想要这段手势"，父容器仍可在 `MOVE` 阶段拦截
并发 `CANCEL`；反过来，父容器在 `MOVE` 超过 slop 后拦截，View 的 `onScroll` 会被
中途打断。

```kotlin
override fun onTouchEvent(event: MotionEvent): Boolean {
    when (event.actionMasked) {
        MotionEvent.ACTION_DOWN -> {
            parent.requestDisallowInterceptTouchEvent(false) // 先不锁死
            downX = event.x
            downY = event.y
            return true
        }
        MotionEvent.ACTION_MOVE -> {
            if (!gestureStarted &&
                hypot(event.x - downX, event.y - downY) > scaledTouchSlop
            ) {
                gestureStarted = true
                // 方向明确后才锁定父容器，避免小幅度点击被误判为滚动
                parent.requestDisallowInterceptTouchEvent(true)
            }
            gestureDetector.onTouchEvent(event)
            return true
        }
        MotionEvent.ACTION_CANCEL -> {
            gestureStarted = false
            parent.requestDisallowInterceptTouchEvent(false)
            return true
        }
    }
    return super.onTouchEvent(event)
}
```

原则：**DOWN 先观察，越过 slop 且方向明确后再 `requestDisallowInterceptTouchEvent`**，
`UP/CANCEL` 时释放；复杂容器优先实现 AndroidX 嵌套滚动协议。

### 陷阱二：`DOWN` 返回 `true` 的时机

症状：只收到 `ACTION_DOWN`，后续 `MOVE/UP` 全部丢失，detector 的滚动/点击都不触发。

根因有两个层面：

1. **View 层**：`onTouchEvent` 对 `DOWN` 返回 `false`，View 不会成为事件目标；
2. **detector 层**：即便 View 接收了事件，`onDown` 回调返回 `false` 也会让
   `GestureDetector` 忽略整段手势，`onScroll/onFling` 不再触发。

```kotlin
// 正确：两处都要 true
override fun onTouchEvent(event: MotionEvent): Boolean {
    if (event.actionMasked == MotionEvent.ACTION_DOWN) return true
    gestureDetector.onTouchEvent(event)
    return true
}
```

> **注意**：若你的 `onTouchEvent` 直接写 `return gestureDetector.onTouchEvent(event)`，
> 而 `onDown` 又返回 `false`，那么 `DOWN` 会返回 `false`，View 立刻失去整个序列。
> 这是最常见的"识别器装了没用"的原因。

### 陷阱三：detector 状态在多指下的表现

症状：两指缩放中抬起一指，接下来单指拖动时位置跳变；或双指按下的瞬间，单指手势
被误判成 fling/点击。

根因：

- `GestureDetector` 本质是单指状态机。第二指落下若未被忽略（未用 `ignoreMultitouch`），
  会打断当前判定；即便忽略，它的 `e1`（`DOWN` 事件）只记录首指。
- `ScaleGestureDetector` 管理多指，但某指抬起后要重新以剩余指针为基准；`POINTER_UP`
  事件必须喂给它，否则 span/focus 用了旧指针。
- 两个 detector 同时在 `onTouchEvent` 里无条件消费，会产生"既滚动又缩放"的竞态。

```kotlin
override fun onTouchEvent(event: MotionEvent): Boolean {
    val action = event.actionMasked
    when (action) {
        MotionEvent.ACTION_POINTER_DOWN -> {
            scaleDetector.onTouchEvent(event) // 让缩放识别器建立新指针集合
            gestureLocked = true              // 进入多指，锁定单指手势
            return true
        }
        MotionEvent.ACTION_POINTER_UP -> {
            scaleDetector.onTouchEvent(event)
            return true
        }
        MotionEvent.ACTION_DOWN -> {
            gestureLocked = false
            return true
        }
        MotionEvent.ACTION_MOVE -> {
            if (scaleDetector.isInProgress) {
                scaleDetector.onTouchEvent(event)
            } else if (!gestureLocked) {
                gestureDetector.onTouchEvent(event)
            }
            return true
        }
        MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
            gestureLocked = false
            if (scaleDetector.isInProgress) scaleDetector.onTouchEvent(event)
            else gestureDetector.onTouchEvent(event)
            return true
        }
    }
    return super.onTouchEvent(event)
}
```

原则：**用状态变量做仲裁**——`POINTER_DOWN` 进入多指后锁定单指逻辑，某指抬起后要么
重设基准继续缩放，要么明确退回单指；`UP/CANCEL` 统一清理，避免残留状态污染下一段
手势。

## 实践检查清单

- [ ] `onDown` 返回 `true`，且 `onTouchEvent` 对 `DOWN` 返回 `true`。
- [ ] 每个 `MotionEvent` 都透传给相应的 detector，包括 `POINTER_DOWN/UP` 与 `CANCEL`。
- [ ] 点击最终走 `performClick()` 且调用 `super.performClick()`。
- [ ] 滑动冲突用 slop + `requestDisallowInterceptTouchEvent` 仲裁，`UP/CANCEL` 释放。
- [ ] 缩放以 `focusX/focusY` 为 pivot，`scaleFactor` 按帧累乘并限幅。
- [ ] 多指状态有显式仲裁变量，指针增减后重设基准。
- [ ] 阈值来自 `ViewConfiguration`，不写死 px。
- [ ] 真机覆盖快速切指、活动指针先抬起、系统取消（来电/手势导航）。

## 小结

`GestureDetector` 与 `ScaleGestureDetector` 把点击、长按、滚动、fling、缩放这些高频
手势从手写状态机里解放出来，但它们是"解释器"而非"仲裁者"：回调消费与 `View` 事件
消费是两套独立的布尔语义，父容器拦截、多指增减、生命周期清理仍然要你自己负责。把
`DOWN` 返回时机、slop 仲裁和手势状态机想清楚，标准识别器才能稳定工作。

## 延伸阅读

- [检测常见手势（官方）](https://developer.android.com/develop/ui/views/touch-and-input/gestures/detector)
- [GestureDetector API](https://developer.android.com/reference/android/view/GestureDetector)
- [ScaleGestureDetector API](https://developer.android.com/reference/android/view/ScaleGestureDetector)
- [GestureDetectorCompat（androidx.core）](https://developer.android.com/reference/kotlin/androidx/core/view/GestureDetectorCompat)
- [ScaleGestureDetectorCompat（androidx.core）](https://developer.android.com/reference/kotlin/androidx/core/view/ScaleGestureDetectorCompat)
