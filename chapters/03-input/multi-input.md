# 键盘、鼠标与触控笔

## 学习目标

- 把控件能力抽象为输入无关的语义操作，而不是只监听触摸。
- 支持键盘焦点、方向键、Enter/Space 与取消键。
- 处理鼠标滚轮、悬停和辅助按钮。
- 根据触控笔工具类型、压力、倾斜和按钮调整笔迹。
- 让键鼠笔路径与点击、无障碍和生命周期保持一致。

## 先设计语义，再绑定设备

一个“增加数值”操作可来自触摸拖动、方向键、鼠标滚轮或无障碍动作。若每种输入直接修改
不同字段，边界、回调和状态很快分叉。推荐先定义：

```text
输入事件             设备适配层            统一语义层
触摸拖动 ----------- map delta ----------- setValue / panBy
方向键 ------------- map direction ------- increment / moveFocus
鼠标滚轮 ----------- map axis ------------ scrollByStep
触控笔轨迹 ---------- map pressure -------- appendStrokePoint
                                             |
                                             v
                                   限幅、通知、绘制、无障碍
```

平台核心类型包括 `android.view.KeyEvent`、`MotionEvent`、`InputDevice`。本章示例中的
`ViewCompat` 来自 AndroidX Core。

## 键盘：焦点是前提

自定义 View 要能被键盘操作，首先需要可聚焦。在 XML 可设置 `android:focusable="true"`；
代码中设置 `isFocusable = true`，触摸模式下如需聚焦再设置 `isFocusableInTouchMode = true`。
不要在每次绘制时请求焦点。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.KeyEvent
import android.view.View

class KeyboardSliderView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var value = 0

    init {
        isFocusable = true
        isClickable = true
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_DOWN -> {
                changeValueBy(-1)
                true
            }
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_UP -> {
                changeValueBy(1)
                true
            }
            KeyEvent.KEYCODE_ENTER,
            KeyEvent.KEYCODE_DPAD_CENTER,
            KeyEvent.KEYCODE_SPACE -> {
                // 让基类维护按键点击语义；若需自定义按压态，应匹配 onKeyUp。
                super.onKeyDown(keyCode, event)
            }
            else -> super.onKeyDown(keyCode, event)
        }
    }

    private fun changeValueBy(delta: Int) {
        val next = (value + delta).coerceIn(0, 100)
        if (next == value) return
        value = next
        invalidate()
        sendAccessibilityEvent(
            android.view.accessibility.AccessibilityEvent.TYPE_VIEW_SELECTED
        )
    }

    override fun performClick(): Boolean {
        super.performClick()
        // 点击对应的业务动作，例如切换编辑模式。
        return true
    }
}
```

> **注意**：键盘行为主要由平台 `View`/`KeyEvent` 完成；不要为了“启用键盘”清除已有的
> 无障碍 delegate。若控件暴露自定义无障碍 action，应在原有 delegate 上扩展。

方向应考虑 RTL（right-to-left）。如果键代表视觉方向，用 `layoutDirection` 决定增减含义；
如果代表数值增减，应按产品语义而不是镜像。长按按键会产生重复 `ACTION_DOWN`，可利用
`event.repeatCount`，也可在不希望连续变化时忽略大于 0 的重复事件。

## 鼠标滚轮：走 `onGenericMotionEvent()`

滚轮通常产生 `ACTION_SCROLL`，不是触摸 `MOVE`。先确认来源包含
`InputDevice.SOURCE_CLASS_POINTER`，再读取 `AXIS_VSCROLL` 和 `AXIS_HSCROLL`。平台常量
`ViewConfiguration.scaledVerticalScrollFactor` / `scaledHorizontalScrollFactor` 自 API 26
公开；若 `minSdk < 26`，可使用 AndroidX 的
`ViewConfigurationCompat.getScaledVerticalScrollFactor()`。

```kotlin
import android.view.InputDevice
import android.view.MotionEvent
import android.view.ViewConfiguration
import androidx.core.view.ViewConfigurationCompat

private val viewConfig = ViewConfiguration.get(context)

private fun verticalScrollFactor(): Float =
    ViewConfigurationCompat.getScaledVerticalScrollFactor(viewConfig, context)

private fun horizontalScrollFactor(): Float =
    ViewConfigurationCompat.getScaledHorizontalScrollFactor(viewConfig, context)

