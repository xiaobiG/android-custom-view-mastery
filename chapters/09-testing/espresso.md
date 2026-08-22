# Espresso 手势与断言

## 学习目标

- 用 Espresso 从用户视角验证自定义 View，而非调用私有方法。
- 编写有约束、可诊断、线程安全的自定义 `ViewAction`。
- 正确处理动画/异步空闲、坐标手势与 `AccessibilityChecks`。

## 1. Espresso 的测试边界

```text
onView(matcher)
   ├─ 唯一定位目标
   ├─ 等待主线程/已注册 IdlingResource 空闲
   ├─ perform(ViewAction)
   └─ check(ViewAssertion) ─> 用户可见结果
```

Espresso 同步主线程消息队列，但不知道未注册的后台任务、自定义 executor 或无限动画。不要用 `Thread.sleep()` 猜时间；让生产异步源暴露 `IdlingResource`、可注入调度器或稳定的完成信号。

## 2. 基础交互测试

```kotlin
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RatingFlowTest {
    @Test fun selectingRating_updatesConfirmation() {
        ActivityScenario.launch(RatingActivity::class.java).use {
            onView(withId(R.id.rating)).perform(selectRating(4))
            onView(withId(R.id.confirmation))
                .check(matches(withText("已选择 4 星")))
                .check(matches(isDisplayed()))
        }
    }
}
```

断言业务结果比断言 `rating` 私有字段更能抵抗重构。

## 3. 自定义 ViewAction 完整模板

自定义控件优先暴露语义操作；只有 Espresso 标准动作无法表达时才写 `ViewAction`。动作应声明约束、给出清晰描述、在 UI 线程操作，并在不满足前置条件时提供可读错误。

```kotlin
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import androidx.test.espresso.action.GeneralClickAction
import androidx.test.espresso.action.Press
import androidx.test.espresso.action.Tap
import androidx.test.espresso.UiController
import androidx.test.espresso.ViewAction
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import org.hamcrest.Matcher
import org.hamcrest.Matchers.allOf

fun selectRating(value: Int): ViewAction = object : ViewAction {
    override fun getConstraints(): Matcher<View> = allOf(
        isDisplayed(),
        isAssignableFrom(AccessibleRatingView::class.java),
    )

    override fun getDescription(): String =
        "select rating $value through the public custom-view API"

    override fun perform(uiController: UiController, view: View) {
        require(value in 1..5) { "rating must be in 1..5, was $value" }
        val xFraction = (value - .5f) / 5f
        val click = GeneralClickAction(
            Tap.SINGLE,
            { target ->
                val location = IntArray(2)
                target.getLocationOnScreen(location)
                floatArrayOf(
                    location[0] + target.width * xFraction,
                    location[1] + target.height * .5f,
                )
            },
            Press.FINGER,
            InputDevice.SOURCE_TOUCHSCREEN,
            MotionEvent.BUTTON_PRIMARY,
        )
        click.perform(uiController, view)
    }
}
```

这个 action 通过真实点击驱动控件，没有为了测试公开危险 setter。若组件本来就有稳定的公共语义 API，也可直接调用它，但要确保该 API 与触摸和无障碍路径共享业务入口。

### 坐标手势

```kotlin
import androidx.test.espresso.action.GeneralClickAction
import androidx.test.espresso.action.Press
import androidx.test.espresso.action.Tap
import androidx.test.espresso.action.CoordinatesProvider
import android.view.InputDevice
import android.view.MotionEvent

fun clickFraction(xFraction: Float, yFraction: Float = .5f): ViewAction {
    require(xFraction in 0f..1f && yFraction in 0f..1f)
    val coordinates = CoordinatesProvider { view ->
        val location = IntArray(2)
        view.getLocationOnScreen(location)
        floatArrayOf(
            location[0] + view.width * xFraction,
            location[1] + view.height * yFraction,
        )
    }
    return GeneralClickAction(
        Tap.SINGLE,
        coordinates,
        Press.FINGER,
        InputDevice.SOURCE_TOUCHSCREEN,
        MotionEvent.BUTTON_PRIMARY,
    )
}
```

这里返回屏幕坐标，且以实际布局后的尺寸计算；若控件有 padding/RTL，测试 API 应将业务值转换为坐标并覆盖这两种条件。比起直接构造 `MotionEvent`，Espresso 手势更接近用户路径。

