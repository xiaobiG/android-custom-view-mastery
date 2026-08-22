# 单元测试与测量测试

## 学习目标

- 把自定义 View 的测量、状态和绘制前置条件拆成可验证契约。
- 正确选择纯 JVM、Robolectric 与仪器测试层级。
- 覆盖 `MeasureSpec` 组合、最小尺寸、padding、RTL 与配置边界。

## 1. 测什么，而不是在哪测

```text
业务/几何纯函数 ──> JVM JUnit：毫秒级、无 Android 运行时
View 测量/资源   ──> Robolectric：本地 JVM + Android shadow
平台真实行为    ──> Instrumentation：模拟器/真机
端到端交互      ──> Espresso：用户可见结果
```

生产级套件把算法从 View 中提取成纯函数，大量组合在 JVM 层验证；再用少量 Robolectric 和仪器测试确认 Android 边界。不要因本地测试快就假设它等同真实渲染。

## 2. 测量契约矩阵

`onMeasure()` 的输入不是宽高，而是父容器给出的 mode + size。至少覆盖：

| 宽 | 高 | 预期重点 |
|---|---|---|
| EXACTLY | EXACTLY | 严格服从父尺寸 |
| EXACTLY | AT_MOST | 固定宽，自适应高但不越界 |
| AT_MOST | AT_MOST | 建议尺寸、padding、最小值受上限约束 |
| UNSPECIFIED | UNSPECIFIED | 内容建议尺寸，不意外为 0 |

```text
MeasureSpec(mode, size)
        │
        v
 desired = content + padding
        │
        v
 resolveSizeAndState(desired, spec, childState)
        │
        ├─ measuredWidth / measuredHeight
        └─ MEASURED_STATE_TOO_SMALL（若内容被压缩）
```

> **注意**：测试不要复刻生产算法再比较两个相同错误；断言外部契约和关键不变量。

## 3. Robolectric 测量测试

Gradle 需启用 Android 资源：

```kotlin
android {
    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:<project-version>")
    testImplementation("androidx.test:core-ktx:<project-version>")
}
```

不要从教材复制“最新版本”；版本应由项目 version catalog 锁定并由依赖更新流程维护。

```kotlin
import android.view.View
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class GaugeViewMeasureTest {
    private fun spec(size: Int, mode: Int) = View.MeasureSpec.makeMeasureSpec(size, mode)

    @Test
    fun exactlyExactly_obeysParent() {
        val view = GaugeView(ApplicationProvider.getApplicationContext())
        view.measure(spec(320, View.MeasureSpec.EXACTLY), spec(96, View.MeasureSpec.EXACTLY))
        assertEquals(320, view.measuredWidth)
        assertEquals(96, view.measuredHeight)
    }

    @Test
    fun atMost_includesPadding_withoutExceedingParent() {
        val view = GaugeView(ApplicationProvider.getApplicationContext()).apply {
            setPadding(11, 13, 17, 19)
            minimumWidth = 80
            minimumHeight = 64
        }
        view.measure(spec(100, View.MeasureSpec.AT_MOST), spec(90, View.MeasureSpec.AT_MOST))
        assertTrue(view.measuredWidth in 80..100)
        assertTrue(view.measuredHeight in 64..90)
    }

    @Test
    fun tinyAtMost_setsTooSmallState() {
        val view = GaugeView(ApplicationProvider.getApplicationContext())
        view.measure(spec(1, View.MeasureSpec.AT_MOST), spec(1, View.MeasureSpec.AT_MOST))
        assertTrue(view.measuredWidth <= 1)
        assertTrue(
            view.measuredWidthAndState and View.MEASURED_STATE_TOO_SMALL != 0 ||
                view.measuredHeightAndState and View.MEASURED_STATE_TOO_SMALL != 0,
        )
    }
}
```

只有生产代码确实用 `resolveSizeAndState()` 表达 too-small 时，最后一个断言才是契约；否则先决定 API 契约，不要让测试臆造行为。

### 参数化覆盖

