# 键盘焦点、语义与测试

## 学习目标

- 区分输入焦点、键盘焦点与无障碍焦点，避免彼此抢占。
- 让 D-pad、Tab、Enter/Space 与 TalkBack 操作共享业务语义。
- 建立静态检查、自动化、真机 TalkBack 和人工任务测试的分层门禁。

## 1. 三种焦点不要混为一谈

```text
输入焦点            键盘焦点                    无障碍焦点
EditText 光标        Tab / D-pad 当前目标         TalkBack 当前朗读节点
系统输入法消费       KeyEvent/FocusFinder 消费     AccessibilityService 消费
        \                |                         /
         \---------------业务动作-----------------/
```

键盘焦点由 View 层级导航；无障碍焦点由服务管理，可能落在虚拟节点上。不要在 `onFocusChanged()` 中调用 `requestAccessibilityFocus()` 强行同步，也不要在内容刷新时反复 `requestFocus()`。

## 2. 键盘契约

可操作控件至少应：`isFocusable = true`，使用逻辑方向，Enter/Space 触发与触摸相同的 `performClick()`。复杂控件可以用方向键移动内部选择，但必须提供可退出路径，不能形成“键盘陷阱”。

```kotlin
import android.content.Context
import android.util.AttributeSet
import android.view.KeyEvent
import android.view.View
import androidx.core.view.ViewCompat

class StepperView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    var value: Int = 0
        private set

    init {
        isFocusable = true
        isClickable = true
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (!isEnabled) return super.onKeyDown(keyCode, event)
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT -> {
                changeBy(if (layoutDirection == LAYOUT_DIRECTION_RTL) 1 else -1)
                true
            }
            KeyEvent.KEYCODE_DPAD_RIGHT -> {
                changeBy(if (layoutDirection == LAYOUT_DIRECTION_RTL) -1 else 1)
                true
            }
            KeyEvent.KEYCODE_ENTER,
            KeyEvent.KEYCODE_DPAD_CENTER,
            KeyEvent.KEYCODE_SPACE -> performClick()
            else -> super.onKeyDown(keyCode, event)
        }
    }

    override fun performClick(): Boolean {
        super.performClick()
        resetToDefault()
        return true
    }

    private fun changeBy(delta: Int) {
        val next = (value + delta).coerceIn(0, 10)
        if (next == value) return
        value = next
        invalidate()
        ViewCompat.notifyViewAccessibilityStateChangedIfNeeded(
            this,
            android.view.accessibility.AccessibilityEvent.CONTENT_CHANGE_TYPE_UNDEFINED,
        )
    }

    private fun resetToDefault() {
        value = 5
        invalidate()
    }
}
```

若 Space 需要在按下时显示 pressed、抬起时执行，应成对处理 `onKeyDown`/`onKeyUp` 与重复事件；上例适合无长按语义的简单控件。焦点高亮必须在浅色/深色、高对比度和 disabled 状态下仍清楚。

> **注意**：XML 的 `nextFocusForward` 等显式关系只能修正稳定布局。响应式/动态界面中硬编码 ID 网络容易产生循环和隐藏目标，应优先让布局顺序自然正确。

## 3. TalkBack 验收路径

TalkBack 的滑动遍历、触摸探索和“操作”菜单可能走不同路径。每个关键任务都应执行以下人工脚本：

```text
开启 TalkBack
  ├─ 单指左右滑：顺序、名称、角色、状态
  ├─ 触摸探索：命中区域与视觉位置一致
  ├─ 双击激活：与普通点击结果一致
  ├─ 操作菜单：自定义动作名称清楚且成功
  ├─ 内容更新：焦点不丢失、不重复播报
  └─ 返回/旋转/恢复：回到合理上下文
```

不要只问“能不能读到”，还要验证用户能否独立完成任务。测试文案应关注结果，例如“音量，40%，可调整”，避免颜色、坐标和手势依赖。

## 4. 自动化质量金字塔

```text
                    / 真机人工：TalkBack + 任务完成 \
                   / 仪器：Espresso + AccessibilityChecks \
                  / Robolectric：节点属性、键盘状态机       \
                 / lint：标签、触摸目标、资源问题            \
```

`AccessibilityChecks` 在 ViewAction 前后审计层级，适合 CI 快速拦截明显问题，但不能评估业务文案和整个流程。

