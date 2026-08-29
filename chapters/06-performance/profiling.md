# Perfetto、HWUI 与卡顿定位

## 学习目标

- 按“复现—量化—trace—归因—改动—复测”的顺序排查卡顿。
- 用 Perfetto FrameTimeline 区分 UI、RenderThread、GPU 与系统合成问题。
- 正确理解 HWUI/gfxinfo、JankStats 和 Macrobenchmark 各自回答的问题。
- 输出能在 CI 与真机上复验的性能证据包。

## 1. 工具不是替代关系

```text
线上/人工发现卡顿
        |
        +--> JankStats：哪段页面状态发生 jank？
        |
        +--> Macrobenchmark：固定场景的分布、回归门槛、trace
        |
        +--> Perfetto：失败帧跨线程/进程的根因时间线
        |
        +--> HWUI/gfxinfo：快速帧统计与渲染阶段线索
        |
        +--> Memory/CPU profiler：分配栈、方法/线程热点
        v
形成假设 -> 单变量修改 -> 同条件 Macrobenchmark + trace 复验
```

- **JankStats** 给帧附加应用状态，适合回答“何时、在哪个 UI 状态卡”。它不是 GPU 根因分析器。
- **Macrobenchmark** 自动重复真实应用场景，输出指标和 trace，适合基线与回归。
- **Perfetto** 展开跨进程时间线，适合对具体失败帧归因。
- **HWUI/gfxinfo** 适合快速观察，但单独不足以证明原因。

## 2. 第一步：写下可复现协议

在打开 profiler 前先固定变量：

```text
设备：Pixel ... / Android ... / display mode ... Hz
构建：release + profileable，commit ...
状态：温控正常、固定亮度/网络/数据集、无调试器
场景：启动 -> 进入图表 -> 预热 2 次 -> 双指缩放 10 s
迭代：例如 10 次（按噪声调整）
指标：jank rate、frameDurationCpuMs p50/p95/p99、目标 jank type
正确性：关键帧截图、最终 viewport/data state
```

> **注意**：不要预设统一 16.67 ms 门槛。Perfetto 应读取该帧的 expected timeline；
> API 31+ 的 Macrobenchmark `frameOverrunMs` 可反映相对 deadline 的超期。JankStats 的
> `isJank` 来自库的帧时长启发式阈值（可由 `jankHeuristicMultiplier` 调整），不能冒充
> FrameTimeline 的实际 deadline；记录测试显示模式，并明确指标来源。

## 3. JankStats：给失败帧补充业务上下文

依赖版本应由项目的 version catalog 统一管理：

```kotlin
implementation("androidx.metrics:metrics-performance:<version>")
```

在 Activity 中启动跟踪，并只记录低基数、可解释的状态：

```kotlin
import androidx.metrics.performance.JankStats
import androidx.metrics.performance.PerformanceMetricsState

class ChartActivity : AppCompatActivity() {
    private lateinit var jankStats: JankStats

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_chart)

        val metricsState =
            PerformanceMetricsState.getHolderForHierarchy(findViewById(android.R.id.content))
                .state
        metricsState?.putState("screen", "chart")
        metricsState?.putState("interaction", "idle")

        jankStats = JankStats.createAndTrack(window) { frameData ->
            if (frameData.isJank) {
                // 生产环境应采样/聚合，避免每个慢帧同步写磁盘或刷大量日志。
                enqueueJankSample(
                    durationUiNanos = frameData.frameDurationUiNanos,
                    states = frameData.states.map { "${it.key}=${it.value}" }
                )
            }
        }
    }

    fun onScaleStart() {
        PerformanceMetricsState
            .getHolderForHierarchy(findViewById(android.R.id.content))
            .state
            ?.putState("interaction", "pinch")
    }

    fun onScaleEnd() {
        PerformanceMetricsState
            .getHolderForHierarchy(findViewById(android.R.id.content))
            .state
            ?.putState("interaction", "idle")
    }

    override fun onResume() {
        super.onResume()
        jankStats.isTrackingEnabled = true
    }

    override fun onPause() {
        jankStats.isTrackingEnabled = false
        super.onPause()
    }
}
```

