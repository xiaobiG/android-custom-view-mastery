# 每帧预算与渲染流水线

## 学习目标

- 用刷新周期而不是固定的“16.67 ms”理解帧预算。
- 区分应用 UI 线程、RenderThread、GPU 与 SurfaceFlinger 的耗时。
- 建立“固定场景—采集基线—修改—复测—判定”的优化闭环。
- 能为不同刷新率、不同设备和不同热状态制定可验证的验收标准。

## 1. 预算来自显示节奏，不是常量

显示器刷新率为 `R` Hz 时，一个刷新周期的理论长度是：

```text
periodNs = 1_000_000_000 / R

 60 Hz -> 约 16.67 ms
 90 Hz -> 约 11.11 ms
120 Hz -> 约  8.33 ms
```

这只是显示节奏，不等于应用可独占的 CPU 时间。输入到达、帧回调、UI 遍历、
RenderThread、GPU、BufferQueue 和 SurfaceFlinger 可以流水并行；调度等待、前序帧、
合成与安全余量都会占用截止时间。设备还可能按内容、功耗和温度动态切换刷新率。
因此：

> **注意**：不要把“每帧必须低于 16.67 ms”写成跨设备结论。应从 trace 中读取
> 该帧的预期时间线（expected timeline）与实际时间线，并按测试时的显示模式验收。

```text
触摸/定时器
    |
    v
VSync/App deadline
    |
    +--> UI thread: input -> animation -> traversal -> record display list
    |                                      |
    |                                      v
    |                              RenderThread: prepare/submit
    |                                      |
    |                                      v
    |                                     GPU
    |                                      |
    +---------------- BufferQueue ---------+
                                           v
                              SurfaceFlinger composition
                                           |
                                           v
                                      display scanout

一帧超时可能来自任一段；只看 onDraw() 用时不能完成归因。
```

### 1.1 “慢帧”与“卡顿帧”

某段代码耗时增长是局部事实；用户是否看到卡顿还取决于它是否让帧错过呈现期限。
Android 的 FrameTimeline 会为帧标出 expected/actual timeline，并给出 jank 类型。分析时
同时回答三个问题：

1. 哪个真实用户场景触发问题？
2. 是 UI 线程、RenderThread、GPU 还是系统合成错过期限？
3. 失败帧在分位数和卡顿率上占多少，而不是“偶尔看到一根柱子”？

## 2. 先记录测试条件

刷新率、温控、后台负载和构建类型不一致时，前后数字不可比。至少记录：

```bash
adb shell dumpsys display
adb shell dumpsys SurfaceFlinger --display-id
adb shell dumpsys thermalservice
adb shell dumpsys battery
adb shell getprop ro.build.version.sdk
```

建议使用同一台实体设备、release/profileable 构建、固定手势脚本、固定数据集与屏幕亮度。
先预热场景，再采集多次；不要用一次 Debug 构建的肉眼感受下结论。

### 2.1 在运行时观察显示模式

下面的代码只用于记录环境，不把刷新周期冒充完整的应用 deadline：

```kotlin
import android.content.Context
import android.hardware.display.DisplayManager
import android.os.Build
import android.util.Log
import android.view.Display
import android.view.WindowManager

fun logDisplayMode(context: Context) {
    val display: Display? = if (Build.VERSION.SDK_INT >= 30) {
        context.display
    } else {
        @Suppress("DEPRECATION")
        (context.getSystemService(Context.WINDOW_SERVICE) as WindowManager)
            .defaultDisplay
    }
    val mode = display?.mode ?: return
    val periodMs = 1_000f / mode.refreshRate
    Log.i(
        "FrameBudget",
        "mode=${mode.physicalWidth}x${mode.physicalHeight}" +
            " @ ${mode.refreshRate}Hz, nominalPeriod=${periodMs}ms"
    )
}
```

> **性能提示**：模式可能在测试过程中变化。长测试应把模式切换事件与 trace 时间戳一起
> 记录，或明确锁定测试条件；不能只在启动时读取一次便推断所有帧的期限。

## 3. 在自定义 View 中放置可追踪边界

系统 trace 能告诉你“哪里慢”，自定义 trace section 能把慢区间映射回业务阶段。
section 名保持稳定、数量有限，并避免把每个像素或每个数据点都包一层：

```kotlin
import android.graphics.Canvas
import android.os.Trace
import android.view.View

class TimelineChartView(context: Context) : View(context) {
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        Trace.beginSection("Chart.drawGrid")
        try {
            drawGrid(canvas)
        } finally {
            Trace.endSection()
        }

        Trace.beginSection("Chart.drawSeries")
        try {
            drawSeries(canvas)
        } finally {
            Trace.endSection()
        }
    }

    private fun drawGrid(canvas: Canvas) { /* 使用预计算几何 */ }
    private fun drawSeries(canvas: Canvas) { /* 只绘制可见数据 */ }
}
```

`Trace.beginSection()` 本身也有开销。它适合阶段级归因，不适合替代基准测试。