```kotlin
@RunWith(org.junit.runners.Parameterized::class)
class MeasureConstraintTest(
    private val mode: Int,
    private val limit: Int,
) {
    companion object {
        @JvmStatic @org.junit.runners.Parameterized.Parameters
        fun cases() = listOf(
            arrayOf(View.MeasureSpec.EXACTLY, 120),
            arrayOf(View.MeasureSpec.AT_MOST, 120),
            arrayOf(View.MeasureSpec.UNSPECIFIED, 0),
        )
    }

    @Test fun measuredSize_respectsModeInvariant() {
        val view = GaugeView(ApplicationProvider.getApplicationContext())
        view.measure(View.MeasureSpec.makeMeasureSpec(limit, mode),
            View.MeasureSpec.makeMeasureSpec(limit, mode))
        when (mode) {
            View.MeasureSpec.EXACTLY -> assertEquals(limit, view.measuredWidth)
            View.MeasureSpec.AT_MOST -> assertTrue(view.measuredWidth <= limit)
            View.MeasureSpec.UNSPECIFIED -> assertTrue(view.measuredWidth >= 0)
        }
    }
}
```

## 4. 仪器测试验证平台边界

字体、硬件栈、真实资源 qualifier 或 API 差异有风险时，在 `androidTest` 做窄而关键的验证：

```kotlin
import android.view.View
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class GaugeMeasureDeviceTest {
    @Test fun attachedView_exactWidth_survivesLayoutPass() {
        ActivityScenario.launch(GaugeHostActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val view = activity.findViewById<GaugeView>(R.id.gauge)
                val width = 240
                view.measure(
                    View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(500, View.MeasureSpec.AT_MOST),
                )
                view.layout(0, 0, view.measuredWidth, view.measuredHeight)
                assertEquals(width, view.width)
            }
        }
    }
}
```

所有 View 操作都在主线程执行；`scenario.onActivity` 提供这个保证。测试结束用 `use` 关闭场景，避免跨测试泄漏。

## 5. 状态、属性与生命周期

除了测量，还应测试：

- XML 属性默认值、显式值与非法输入策略。
- setter 是否按需调用 `requestLayout()` 或 `invalidate()`。
- 保存/恢复公开状态，且恢复不触发重复业务回调。
- `onDetachedFromWindow()` 移除 callback、listener、animator。
- RTL 与 fontScale 改变后重新计算几何。

可用 Robolectric shadow 断言失效请求，但优先断言最终尺寸/状态，避免绑定 shadow 实现细节。

## 常见陷阱

- 只测 `EXACTLY`，遗漏 wrap_content 的 `AT_MOST` 缺陷。
- 单位混乱：把 dp 当 px，测试恰好在 mdpi 通过。
- 在 JVM 测试依赖未 shadow 的平台渲染细节。
- 测试直接调用受保护生命周期，绕过真实 measure/layout 顺序。
- 断言私有字段而不是公开状态与最终尺寸。
- 使用 `returnDefaultValues` 掩盖 “Method ... not mocked” 而继续信任结果。
- 多 SDK/设备矩阵没有明确风险目标，只增加 CI 时间。

## 实践检查清单

- [ ] 纯几何/状态算法已从 View 提取并用 JVM 测试覆盖。
- [ ] EXACTLY、AT_MOST、UNSPECIFIED 及极小/极大边界均有契约测试。
- [ ] padding、minimum、RTL、fontScale 和资源 qualifier 有风险覆盖。
- [ ] Robolectric 已启用资源，SDK 与依赖版本固定。
- [ ] 平台相关行为有真实仪器测试，且 View 操作在主线程。
- [ ] 断言最终行为，不复制生产算法、不依赖私有实现。
- [ ] 场景、动画和监听器在测试后正确释放。

## 小结

测量测试的价值是把父约束、内容建议和 View 输出之间的契约固定下来。纯函数负责组合爆炸，Robolectric 负责快速 Android 集成，仪器测试负责真实平台风险。

## 延伸阅读

- [Android Developers：Robolectric 测试策略](https://developer.android.com/training/testing/local-tests/robolectric)
- [Android Developers：构建本地单元测试](https://developer.android.com/training/testing/local-tests)
- [Android Developers：构建仪器测试](https://developer.android.com/training/testing/instrumented-tests)
- [Android `View.MeasureSpec` API](https://developer.android.com/reference/android/view/View.MeasureSpec)
- [Android Developers：支持不同屏幕的测试工具](https://developer.android.com/training/testing/different-screens/tools)
