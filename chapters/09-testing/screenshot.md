# 截图测试与视觉回归

## 学习目标

- 明确截图测试能发现什么、不能证明什么。
- 建立可重复的渲染环境、基线审核与差异诊断流程。
- 设计覆盖主题、字体、RTL、状态和设备矩阵的最小高价值用例。

## 1. 截图测试的位置

```text
状态/布局断言：为什么错、逻辑是否对
            +
截图差异：最终像素是否意外改变
            +
无障碍/人工：语义和体验是否可用
```

截图擅长发现颜色、间距、裁剪、层级与字体回归；它不能证明点击有效、语义正确或业务结果正确。截图失败是“需要审查的视觉差异”，不是自动等同缺陷。

## 2. 可重复性先于工具

基线与实际图必须固定：

- API level、设备尺寸、密度与色彩空间。
- locale、RTL、fontScale、显示缩放、时区（若文案含日期）。
- light/dark、动态色开关、系统栏和 edge-to-edge 策略。
- 字体文件、字体 fallback 与 emoji 版本。
- 动画时钟、随机种子、网络数据、当前时间与光标。
- 截图裁剪范围与背景透明度。

```text
固定输入/配置
     │
measure -> layout -> draw -> capture
     │                      │
     └──── metadata ────────┤
                            v
baseline ── pixel/perceptual diff ──> actual + diff + report
```

> **性能提示**：PR 运行小而稳定的组件矩阵；完整设备/语言矩阵放夜间任务，避免反馈时间失控。

## 3. 组件级 Robolectric 示例

下面示例演示确定性的 measure/layout/draw 与像素探针。真实项目应使用已选定且锁版的截图库生成 PNG、比较基线并输出 diff；不要手写一个没有报告能力的比较器。

```kotlin
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w360dp-h640dp-420dpi-notnight")
class GaugeScreenshotPreparationTest {
    @Test fun determinate75_rendersAtFixedSize() {
        val view = GaugeView(ApplicationProvider.getApplicationContext()).apply {
            progress = 75
            isEnabled = true
        }
        val width = 300
        val height = 120
        view.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY),
        )
        view.layout(0, 0, width, height)

        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        view.draw(Canvas(bitmap))

        assertEquals(width, bitmap.width)
        assertEquals(height, bitmap.height)
        assertTrue("render must not be fully transparent", containsOpaquePixel(bitmap))
        // 交给项目锁定的 screenshot rule：assertAgainstGolden(bitmap, "gauge_75_light")
    }

    private fun containsOpaquePixel(bitmap: Bitmap): Boolean {
        for (y in 0 until bitmap.height step 4) {
            for (x in 0 until bitmap.width step 4) {
                if (android.graphics.Color.alpha(bitmap.getPixel(x, y)) > 0) return true
            }
        }
        return false
    }
}
```

`qualifiers` 示例应按项目 Robolectric 版本验证。涉及真实字体栅格、硬件阴影或 OEM 差异的高风险控件，再补仪器截图。

### Robolectric 原生图形模式

Robolectric 4.10 起提供 `@GraphicsMode(GraphicsMode.Mode.NATIVE)`。默认 LEGACY 模式下，graphics 相关类由桩件或低保真替代实现，像素内容常为空或不可靠；NATIVE 模式加载真实的 Android 原生图形栈（Skia 栅格化），绘制结果更接近真机，可直接从 Bitmap 读取像素做断言。

何时需要 NATIVE：

- 测试断言真实像素：截取 View/Bitmap 后检查颜色、透明度或不透明像素占比。
- 依赖真实字体栅格、Shader、Path、硬件阴影等 LEGACY 表现不可靠的绘制路径。
- 与 Roborazzi 等基于 Robolectric 的 JVM 截图库配合做基线比较。

```kotlin
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [33], qualifiers = "w360dp-h640dp-420dpi-notnight")
class GaugeNativeScreenshotTest {

    @Test fun determinate75_rendersPixels() {
        val view = GaugeView(ApplicationProvider.getApplicationContext()).apply {
            progress = 75
        }
        val width = 300
        val height = 120
        view.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY),
        )
        view.layout(0, 0, width, height)

        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        view.draw(Canvas(bitmap))
        // NATIVE 下栅格化真实发生，像素断言才有意义；LEGACY 下可能全部透明。
        assertTrue("NATIVE 渲染不应全透明", containsOpaquePixel(bitmap))
    }

    private fun containsOpaquePixel(bitmap: Bitmap): Boolean {
        for (y in 0 until bitmap.height step 4) {
            for (x in 0 until bitmap.width step 4) {
                if (android.graphics.Color.alpha(bitmap.getPixel(x, y)) > 0) return true
            }
        }
        return false
    }
}
```