## 4. 诊断矩阵

| 观测 | 首先查看 | 常见原因 | 下一项验证 |
|---|---|---|---|
| UI thread 跨过 deadline | `Choreographer#doFrame`、`performTraversals`、自定义 section | 主线程 I/O、布局风暴、`onDraw` 重活 | CPU slice、调用栈、`requestLayout` 次数 |
| RenderThread 长 | `DrawFrame`、HWUI task | display list 构建/同步、昂贵效果 | 对照移除效果的 A/B trace |
| GPU completion 晚 | FrameTimeline、GPU/HWUI 轨道 | fill-rate、复杂 shader、大离屏缓冲 | GPU counters、降低分辨率/遮挡 A/B |
| SurfaceFlinger 晚而应用正常 | SurfaceFlinger、合成轨道 | 系统负载、合成、其他 layer | 干净设备复测，检查其他 layer |
| 周期性尖峰伴随 GC | ART/Heap/GC 事件 | 热路径分配、Bitmap 抖动 | allocation 录制与分配栈 |
| p50 好但 p95/p99 差 | 帧分布与失败帧 | 冷路径、偶发 I/O、缓存失效 | 单独标记首次/稳态场景 |
| 120 Hz 失败、60 Hz 正常 | expected timeline | 高刷期限更短 | 按显示模式分组，而非混算 |

## 5. 可重复的优化闭环

```text
定义场景和设备矩阵
        |
        v
采集基线 >= 多次迭代 ----> 保存 trace + 指标 JSON
        |
        v
从失败帧沿依赖链归因（不凭猜测）
        |
        v
一次只改一个主要变量
        |
        v
同条件复测 -> 分布改善且无视觉/功能回归？
        |                         |
       是                         否
        |                         |
        v                         +--> 回滚/形成新假设
记录证据、阈值、提交与设备
```

### 5.1 优化前后验收标准

阈值应由产品体验目标和基线共同确定。下面是格式示例，不是通用数字：

| 项目 | 优化前基线 | 本次门槛 | 验收方法 |
|---|---:|---:|---|
| 场景 | 1000 点折线图连续缩放 10 s | 手势/数据完全相同 | UI Automator 脚本 |
| 测试模式 | 120 Hz、release、温控正常 | 不得发生模式切换 | `dumpsys display` + trace |
| `frameOverrunMs` p95（API 31+） | 记录实测值 | 低于基线并达到预设容差 | `FrameTimingMetric` 多次迭代 |
| `frameDurationCpuMs` p95（API 31+） | 记录实测值 | 低于基线且置信区间不重叠或达到预设容差 | Macrobenchmark JSON |
| FrameTimeline missed frames | 记录类型与数量 | 目标 jank 类型显著下降 | Perfetto |
| 正确性 | 截图基线 | 关键帧无视觉差异 | 截图/像素容差测试 |

不要只报平均值。至少报告迭代数、p50/p90/p95/p99（按样本规模选择）、刷新模式和设备；
若另用 JankStats 统计卡顿帧比例，应注明其启发式判定与采样方式。小样本时保留每次原始数据。

## 6. 常见陷阱

- **把刷新周期当 CPU 独占预算**：流水线各段会并行，也会互相排队。
- **只优化 `onDraw()`**：根因可能在 input、layout、RenderThread、GPU 或合成。
- **只看平均值**：少量严重长尾正是用户感知的卡顿。
- **用 Debug 构建验收**：调试器、日志和未优化代码改变了测量对象。
- **比较不同刷新率的裸毫秒而不分组**：deadline 不同，卡顿分类不可直接混算。
- **看到相关就认定因果**：应做单变量 A/B，并在 trace 中验证目标 slice 确实缩短。

## 7. 实践检查清单

- [ ] 场景、设备、系统版本、构建类型和数据集已固定。
- [ ] 已记录测试期间的刷新模式与温控状态。
- [ ] 使用 FrameTimeline/帧指标判断是否错过该设备的 deadline。
- [ ] 已把耗时归因到 UI、RenderThread、GPU 或合成中的具体阶段。
- [ ] 前后都保留 trace、原始指标和迭代次数。
- [ ] 同时验证性能、视觉正确性、输入响应与无障碍行为。

## 小结

帧预算不是 16.67 ms 常量，而是由当时显示节奏、系统调度和渲染流水线共同约束的
期限。可靠优化从可复现用户场景开始，以 trace 定位失败帧，以分布和卡顿率验收，
并在相同条件下复测。数字只有带着设备、刷新模式和采样方法才有意义。

## 官方资料

- [Slow rendering / Android vitals](https://developer.android.com/topic/performance/vitals/render)
- [FrameTimeline](https://developer.android.com/topic/performance/vitals/render#frametimeline)
- [System tracing](https://developer.android.com/topic/performance/tracing)
- [Macrobenchmark metrics](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-metrics)
- [Perfetto：Frame timeline](https://perfetto.dev/docs/data-sources/frametimeline)