不要把用户 ID、随机字符串或每帧坐标作为状态键值，否则难以聚合且可能泄露隐私。
JankStats 帮你缩小到 `screen=chart, interaction=pinch`，随后仍需 Perfetto 找根因。

## 4. Macrobenchmark：把复现变成可回归测试

在独立 benchmark 模块中测目标应用。示例使用确定性滑动；真实项目应通过 resource id 找到
目标区域并验证手势确实发生：

```kotlin
import androidx.benchmark.macro.FrameTimingMetric
import androidx.benchmark.macro.MacrobenchmarkRule
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.measureRepeated
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.LargeTest
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@LargeTest
@RunWith(AndroidJUnit4::class)
class ChartFrameBenchmark {
    @get:Rule
    val rule = MacrobenchmarkRule()

    @Test
    fun panAndZoom() = rule.measureRepeated(
        packageName = "com.example.app",
        metrics = listOf(FrameTimingMetric()),
        iterations = 10,
        startupMode = StartupMode.WARM,
        setupBlock = {
            pressHome()
            startActivityAndWait()
            device.waitForIdle()
        }
    ) {
        val cx = device.displayWidth / 2
        val y = device.displayHeight * 2 / 3
        device.swipe(cx + 300, y, cx - 300, y, 24)
        device.waitForIdle()
    }
}
```

```bash
# 模块名按项目调整；保存控制台结果与 additional output 中的 JSON/trace。
./gradlew :benchmark:connectedCheck
```

每次迭代通常会生成可打开的 trace。比较前后时保持编译模式、启动模式、设备、数据与手势一致，
并保留原始 JSON，而非只抄控制台的一行。

## 5. Perfetto：从失败帧沿时间线反查

可以使用 Android Studio System Trace，也可通过 adb 快速采集。不同系统版本支持的数据源不同，
先运行 `adb shell perfetto --query`，正式自动化建议使用版本控制的 protobuf text config。

```bash
adb shell perfetto --query

# 简短开发采集示例；若设备不支持某 category，按 --query 结果调整。
adb shell perfetto \
  -o /data/misc/perfetto-traces/chart.perfetto-trace \
  -t 10s sched freq idle am wm gfx view binder_driver

adb pull /data/misc/perfetto-traces/chart.perfetto-trace .
```

打开 trace 后按以下顺序，避免在海量 slice 中漫游：

```text
1. FrameTimeline: 选一个实际 jank frame
             |
             v
2. 比较 expected timeline 与 actual timeline，记录 jank type
             |
             v
3. 沿 frame 关联到 app UI / RenderThread / GPU / SurfaceFlinger
             |
             v
4. 找 deadline 前最长的关键路径，而不是全局最长函数
             |
             v
5. 对齐 binder、I/O、GC、调度等待、频率/温控事件
             |
             v
6. 用自定义 Trace section 映射到控件阶段
             |
             v
7. 建立可证伪假设，做一次单变量 A/B
```

步骤 1、2 里的 "expected timeline 与 actual timeline" 具体读什么？Perfetto 的
FrameTimeline 轨道同时给出两条时间线（该数据源仅在 Android 11 / API 30+ 系统可用，
以 `perfetto --query` 确认设备是否支持）：

```text
expected（期望）轨道，按 vsync 切分帧槽：
vsync      v0     v1     v2     v3     v4
帧槽     ┌──A────┬──B────┬──C────┬──D────┬──E────┐
         │  每个帧槽 = 一个刷新周期，期望帧在下一 vsync 前完成 │
         └───────┴───────┴───────┴───────┴───────┘

actual（实际）轨道，记录真实 CPU/GPU 完成情况：
帧 A 正常：  ┌────────┐
            │CPU   GPU│ 完成 < v1        -> 按时显示
帧 B 临界：    ┌──────────────────┐
              │CPU            GPU│ 完成 ≈ v2     -> 勉强赶上
帧 C 掉帧：      ┌──────────────────────────────────────┐
                │CPU                    GPU            │ 完成 > v3
                ▼                                      ▼
               v2、v3 两个帧槽无对应输出 -> 屏幕沿用旧帧 -> 卡顿
```

