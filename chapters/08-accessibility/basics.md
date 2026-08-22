# 自定义控件无障碍基础

## 学习目标

- 把“画出来的像按钮”升级为可点击、可命名、可表达状态的语义节点。
- 理解 `performClick()`、节点语义与 `AccessibilityEvent` 的职责边界。
- 用自动化测试守住基础规则，并知道自动检查不能替代 TalkBack 验收。

## 1. 无障碍契约不是一句 contentDescription

辅助技术不会推断像素含义，而是消费 View 暴露的**语义（semantics）**：角色、名称、值、状态、可用操作和变化事件。生产级控件要让触摸、键盘、Switch Access 与 TalkBack 最终进入同一业务入口。

```text
触摸手势 ─┐
键盘 Enter ├─> performClick() ─> 业务状态更新 ─> 重绘/回调
辅助服务 ─┘       │                    │
                   └─ TYPE_VIEW_CLICKED └─ 状态/内容变化事件

像素：圆点 + 文字     语义：Button, “开始”, enabled, ACTION_CLICK
```

> **无障碍提示**：`contentDescription` 只解决“叫什么”，不能替代角色、状态、操作和事件。

## 2. 点击只有一个入口：performClick()

自定义 `onTouchEvent()` 识别出点击后必须调用 `performClick()`。覆盖方法时先调用 `super.performClick()`；它负责标准点击行为和无障碍事件，业务逻辑随后执行。不要在 `ACTION_UP` 与 `performClick()` 各写一次逻辑。

```kotlin
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat

class RecordButton @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    var recording: Boolean = false
        private set

    init {
        isClickable = true
        isFocusable = true
        ViewCompat.setAccessibilityDelegate(
            this,
            object : androidx.core.view.AccessibilityDelegateCompat() {
                override fun onInitializeAccessibilityNodeInfo(
                    host: View,
                    info: AccessibilityNodeInfoCompat,
                ) {
                    super.onInitializeAccessibilityNodeInfo(host, info)
                    info.className = android.widget.Button::class.java.name
                    info.text = if (recording) "停止录音" else "开始录音"
                    info.stateDescription = if (recording) "正在录音" else "未录音"
                }
            },
        )
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled) return false
        return when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                isPressed = true
                true
            }
            MotionEvent.ACTION_UP -> {
                val click = isPressed && event.x in 0f..width.toFloat() &&
                    event.y in 0f..height.toFloat()
                isPressed = false
                if (click) performClick()
                true
            }
            MotionEvent.ACTION_CANCEL -> {
                isPressed = false
                true
            }
            else -> true
        }
    }

    override fun performClick(): Boolean {
        if (!isEnabled) return false
        super.performClick()
        recording = !recording
        invalidate()
        // 状态已变化；让辅助技术重新读取节点属性。
        ViewCompat.notifyViewAccessibilityStateChangedIfNeeded(
            this,
            android.view.accessibility.AccessibilityEvent.CONTENT_CHANGE_TYPE_STATE_DESCRIPTION,
        )
        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        paint.color = if (recording) 0xffc62828.toInt() else 0xff2e7d32.toInt()
        canvas.drawCircle(width / 2f, height / 2f, minOf(width, height) * .4f, paint)
    }
}
```

若控件已有稳定可见文本，优先让节点复用该文本；不要同时设置重复的文本和描述，避免 TalkBack 朗读两次。图标按钮才通常需要本地化的 `contentDescription`。装饰图应设为无障碍不重要，而不是朗读“背景”。

## 3. 节点语义与事件

| 信息 | 节点属性/做法 | 示例 |
|---|---|---|
| 名称 | 可见文本或 `contentDescription` | “静音” |
| 角色 | 继承标准控件，或准确设置 `className` | `Button` |
| 状态 | `isChecked`、`isSelected`、`stateDescription` | “已静音” |
| 操作 | `isClickable`、`addAction()`、`performAccessibilityAction()` | 点击、增加 |
| 范围 | `RangeInfoCompat` | 亮度 40% |
| 变化 | 内容变化通知或针对虚拟节点发事件 | 数值已更新 |