override fun onGenericMotionEvent(event: MotionEvent): Boolean {
    val isPointer = event.isFromSource(InputDevice.SOURCE_CLASS_POINTER)
    if (isPointer && event.actionMasked == MotionEvent.ACTION_SCROLL) {
        val v = event.getAxisValue(MotionEvent.AXIS_VSCROLL)
        val h = event.getAxisValue(MotionEvent.AXIS_HSCROLL)
        if (v != 0f || h != 0f) {
            panBy(
                dx = -h * horizontalScrollFactor(),
                dy = -v * verticalScrollFactor()
            )
            return true
        }
    }
    return super.onGenericMotionEvent(event)
}
```

滚轮轴值通常只表达刻度，不等于像素；乘系统因子可获得与设备配置一致的距离。触控板可能
产生更细密的轴值，不要强制取整后再累计，否则小量会全部丢失。

## 悬停、鼠标按钮和上下文操作

鼠标与悬停触控笔可产生 `ACTION_HOVER_ENTER/MOVE/EXIT`。悬停不等于按下，适合更新热点、
提示或光标，不应提交绘制。平台 `View.onHoverEvent()` 可处理它；若控件可点击，优先设置
`tooltipText`（API 26）或 `TooltipCompat`（AndroidX AppCompat）提供提示。

```kotlin
import android.graphics.PointF
import android.view.MotionEvent

private var hoverPoint: PointF? = null

override fun onHoverEvent(event: MotionEvent): Boolean {
    when (event.actionMasked) {
        MotionEvent.ACTION_HOVER_ENTER,
        MotionEvent.ACTION_HOVER_MOVE -> {
            val point = hoverPoint ?: PointF().also { hoverPoint = it }
            point.set(event.x, event.y)
            invalidate()
            return true
        }
        MotionEvent.ACTION_HOVER_EXIT -> {
            hoverPoint = null
            invalidate()
            return true
        }
    }
    return super.onHoverEvent(event)
}
```

鼠标主键通常进入触摸分发。通过 `event.buttonState` 检查
`MotionEvent.BUTTON_SECONDARY`（API 14）可触发上下文语义，但建议使用
`View.setOnContextClickListener`（API 23）或兼容组件，以便系统统一处理。不要仅凭
`toolType == MOUSE` 推断当前按了哪个键。

## 触控笔：工具类型与连续轴

通过 `event.getToolType(index)` 可区分：

- `TOOL_TYPE_FINGER`：手指。
- `TOOL_TYPE_STYLUS`：笔尖。
- `TOOL_TYPE_ERASER`：橡皮端。
- `TOOL_TYPE_MOUSE`：鼠标。

压力 `getPressure(index)` 通常归一化，但硬件范围和曲线并不完全一致；倾斜可读
`AXIS_TILT`，方位常用 `AXIS_ORIENTATION`。并非所有设备提供所有轴，应有默认值和限幅。

```kotlin
package com.example.input

import android.content.Context
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View

class StylusPadView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var drawing = false

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val actionIndex = when (event.actionMasked) {
            MotionEvent.ACTION_POINTER_DOWN,
            MotionEvent.ACTION_POINTER_UP -> event.actionIndex
            else -> 0
        }.coerceAtMost(event.pointerCount - 1)

        val tool = event.getToolType(actionIndex)
        val isPen = tool == MotionEvent.TOOL_TYPE_STYLUS ||
            tool == MotionEvent.TOOL_TYPE_ERASER

        if (!isPen) return super.onTouchEvent(event)

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                drawing = true
                appendPoint(event, 0)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                if (!drawing) return true
                // 消费批处理的历史点，避免快速书写出现断线。
                for (h in 0 until event.historySize) appendHistoricalPoint(event, 0, h)
                appendPoint(event, 0)
                postInvalidateOnAnimation()
                return true
            }
            MotionEvent.ACTION_UP -> {
                appendPoint(event, 0)
                drawing = false
                invalidate()
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                drawing = false
                return true
            }
        }
        return true
    }

    private fun appendPoint(event: MotionEvent, index: Int) {
        val erasing = event.getToolType(index) == MotionEvent.TOOL_TYPE_ERASER
        val pressure = event.getPressure(index).coerceIn(0f, 1f)
        val tilt = event.getAxisValue(MotionEvent.AXIS_TILT, index)
        addToStroke(event.getX(index), event.getY(index), pressure, tilt, erasing)
    }

    private fun appendHistoricalPoint(event: MotionEvent, index: Int, history: Int) {
        val erasing = event.getToolType(index) == MotionEvent.TOOL_TYPE_ERASER
        val pressure = event.getHistoricalPressure(index, history).coerceIn(0f, 1f)
        addToStroke(
            event.getHistoricalX(index, history),
            event.getHistoricalY(index, history),
            pressure,
            0f, // 历史倾斜可按设备/API 需求读取对应 historical axis
            erasing
        )
    }

    private fun addToStroke(
        x: Float,
        y: Float,
        pressure: Float,
        tilt: Float,
        erasing: Boolean
    ) {
        // 写入复用的笔迹缓冲；笔宽可由 pressure 映射。
    }
}
```

> **性能提示**：笔事件采样率可能很高。复用点缓冲，批量构造 `Path`，避免每个采样点创建
> 对象或调用 `requestLayout()`。历史采样可提高轨迹完整性。

触控笔侧键通过 `buttonState` 检查 `BUTTON_STYLUS_PRIMARY` / `BUTTON_STYLUS_SECONDARY`
（API 23）。按钮映射因设备而异，应允许用户配置，不应硬编码为唯一擦除方式。

## 同时存在多种来源时

事件来源由 `event.source` 位标志描述，使用 `isFromSource()`，不要用等号，因为一个来源可
包含多个类别。不同输入可能交错：鼠标悬停仍在，键盘改变焦点；触控笔按下时系统取消原触摸
序列。每条路径应更新共享模型，但各自维护短暂输入状态。

```text
共享模型：value / viewport / strokes
     ^             ^             ^
     |             |             |