读图定位卡顿阶段的顺序：

1. 在 actual 轨道找“完成时间越过本帧 expected deadline”的帧，即完成晚于下一 vsync 的帧。
2. 看该帧里 CPU 段（frameStartTime 到提交 display list）与 RenderThread/GPU 段（到 GPU
   completion）谁更长：前者指向 UI 线程，后者指向渲染/GPU（对照下方诊断表）。
3. 掉帧区间 = 有 expected 帧槽但 actual 无对应输出的间隙；其跨度说明卡顿持续了几个刷新
   周期，而不是只看单帧耗时。帧槽与实际帧通过 vsync id 关联，上图仅为示意。

### 5.1 诊断表：常见轨道解释

| Trace 证据 | 可能根因 | 验证动作 | 不能直接推出 |
|---|---|---|---|
| UI `Choreographer#doFrame` 长 | input/animation/traversal/业务 | 展开 slice 与调用栈，自定义 section | “GPU 没问题” |
| `performTraversals` 中 layout 长 | `requestLayout` 风暴/复杂层级 | 计数与合并状态更新 A/B | 一定是自定义 View 的 `onMeasure` |
| `Chart.drawSeries` 长 | 可见点过多、Path 重建 | 缓存/裁剪后 section 是否下降 | 改动一定改善呈现期限 |
| RenderThread `DrawFrame` 长 | HWUI 同步/绘制/层 | 去掉效果或 layer 做 A/B | UI 线程优化会有效 |
| GPU completion 超期 | fill-rate/shader/离屏层 | GPU counter、缩小 layer bounds | 仅凭 CPU profiler 可归因 |
| runnable 但久未调度 | CPU 竞争/调度 | sched、其他进程、频率轨道 | 代码本身执行慢 |
| GC 与失败帧重叠 | 热路径分配候选 | allocation 栈 + 去分配 A/B | 任意 GC 都是根因 |
| SurfaceFlinger 超期 | 合成/系统层/负载 | clean device、layer 与 SF 轨道 | 应用代码一定有错 |

## 6. HWUI 与 gfxinfo：快速筛查，不做最终归因

```bash
adb shell dumpsys gfxinfo com.example.app reset
# 执行固定场景
adb shell dumpsys gfxinfo com.example.app framestats > framestats.txt
adb shell dumpsys meminfo com.example.app > meminfo.txt
```

开发者选项的 **Profile HWUI rendering** 可用柱状图观察连续慢帧，**Debug GPU overdraw** 可找重复
覆盖候选。它们适合回答“在哪段交互值得录 trace”，不适合回答跨线程关键路径。

某些设备/版本可用系统属性开启可视化：

```bash
adb shell setprop debug.hwui.profile visual_bars
# 测试结束后恢复：
adb shell setprop debug.hwui.profile false
```

系统属性行为可能因版本/OEM 不同；自动化验收优先使用 Macrobenchmark 与 Perfetto 数据。

## 7. 从证据到改动：三个完整例子

### 7.1 `onDraw` 分配导致周期性 GC

```text
JankStats: pinch 状态卡顿集中
-> FrameTimeline: UI deadline miss
-> UI slice: Chart.drawSeries + GC 重叠
-> Allocation recording: Path/ArrayList 来自 onDraw
-> 改动: 预分配 Path/缓冲，数据变化时重建
-> 复测: 目标分配消失、GC 不再重叠、jank rate/p95 改善
```

### 7.2 全屏 `saveLayer` 导致 GPU 超期