> **注意**：`@GraphicsMode` 与 NATIVE 模式自 Robolectric 4.10 引入，默认仍为 LEGACY，需显式声明（后续版本如有默认值变化，以官方发布说明为准）。平台支持：4.10–4.11 仅 Linux/macOS（Windows 可走 WSL 2），Windows x86_64 自 4.12 起支持；NATIVE 比 LEGACY 慢，只对确实需要真实栅格化的用例开启。

## 4. 仪器截图与工件

```kotlin
import android.graphics.Bitmap
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import java.io.FileOutputStream
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class GaugeDeviceScreenshotTest {
    @Test fun darkLargeFont_captureForGoldenComparison() {
        ActivityScenario.launch(GaugeHostActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val view = activity.findViewById<GaugeView>(R.id.gauge)
                val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                view.draw(android.graphics.Canvas(bitmap))
                // 保存到测试工件目录，再由锁定的 golden 工具比较。
                val file = File(activity.cacheDir, "gauge_dark_large_font_actual.png")
                FileOutputStream(file).use { output ->
                    check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output))
                }
                check(file.length() > 0L)
            }
        }
    }
}
```

设备测试必须等待布局与字体加载完成；若使用 PixelCopy 捕获 Window，要等待回调而非 sleep。工件至少包含 actual、expected、diff、配置 JSON 和测试名。

## 5. 比较策略

| 策略 | 优点 | 风险 | 适用 |
|---|---|---|---|
| 逐像素完全一致 | 最严格、易解释 | 字体/抗锯齿易噪声 | 锁定渲染栈的组件 |
| 像素阈值 | 容忍微小差异 | 阈值可能吞缺陷 | 少量平台噪声 |
| 感知差异 | 接近人眼 | 算法和阈值更复杂 | 跨渲染环境审核 |
| 区域遮罩 | 排除时间/光标 | 容易遮住真实问题 | 极少数不可控区域 |

阈值必须用真实噪声样本校准并记录原因。禁止因为 CI 红就不断调大阈值。若基线变更，PR 必须展示 before/after/diff，由非作者或指定设计责任人审核。

## 6. 最小高价值矩阵

```text
状态：default / pressed / disabled / error / loading
主题：light / dark / high contrast（产品支持时）
文本：短 / 长 / 200% fontScale / 伪本地化
方向：LTR / RTL
尺寸：最小支持宽度 / 常规 / 大屏关键断点
```

不做全排列。用风险配对：长文本 + 小宽度、RTL + 图标方向、dark + disabled、高 fontScale + error。每个基线名编码组件、状态和配置，例如 `gauge_error_rtl_dark_360x640_api33.png`。

## 7. 基线生命周期

1. 新用例先在固定环境生成候选基线。
2. 人工确认设计意图后提交基线和元数据。
3. CI 只比较，不自动更新。
4. 差异失败上传 actual/expected/diff。
5. 有意变更单独执行 update 任务，评审后合并。
6. 删除组件时同步删除测试和孤儿基线。

> **注意**：基线更新是代码变更，不是“接受失败”按钮；禁止在普通测试任务中自动覆写 expected。

## 常见陷阱

- 开发机与 CI 使用不同 JDK、API、字体或 locale。
- 动画、当前时间、网络图片和随机数据未冻结。
- 只截正常态，遗漏 disabled/error/pressed。
- 用宽松阈值掩盖全局 1 px 偏移或颜色错误。
- 失败只输出“相似度 98%”，没有三联图和配置。
- 每个设备做全排列，基线数量失控且无人审阅。
- 截图通过就省略语义、交互和 TalkBack 测试。

## 实践检查清单

- [ ] 渲染环境、字体、locale、主题、时间和随机性均固定。
- [ ] 组件先完成确定性 measure/layout，再截图。
- [ ] PR 矩阵基于风险，不做无意义全排列。
- [ ] actual、expected、diff 和环境元数据作为 CI 工件保存。
- [ ] 阈值有样本依据；遮罩区域最小且有说明。
- [ ] CI 比较任务不可自动更新基线。
- [ ] 有意变化需人工审查 before/after/diff。
- [ ] 截图测试与状态、交互、无障碍测试并行存在。

## 小结

截图测试的生产价值来自“固定环境 + 风险矩阵 + 可诊断差异 + 受控基线”，而不是 PNG 数量。先消除非确定性，再讨论阈值和覆盖率。

## 延伸阅读

- [Android Developers：截图测试](https://developer.android.com/training/testing/ui-tests/screenshot)
- [Android Developers：测试不同屏幕尺寸的工具](https://developer.android.com/training/testing/different-screens/tools)
- [Android Developers：Gradle Managed Devices](https://developer.android.com/studio/test/gradle-managed-devices)
- [Android Developers：Robolectric 策略](https://developer.android.com/training/testing/local-tests/robolectric)
- [Android `PixelCopy` API](https://developer.android.com/reference/android/view/PixelCopy)