> **注意**：坐标测试天然比语义测试脆弱。只把它用于命中测试、拖动状态机等坐标本身就是需求的场景。
> 上例使用当前非废弃的五参数 `GeneralClickAction` 构造器；项目需锁定提供该构造器的
> `androidx.test.espresso:espresso-core` 版本。若项目版本不同，以该锁定版本的 API 为准，
> 不要退回已废弃的三参数构造器而不记录版本边界。

## 4. 自定义断言与诊断

```kotlin
import androidx.test.espresso.ViewAssertion
import org.hamcrest.MatcherAssert.assertThat
import org.hamcrest.Matchers.`is`

fun hasRating(expected: Int) = ViewAssertion { view, noViewFound ->
    if (noViewFound != null) throw noViewFound
    val rating = view as? AccessibleRatingView
        ?: throw AssertionError("Expected AccessibleRatingView, was ${view.javaClass.name}")
    assertThat("public rating", rating.rating, `is`(expected))
}
```

优先使用可见文本/无障碍状态；公开组件库 API 才适合直接断言公开属性。失败消息要带预期、实际和目标类型，避免只得到 `AssertionError`。

## 5. AccessibilityChecks 作为全局门禁

```kotlin
import androidx.test.espresso.accessibility.AccessibilityChecks
import org.junit.BeforeClass

companion object {
    @JvmStatic @BeforeClass
    fun enableA11yChecks() {
        AccessibilityChecks.enable()
            .setRunChecksFromRootView(true)
    }
}
```

它会在 Espresso 动作周围检查 View 层级。全局启用后，对已评估的第三方问题只做最窄的 suppress，并附 issue、负责人和到期时间；禁止一键忽略整个规则类别。

## 6. 异步与动画

```text
可控异步 ─> 注入 test dispatcher / fake repository
不可替换异步 ─> 注册 CountingIdlingResource
无限动画 ─> 测试配置关闭或替换时钟
绝不使用 ─> sleep(2000)
```

```kotlin
val idling = androidx.test.espresso.idling.CountingIdlingResource("rating-load")

fun load() {
    idling.increment()
    repository.load { result ->
        try { render(result) } finally { idling.decrement() }
    }
}
```

注册与注销放在 rule/`@Before`、`@After` 成对管理；每条异常路径都必须 decrement，否则测试永久等待。

## 常见陷阱

- matcher 不唯一，测试偶发命中另一个重复 ID/文本。
- `ViewAction.getConstraints()` 返回 `any(View::class.java)`，错误到 perform 才爆炸。
- 在 action 中启动后台线程或使用 sleep。
- 直接调用私有监听器，绕过触摸、点击和无障碍入口。
- 坐标写死 px，在密度、RTL、padding 改变后失败。
- 动画无限运行，Espresso 永远等不到 idle。
- AccessibilityChecks 只在单个烟雾测试开启，覆盖不足。

## 实践检查清单

- [ ] matcher 唯一、稳定，不依赖翻译文本或列表位置（除非它们就是需求）。
- [ ] 自定义 action 有严格约束、清晰描述和参数验证。
- [ ] 交互走公开语义或真实手势，断言用户可见结果。
- [ ] 坐标由已布局 View 计算，并覆盖 RTL/padding/密度。
- [ ] 异步使用 IdlingResource 或可注入调度器，无 `Thread.sleep()`。
- [ ] 动画在测试环境可控，注册资源成对清理。
- [ ] `AccessibilityChecks` 从根运行，suppress 有期限和责任人。
- [ ] 失败信息足以定位目标、预期和实际值。

## 小结

可靠 Espresso 测试 = 稳定定位 + 与用户一致的动作 + 明确同步 + 可观察结果。自定义 `ViewAction` 是语义适配器，不应成为绕过组件契约的后门。

## 延伸阅读

- [Android Developers：Espresso 基础](https://developer.android.com/training/testing/espresso/basics)
- [AndroidX `ViewAction` API](https://developer.android.com/reference/androidx/test/espresso/ViewAction)
- [Android Developers：Espresso Idling Resources](https://developer.android.com/training/testing/espresso/idling-resource)
- [Android Developers：Espresso 无障碍检查](https://developer.android.com/training/testing/espresso/accessibility-checking)
- [Android Developers：测试应用无障碍（Views）](https://developer.android.com/guide/topics/ui/accessibility/views/testing-views)