键盘焦点状态   鼠标 hover 状态   笔 drawing 状态
     |             |             |
  KeyEvent     GenericMotion    Touch MotionEvent

任一路径只通过语义方法改共享模型；CANCEL/焦点丢失只清自己的瞬态状态。
```

## 无障碍与反馈

> **无障碍提示**：键盘可操作不等于无障碍完整。控件还应报告 role、范围、当前值和可用
> action；触摸点击必须走 `performClick()`。焦点指示应在 `isFocused` 时清晰可见，不能只靠
> hover。自定义范围控件可通过 `AccessibilityNodeInfo.RangeInfo` 描述数值。

输入反馈应匹配来源：鼠标悬停可显示热点，键盘焦点需要持久焦点环，触控笔按压可预览笔宽。
不要把震动绑定到每个滚轮刻度或笔采样点。

## 生命周期清理

在 `onFocusChanged(..., hasFocus=false, ...)` 取消键盘按压/编辑态；在
`ACTION_HOVER_EXIT` 清悬停；在 `ACTION_CANCEL` 结束笔迹但不提交；在
`onDetachedFromWindow()` 清除延迟任务、光标动画和输入缓冲。若中途切换工具类型，先结束
旧工具状态，再开始新状态。

## 常见陷阱

1. **只实现触摸**：Chromebook、键盘导航和鼠标滚轮无法使用。
2. **滚轮放在 `onTouchEvent()`**：`ACTION_SCROLL` 通常走 generic motion 路径。
3. **轴值直接当像素**：设备间滚动距离差异巨大。
4. **用 `source == MOUSE`**：忽略来源是位集合，判断失败。
5. **悬停时提交操作**：光标经过就触发业务。
6. **假设压力始终可靠**：不支持压力的设备可能持续返回默认值。
7. **忽略历史点**：高速笔迹断裂或棱角明显。
8. **焦点不可见**：键盘用户不知道操作对象。

## 实践检查清单

- [ ] 业务变化集中在输入无关的语义方法中。
- [ ] View 可聚焦，有可见焦点态，方向键与 Enter/Space 行为明确。
- [ ] 鼠标滚轮读取正确轴并乘系统滚动因子。
- [ ] hover、主键、辅助键和上下文操作语义分离。
- [ ] 笔迹读取工具类型、压力与历史点，并提供缺失轴的退化行为。
- [ ] 使用 `isFromSource()` 判断来源。
- [ ] 取消、焦点丢失和脱离窗口都清理对应瞬态状态。
- [ ] 无障碍 action 与键鼠触摸调用同一语义层。

## 小结

多输入支持不是为触摸代码增加更多 `if`，而是把设备事件翻译为统一语义。键盘依赖焦点，
鼠标滚轮走 generic motion，触控笔提供压力、倾斜与历史采样。明确来源、轴单位和生命周期，
再让所有输入共享边界与反馈，控件才能在手机、平板与桌面形态中保持一致。

## 延伸阅读

- [Handle keyboard input](https://developer.android.com/develop/ui/views/touch-and-input/keyboard-input)
- [Handle mouse actions](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/mouse)
- [Advanced stylus features](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features)
- [MotionEvent axes](https://developer.android.com/reference/android/view/MotionEvent)
