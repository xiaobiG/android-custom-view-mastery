# 调试清单与故障模式

## 学习目标

- 用“先分类、再证伪”的故障树定位自定义 View 问题。
- 为测量、绘制、输入、状态、性能和无障碍建立证据链。
- 把线上缺陷转化为最小复现与回归测试，而非永久日志。

## 1. 先保存现场

不要先改代码。记录设备/API、主题、locale、fontScale、RTL、窗口尺寸、输入类型、复现率和最后一个正常版本；保留截图/录屏、Layout Inspector、Perfetto trace 和相关日志。

```text
现象
├─ 看不见/裁剪 ─> measure? layout? clip? alpha? z-order?
├─ 位置错误     ─> 坐标系? padding? RTL? matrix? scroll?
├─ 不响应       ─> hit test? dispatch? intercept? enabled? performClick?
├─ 状态错乱     ─> 单一真相源? save/restore? 重入? 生命周期?
├─ 卡顿/闪烁    ─> 每帧分配? invalidate 范围? layout 抖动? GPU?
└─ TalkBack 错  ─> 节点? 边界? 动作? 事件? 焦点?
```

## 2. 系统化调试循环

```text
复现 -> 分类 -> 单一假设 -> 增加最小观测 -> 证伪/确认
  ^                                              |
  └──── 回归测试 <- 最小修复 <- 根因解释 <──────┘
```

一次只改变一个变量。日志要带帧/手势 ID、View 尺寸和状态，不要在 `onDraw()` 无条件刷屏。修复完成后删除临时观测，保留可运行测试和必要的结构化诊断。

## 3. 分支一：测量与布局

检查顺序：

1. 父传入的 width/height `MeasureSpec` mode/size。
2. desired size 是否含 padding、minimum 和内容。
3. `setMeasuredDimension()` 输出及 too-small state。
4. `layout()` 边界、父裁剪、translation 与 matrix。
5. 是否在 layout 中再次 `requestLayout()` 形成抖动。

临时结构化记录：

```kotlin
private fun specString(spec: Int): String {
    val mode = when (View.MeasureSpec.getMode(spec)) {
        View.MeasureSpec.EXACTLY -> "EXACTLY"
        View.MeasureSpec.AT_MOST -> "AT_MOST"
        else -> "UNSPECIFIED"
    }
    return "$mode(${View.MeasureSpec.getSize(spec)})"
}

override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
    super.onMeasure(widthMeasureSpec, heightMeasureSpec)
    android.util.Log.d(
        "GaugeMeasure",
        "in=${specString(widthMeasureSpec)}x${specString(heightMeasureSpec)} " +
            "out=${measuredWidth}x${measuredHeight} padding=$paddingLeft,$paddingTop,$paddingRight,$paddingBottom",
    )
}
```

此日志仅用于本地诊断，根因确认后移除或受 debug flag 控制。

## 4. 分支二：绘制与坐标

逐层排除：背景 → 内容 → children → foreground；保存/恢复 Canvas 状态必须成对。将触摸点、内容 bounds、clip bounds 用 debug overlay 画出来，比猜 matrix 更快。

```text
屏幕坐标
  - view.getLocationOnScreen()
宿主局部坐标
  - padding / scroll
内容坐标
  - inverse(matrix)
模型坐标
```

矩阵调试必须验证逆变换是否成功；不可逆矩阵应拒绝手势而不是使用旧坐标。检查 Path/Rect 是否被跨帧错误复用，Paint alpha/colorFilter 是否恢复。

## 5. 分支三：触摸与点击

用同一 gesture ID 记录 `dispatchTouchEvent`、`onInterceptTouchEvent`、`onTouchEvent` 的 action、pointerId、坐标和返回值：

- DOWN 必须建立手势所有权；中途开始返回 true 太晚。
- 父拦截后子会收到 CANCEL，必须清理 pressed/velocity/drag 状态。
- 使用 `actionIndex` 读取 pointer ID，后续按 ID 查 index。
- 点击识别最终调用 `performClick()`。
- 嵌套滚动先消费协议，再修改自身偏移。

```kotlin
import android.view.MotionEvent
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class DragStateRegressionTest {
    @Test fun cancel_clearsPressedAndDragging() {
        val view = DraggableGauge(ApplicationProvider.getApplicationContext())
        view.layout(0, 0, 300, 100)
        val down = MotionEvent.obtain(0, 0, MotionEvent.ACTION_DOWN, 30f, 50f, 0)
        val cancel = MotionEvent.obtain(0, 16, MotionEvent.ACTION_CANCEL, 30f, 50f, 0)
        try {
            view.dispatchTouchEvent(down)
            view.dispatchTouchEvent(cancel)
            assertEquals(false, view.isPressed)
            assertEquals(false, view.isDraggingForTest)
        } finally {
            down.recycle()
            cancel.recycle()
        }
    }
}
```

测试钩子应是只读且限制在测试可见范围，或直接断言公开视觉/业务结果。

## 6. 分支四：状态与生命周期

建立唯一真相源：输入属性 → 派生几何 → 绘制。若 setter、动画和恢复流程都能直接写多个缓存字段，状态迟早分叉。

检查：