```kotlin
import android.view.KeyEvent
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.accessibility.AccessibilityChecks
import androidx.test.espresso.action.ViewActions.pressKey
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.hasFocus
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.BeforeClass
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class StepperKeyboardTest {
    companion object {
        @JvmStatic @BeforeClass
        fun a11yGate() {
            AccessibilityChecks.enable().setRunChecksFromRootView(true)
        }
    }

    @Test
    fun tabThenEnter_reachesControlAndUsesClickAction() {
        ActivityScenario.launch(StepperActivity::class.java).use { scenario ->
            onView(withId(R.id.before)).perform(pressKey(KeyEvent.KEYCODE_TAB))
            onView(withId(R.id.stepper)).check(matches(hasFocus()))
            onView(withId(R.id.stepper)).perform(pressKey(KeyEvent.KEYCODE_ENTER))
            scenario.onActivity { activity ->
                assertEquals(5, activity.findViewById<StepperView>(R.id.stepper).value)
            }
        }
    }
}
```

实际项目更应断言确认文本等用户可见结果；组件级测试也可断言公开业务状态，但不要只断言“收到按键”。

Robolectric 可快速验证 key mapping：

```kotlin
import android.view.KeyEvent
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.robolectric.RobolectricTestRunner
import org.junit.runner.RunWith

@RunWith(RobolectricTestRunner::class)
class StepperViewLocalTest {
    @Test
    fun rightArrow_inLtr_incrementsValue() {
        val view = StepperView(ApplicationProvider.getApplicationContext())
        view.layoutDirection = View.LAYOUT_DIRECTION_LTR
        view.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DPAD_RIGHT))
        assertEquals(1, view.value)
    }
}
```

## 5. 焦点恢复与动态内容

- 删除当前项：把焦点交给逻辑上的下一个项，若无则交给上一个或容器标题。
- 插入非紧急内容：不要偷焦点；用结构化状态变化提示。
- 页面切换：焦点落在新页面标题或首个任务目标，而非返回到隐藏 View。
- 旋转/进程恢复：恢复业务选择不等于盲目恢复过期的节点 ID。
- 弹窗关闭：焦点返回触发弹窗的控件。

> **无障碍提示**：程序化焦点移动必须可预测、与用户刚完成的动作存在因果关系。

## 常见陷阱

- 把 `focused` 当作无障碍焦点，TalkBack 朗读与视觉高亮错位。
- 仅监听触摸，不支持 Enter、Space 或 D-pad center。
- 左右键逻辑忽略 RTL。
- 动态更新总是抢焦点，用户无法继续阅读。
- 显式 next-focus 形成循环或指向 `GONE` View。
- 只跑 AccessibilityChecks 就宣称“已支持 TalkBack”。
- 测试只断言事件被发送，不断言用户可见结果。

## 实践检查清单

- [ ] Tab/D-pad 顺序与视觉和任务顺序一致，无陷阱。
- [ ] Enter、Space、D-pad center 与点击共享动作入口。
- [ ] 左右方向在 RTL 下语义正确。
- [ ] 焦点样式清楚，且不依赖颜色作为唯一线索。
- [ ] 动态插入、删除、弹窗和配置变化均有焦点策略。
- [ ] CI 运行 lint、Robolectric、仪器测试和 AccessibilityChecks。
- [ ] 至少一台真实设备完成 TalkBack 滑动、探索、激活和恢复脚本。
- [ ] 自动化断言业务结果，人工验收文案与任务完成度。

## 小结

焦点是多套系统对同一业务语义的入口，而不是一个全局布尔值。生产级策略让每套焦点各司其职、所有输入共享动作，并用分层测试覆盖规则、机制与真实体验。

## 延伸阅读

- [Android Developers：测试应用无障碍](https://developer.android.com/guide/topics/ui/accessibility/testing)
- [Android Developers：View 无障碍测试](https://developer.android.com/guide/topics/ui/accessibility/views/testing-views)
- [Android Developers：Espresso AccessibilityChecks](https://developer.android.com/training/testing/espresso/accessibility-checking)
- [Android Developers：Android TV 自定义 View 无障碍](https://developer.android.com/training/tv/accessibility/custom-views)
- [Android Developers：键盘输入](https://developer.android.com/develop/ui/views/touch-and-input/keyboard-input)