事件是“发生了什么”，节点是“现在是什么”。不要每帧发送事件，也不要在一次点击中手工再发 `TYPE_VIEW_CLICKED`——`super.performClick()` 已处理标准路径。连续拖动值可节流后报告，最终值必须报告。

> **注意**：动态文本变化若需要主动播报，优先正确的 live region/内容变化通知；`announceForAccessibility()` 会打断朗读，应只用于确有必要、且没有更结构化表达的短消息。

## 4. 自定义动作

当动作无法用点击表达（例如“增加一天”），把它作为命名动作暴露，并令辅助动作和触摸动作调用同一函数。

```kotlin
private const val ACTION_INCREMENT = 0x01020001

// 在 AccessibilityDelegateCompat.onInitializeAccessibilityNodeInfo 中：
info.addAction(
    AccessibilityNodeInfoCompat.AccessibilityActionCompat(
        ACTION_INCREMENT,
        "增加一天",
    ),
)

// 在 delegate 中覆盖：
override fun performAccessibilityAction(host: View, action: Int, args: android.os.Bundle?): Boolean {
    return if (action == ACTION_INCREMENT) {
        incrementDay() // 与触摸按钮复用同一业务入口
        true
    } else {
        super.performAccessibilityAction(host, action, args)
    }
}
```

动作标签必须本地化，并描述结果而非手势（“删除项目”，不是“双击删除”）。

## 5. Kotlin 自动化测试

以下仪器测试同时验证可点击入口与 AndroidX Accessibility Test Framework 的基础规则：

```kotlin
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.accessibility.AccessibilityChecks
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RecordButtonAccessibilityTest {
    companion object {
        @JvmStatic
        @BeforeClass
        fun enableAccessibilityChecks() {
            AccessibilityChecks.enable().setRunChecksFromRootView(true)
        }
    }

    @Test
    fun click_usesPublicClickContract_andChangesState() {
        ActivityScenario.launch(RecordActivity::class.java).use { scenario ->
            onView(withId(R.id.record)).perform(click())
            scenario.onActivity { activity ->
                assertTrue(activity.findViewById<RecordButton>(R.id.record).recording)
            }
        }
    }
}
```

自动检查能发现缺少标签、目标过小等规则问题，却无法判断文案是否自然、焦点顺序是否符合任务流程。

## 常见陷阱

- 仅在 `ACTION_UP` 修改状态，导致辅助服务调用 `ACTION_CLICK` 无效。
- 覆盖 `performClick()` 却不调用 `super.performClick()`。
- 用 `contentDescription = "按钮"` 重复角色，却没有业务名称。
- 状态改变只 `invalidate()`，语义树仍是旧状态。
- 高频动画逐帧发事件，造成 TalkBack 噪声和主线程压力。
- 把多个可操作区域压成一个节点；这类控件应使用虚拟节点。

## 实践检查清单

- [ ] 每个操作都有稳定、可本地化的名称和准确角色。
- [ ] 触摸、键盘和辅助服务汇合到同一业务入口。
- [ ] 点击路径调用 `performClick()`，覆盖时调用 `super`。
- [ ] 禁用、选中、范围和错误状态均可从节点读取。
- [ ] 状态变化发送恰当且不过量的无障碍通知。
- [ ] 装饰元素不抢焦点；触摸目标至少满足产品无障碍规范。
- [ ] Espresso 已启用 `AccessibilityChecks`，并完成真机 TalkBack 验收。

## 小结

生产级无障碍契约由“可操作入口 + 完整语义节点 + 准确变化事件”组成。先统一行为入口，再补角色、名称和状态，最后以自动检查和辅助技术实测闭环。

## 延伸阅读

- [Android Developers：让自定义 View 更易于访问](https://developer.android.com/guide/topics/ui/accessibility/views/custom-views)
- [Android Developers：View 无障碍测试](https://developer.android.com/guide/topics/ui/accessibility/views/testing-views)
- [AndroidX `AccessibilityNodeInfoCompat`](https://developer.android.com/reference/kotlin/androidx/core/view/accessibility/AccessibilityNodeInfoCompat)
- [Android Developers：无障碍原则](https://developer.android.com/guide/topics/ui/accessibility/principles)
