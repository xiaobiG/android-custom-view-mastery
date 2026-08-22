# 多点触控与缩放旋转

## 学习目标

- 区分稳定的 pointer ID 与会变化的 pointer index。
- 正确解析 `ACTION_POINTER_DOWN/UP` 的 `actionIndex`。
- 在手指增减时平滑切换活动指针，避免坐标跳变。
- 组合 `ScaleGestureDetector` 与双指旋转算法。
- 让平移、缩放、旋转共享明确的手势状态与变换中心。

## 一条事件里为什么有多个坐标

`MotionEvent`（平台 `android.view.MotionEvent`）描述某一时刻所有活动指针。每个指针有：

- **pointer ID**：本指针从按下到抬起期间稳定的整数标识。
- **pointer index**：它在当前事件数组中的位置，范围 `0 until pointerCount`，可能变化。
- 工具类型（tool type）、压力、尺寸以及各轴坐标。

永远把 ID 存入字段，使用前通过 `findPointerIndex(id)` 找到本事件的 index。不要跨事件保存
index。

```text
事件                  index 0       index 1       活动 ID
DOWN                   id=7                        [7]
POINTER_DOWN           id=7          id=12         [7,12]
POINTER_UP(id=7)       id=7          id=12         [12]
下一次 MOVE            id=12                       [12]

结论：id=12 始终是 12，但它的 index 从 1 变成 0。
```

`event.actionMasked` 表示动作种类；仅对 `POINTER_DOWN/POINTER_UP`，
`event.actionIndex` 指向发生变化的那个指针。最后一指抬起仍是 `ACTION_UP`，不是
`ACTION_POINTER_UP`。

## 活动指针切换

单指平移通常维护一个 `activePointerId`。当活动指针抬起时选择仍留在屏幕上的另一个 ID，
并把上一坐标重置到它当前的位置。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View