- `onSaveInstanceState()` 是否包含用户可见状态并携带 super state。
- restore 是否仅恢复，不重复触发 analytics/业务回调。
- animator/callback/listener 在 detach 时取消，在 attach 时按需恢复。
- 异步回调是否写入已经 detach 或复用后的 View。
- 配置变化后缓存 key 是否包含 density/fontScale/layoutDirection/theme。

## 7. 分支五：性能

先量化再优化：Perfetto 定位慢帧所在阶段；Layout Inspector 看层级/重组；GPU/渲染工具看过度绘制。常见根因：

- `onDraw()` 每帧创建 Bitmap、Path、Shader 或字符串。
- 动画每帧 `requestLayout()`，本可只 `invalidate()`。
- `invalidate()` 覆盖整个超大 View，而变化区域很小。
- 软件层/离屏图层被当成万能修复。
- 主线程执行 I/O、图片解码或复杂数据降采样。

> **性能提示**：缓存必须有正确失效键；错误缓存比重算更危险。

## 8. 分支六：无障碍故障树

```text
TalkBack 找不到
├─ importantForAccessibility?
├─ helper delegate 安装?
├─ dispatchHoverEvent 转发?
└─ 虚拟节点是否 visible + 非空 bounds?

找得到但读错
├─ name/role/state 是否完整且重复?
└─ 节点更新后是否 invalidate?

读得到但不能操作
├─ clickable/action 是否声明?
├─ performAccessibilityAction 是否返回 true?
└─ 是否复用 performClick/业务入口?

焦点跳走
├─ virtual ID 是否稳定?
├─ 刷新是否重建成另一对象?
└─ 是否有代码强抢焦点?
```

在 Espresso 套件全局启用 `AccessibilityChecks`，再用 TalkBack 真机复现；节点 dump 只能说明结构，不能替代任务测试。

## 9. 从缺陷到回归测试

先写能稳定复现根因的最小测试并确认失败，再做最小修复，最后运行同层和全套测试。例如：

```kotlin
@Test fun atMostWidth_neverExceedsParent_afterLongLabel() {
    val view = LabelGauge(ApplicationProvider.getApplicationContext()).apply {
        label = "A very long diagnostic label"
    }
    val limit = 120
    view.measure(
        View.MeasureSpec.makeMeasureSpec(limit, View.MeasureSpec.AT_MOST),
        View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED),
    )
    assertTrue(view.measuredWidth <= limit)
}
```

测试名应描述已破坏的契约，不写工单号替代行为说明；工单链接可放注释。

## 10. 生产排障清单

| 症状 | 第一证据 | 常用工具 | 回归层 |
|---|---|---|---|
| 尺寸/裁剪 | specs + measured/layout bounds | Layout Inspector | Robolectric/仪器 |
| 绘制错误 | actual/expected/diff + draw overlay | 截图测试、GPU 工具 | screenshot |
| 手势丢失 | 分发链 + pointer ID + CANCEL | 结构化事件日志 | Robolectric/Espresso |
| 慢帧 | frame timeline/trace | Perfetto | benchmark/宏基准 |
| 语义错误 | node tree + TalkBack 录屏 | Accessibility Scanner/Checks | 仪器 + 人工 |
| 恢复错误 | saved state + 生命周期序列 | `dumpsys`/日志 | 仪器 |

## 常见陷阱

- 看到现象立即改 Paint/尺寸常量，没有根因假设。
- 一次提交混入重构、优化和修复，无法确认真正原因。
- 用 sleep、重试或扩大截图阈值“修复”不稳定测试。
- 只在开发者设备复现，不记录配置矩阵。
- 保留高频日志进入 release，泄露状态并制造卡顿。
- 修复触摸路径却没有检查键盘/无障碍是否共享入口。
- 只修截图，不增加能解释根因的契约测试。

## 实践检查清单

- [ ] 已保存环境、最小复现、最后正常版本和原始证据。
- [ ] 已按测量/绘制/输入/状态/性能/无障碍分类。
- [ ] 每轮只有一个可证伪假设和一个变量变化。
- [ ] 根因能解释全部现象，而非只让当前设备看起来正常。
- [ ] 修复前有稳定失败的最小回归测试。
- [ ] 修复后运行同层、相关集成与全套测试。
- [ ] 临时日志/overlay 已移除或仅限 debug，资源已释放。
- [ ] 触摸修复同步检查键盘、TalkBack 和虚拟节点路径。

## 小结

高质量调试不是积累技巧列表，而是建立证据链：保存现场、故障树分类、单假设证伪、最小修复、回归测试。最终产物应是被固定的契约，而不是无法复述的“调好了”。

## 延伸阅读

- [Android Developers：使用 Layout Inspector 调试布局](https://developer.android.com/studio/debug/layout-inspector)
- [Android Developers：使用 Perfetto 记录系统跟踪](https://developer.android.com/topic/performance/tracing)
- [Android Developers：分析 GPU 渲染](https://developer.android.com/topic/performance/rendering/inspect-gpu-rendering)
- [Android Developers：调试应用](https://developer.android.com/studio/debug)
- [Android Developers：测试无障碍](https://developer.android.com/guide/topics/ui/accessibility/testing)
- [Android Developers：输入事件概览](https://developer.android.com/develop/ui/views/touch-and-input/input-events)