```text
Macrobenchmark: CPU p95 无明显异常，但 jank 仍高
-> Perfetto: GPU completion 晚，RenderThread 有离屏层工作
-> 代码: saveLayer(null, paint)
-> 改动: 使用包含效果边缘的紧 bounds，或移除不必要隔离
-> 复测: GPU deadline miss 下降 + 截图 blend 结果一致
```

### 7.3 `requestLayout()` 被当成刷新

```text
FrameTimeline: UI thread miss
-> performTraversals/layout 每帧出现
-> setter: 颜色动画每帧 requestLayout()
-> 改动: 仅 invalidate()；尺寸相关属性才 requestLayout()
-> 复测: layout slice 消失 + 最终尺寸/视觉测试通过
```

## 8. 优化前后验收模板

```markdown
场景：____________________  commit before/after：________ / ________
设备/API：________________  显示模式：________ Hz（是否切换：是/否）
构建/编译模式：__________  迭代数：before ____ / after ____
温控与后台条件：________________________________________

主指标：
- JankStats jank frame rate：before ____ -> after ____；门槛 ____
- Macrobenchmark frameOverrunMs p50/p90/p95/p99（API 31+）：____ -> ____
- frameDurationCpuMs p50/p95/p99：____ -> ____；门槛 ____
- 目标 FrameTimeline jank type/count：____ -> ____

守护指标：
- 内存峰值：____ -> ____；上限 ____
- 启动/输入响应：____ -> ____；不得劣化 ____
- 截图/状态/无障碍回归：通过 / 失败

证据：before trace ____；after trace ____；benchmark JSON ____
结论：通过 / 不通过 / 样本不足（原因：____）
```

推荐把明确的回归阈值放入 CI，但先在实验室设备建立噪声范围。虚拟设备适合部分稳定性检查，
最终渲染性能门槛应在受控实体设备上验证。

## 9. 常见陷阱

- 先改代码后找证据，无法判断哪项改动有效。
- 只选择最差或最好一次运行，忽略完整分布。
- profiler 开销、Debug 构建或日志 I/O 改变了被测对象。
- 只看 UI thread，却忽略 RenderThread/GPU/SurfaceFlinger。
- 把 JankStats 的 UI duration 当成完整 GPU 呈现时间。
- Macrobenchmark 前后使用不同启动/编译模式或刷新率。
- trace 名称高基数过高，或在每个数据点创建 section。
- 优化了帧数据，却没有验证图像、触摸、状态与无障碍回归。

## 10. 实践检查清单

- [ ] 复现协议和验收门槛在采集前写好。
- [ ] JankStats 状态可聚合、无敏感信息、无热路径同步 I/O。
- [ ] Macrobenchmark 固定设备、构建、编译模式、数据和手势。
- [ ] Perfetto 从 FrameTimeline 失败帧沿关键路径归因。
- [ ] 根因假设可证伪，且一次只改变一个主要变量。
- [ ] 保存 before/after trace、JSON、系统条件与 commit。
- [ ] 性能指标和正确性守护指标全部通过。

## 小结

可靠的卡顿排查不是“打开一个 profiler 看红色”，而是把场景、帧、线程、代码和回归指标串成
证据链。JankStats 提供业务上下文，Macrobenchmark 提供重复与统计，Perfetto 提供跨流水线
根因，HWUI 提供快速筛查。最终结论必须能由另一台受控设备、同一脚本和原始证据复验。

## 官方资料

- [JankStats](https://developer.android.com/topic/performance/jankstats)
- [Write a Macrobenchmark](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview)
- [Macrobenchmark metrics](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-metrics)
- [Record a system trace](https://developer.android.com/topic/performance/tracing)
- [Perfetto Android tracing](https://perfetto.dev/docs/getting-started/system-tracing)
- [Perfetto FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline)
- [Profile GPU rendering](https://developer.android.com/topic/performance/rendering/profile-gpu)