/** 平台 API：MotionEvent.INVALID_POINTER_ID、findPointerIndex。 */
class MultiDragView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var activeId = MotionEvent.INVALID_POINTER_ID
    private var lastX = 0f
    private var lastY = 0f

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                activeId = event.getPointerId(0)
                lastX = event.x
                lastY = event.y
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val index = event.findPointerIndex(activeId)
                if (index < 0) return true // 数据异常时跳过本帧，不用错误 index
                val x = event.getX(index)
                val y = event.getY(index)
                panBy(x - lastX, y - lastY)
                lastX = x
                lastY = y
                return true
            }
            MotionEvent.ACTION_POINTER_UP -> {
                val liftedIndex = event.actionIndex
                if (event.getPointerId(liftedIndex) == activeId) {
                    val replacement = (0 until event.pointerCount)
                        .firstOrNull { it != liftedIndex }
                    if (replacement != null) {
                        activeId = event.getPointerId(replacement)
                        lastX = event.getX(replacement)
                        lastY = event.getY(replacement)
                    } else {
                        activeId = MotionEvent.INVALID_POINTER_ID
                    }
                }
                return true
            }
            MotionEvent.ACTION_UP -> {
                performClick()
                reset()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                reset()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun panBy(dx: Float, dy: Float) {
        // 更新模型中的平移量，然后 invalidate()。
    }

    private fun reset() {
        activeId = MotionEvent.INVALID_POINTER_ID
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
```

生产代码还应以 `touchSlop` 区分点击和平移；示例只聚焦 ID 切换。

## 缩放：优先使用 `ScaleGestureDetector`

平台 `android.view.ScaleGestureDetector` 自 API 8 可用，它处理跨度（span）、焦点、指针增减
和部分异常序列。监听器的 `scaleFactor` 是相邻回调的倍率，不应当作累计倍率。

```kotlin
package com.example.input

import android.content.Context
import android.graphics.Canvas
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View

class ZoomCanvasView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var scale = 1f
    private var translationXModel = 0f
    private var translationYModel = 0f
    private var transformedInGesture = false

    private val scaleDetector = ScaleGestureDetector(
        context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
                transformedInGesture = true
                return true
            }

            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val old = scale
                val next = (old * detector.scaleFactor).coerceIn(0.5f, 5f)
                val applied = next / old

                // 保持 detector.focusX/Y 对应的内容点仍位于手指焦点下。
                translationXModel = detector.focusX -
                    (detector.focusX - translationXModel) * applied
                translationYModel = detector.focusY -
                    (detector.focusY - translationYModel) * applied
                scale = next
                postInvalidateOnAnimation() // 平台 View API 16
                return true
            }
        }
    )

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaleDetector.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                transformedInGesture = false
                return true
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                // 即使未越过缩放阈值，多指序列也不应在最后一指抬起时误报点击。
                transformedInGesture = true
                return true
            }
            MotionEvent.ACTION_UP -> {
                // detector 处理 UP 后 isInProgress 已可能变为 false，不能用它判断整段手势。
                if (!transformedInGesture) performClick()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                transformedInGesture = false
                return true
            }
        }
        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.save()
        canvas.translate(translationXModel, translationYModel)
        canvas.scale(scale, scale)
        drawScene(canvas)
        canvas.restore()
    }

    private fun drawScene(canvas: Canvas) {
        // 所有内容以模型坐标绘制。
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
```

> **注意**：若 `canvas.translate()`、`canvas.scale()` 的顺序变化，平移量所属坐标系也会变化。
> 绘制、命中测试和焦点保持必须使用同一套变换约定。

## 旋转：用两个 ID 计算有向角

角度可由 `atan2(y2-y1, x2-x1)` 得到。相邻两帧角度差要归一化到
`[-180°, 180°]`，否则跨越 `-180/180` 时会突然旋转近 360°。

```kotlin
import android.view.MotionEvent
import kotlin.math.atan2

private const val NO_ID = -1

private var firstId = NO_ID
private var secondId = NO_ID
private var previousAngle = 0f
private var rotationDegrees = 0f

private fun angle(event: MotionEvent, id1: Int, id2: Int): Float? {
    val i1 = event.findPointerIndex(id1)
    val i2 = event.findPointerIndex(id2)
    if (i1 < 0 || i2 < 0) return null
    val radians = atan2(
        event.getY(i2) - event.getY(i1),
        event.getX(i2) - event.getX(i1)
    )
    return Math.toDegrees(radians.toDouble()).toFloat()
}

private fun normalizedDelta(current: Float, previous: Float): Float {
    var delta = current - previous
    while (delta > 180f) delta -= 360f
    while (delta < -180f) delta += 360f
    return delta
}
```

事件处理遵循以下时序：

```text
第 1 指 DOWN       保存 firstId
第 2 指 POINTER_DOWN
                   保存 secondId，计算 previousAngle
MOVE               currentAngle - previousAngle
                   -> 归一化 -> 累加 rotationDegrees
                   -> previousAngle = currentAngle
任一参与指针 UP    结束旋转；若仍有两指，重新选对并重设基准角
UP / CANCEL        清空全部 ID 与状态
```

不要在参与指针变更后沿用旧角度基准，否则第一帧会跳变。若同时缩放和旋转，可让
`ScaleGestureDetector` 管缩放，自己的 ID 对管理旋转；两者都以双指焦点为 pivot 更新同一个
模型矩阵。

## 组合手势状态机

平移、缩放、旋转不应各自无条件写模型。可采用：

```text
ONE_FINGER_POSSIBLE
  |-- 超过 slop ----------------> PAN
  |-- 第二指按下 ---------------> TRANSFORM
PAN
  |-- 第二指按下 ---------------> TRANSFORM（重设跨度/角度基准）
TRANSFORM
  |-- 剩一指 -------------------> ONE_FINGER_POSSIBLE（重设位置基准）
任意状态
  |-- UP/CANCEL ----------------> IDLE
```

是否允许双指同时缩放与旋转取决于产品。若允许，应加旋转死区和缩放倍率过滤；若不允许，
可先越过阈值者锁定本序列。

## 历史采样与事件批处理

一个 `ACTION_MOVE` 可能携带历史坐标，可用 `historySize`、`getHistoricalX/Y()` 读取。绘图或
笔迹控件可以利用历史点改善连续性；普通拖动通常只需当前坐标。历史数组同样按当前事件的
pointer index 访问，因此先由 ID 查 index。

> **性能提示**：多指 `MOVE` 中避免创建 `PointF`、列表或临时矩阵。把累计变换保存在字段，
> 复用 `Matrix`，并在一帧内合并重绘请求。

## 常见陷阱

1. **缓存 pointer index**：另一指抬起后 index 压缩，坐标突然属于别人。
2. **用 `action` 直接比较**：该值还编码了 pointer index；应读 `actionMasked`。
3. **所有 `POINTER_UP` 都结束手势**：只有最后 `UP` 结束整个序列。
4. **活动指针切换不重置 lastX/lastY**：下一帧出现巨大位移。
5. **累计原始 `scaleFactor` 但不限幅**：内容可缩成零或放大到数值不稳定。
6. **跨 ±180° 直接相减**：产生近 360° 的角度突变。
7. **忽略 CANCEL**：残留 ID 让下一序列从错误状态开始。

## 实践检查清单

- [ ] 字段只保存 pointer ID，每次事件重新查 index。
- [ ] 使用 `actionMasked` 与 `actionIndex` 解析多指动作。
- [ ] 任一参与指针更换后重设位置、跨度和角度基准。
- [ ] 累计缩放有合理上下限，旋转差已归一化。
- [ ] 绘制、逆向命中和手势 pivot 使用同一坐标变换。
- [ ] 测试两指交叉、快速增减、活动指针先抬起及系统取消。

## 小结

多点触控可靠性的核心不是手指数，而是身份管理：ID 稳定、index 短暂。缩放可交给
`ScaleGestureDetector`，旋转用稳定 ID 对和归一化角差计算；每次指针集合改变都要重设基准。
最后用统一状态机和坐标模型组合平移、缩放、旋转，才能避免跳变与手势互相覆盖。

## 延伸阅读

- [Handle multi-touch gestures](https://developer.android.com/develop/ui/views/touch-and-input/gestures/multi)
- [MotionEvent](https://developer.android.com/reference/android/view/MotionEvent)
- [ScaleGestureDetector](https://developer.android.com/reference/android/view/ScaleGestureDetector)
