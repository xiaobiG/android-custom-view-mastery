# Baseline Profile 与冷启动优化

> 本章定位：理解 Baseline Profile 解决"首次冷启动没有热点 profile"的问题，学会用
> Macrobenchmark 生成规则、把 profile 集成进构建，并区分不同 Android 版本与分发渠道
> 的实际生效条件。

## 学习目标

- 解释 ART 的 AOT/JIT 混合编译，以及为什么"第一次启动"性能总是最差。
- 说清 Baseline Profile、Startup Profile 与 Cloud Profile 的分工。
- 用 Macrobenchmark 的 `BaselineProfileRule` 自动生成 profile，或手工编写最小规则。
- 把 profile 与 `androidx.profileinstaller` 集成进 release 构建，并知道哪些设备/渠道会真正生效。
- 避免"profile 过大""被 Play 忽略""debug 与 release 表现不一致"等陷阱。

## 问题场景：冷启动的"性能低谷"

Android 7.0（API 24）之后默认采用 **JIT + AOT 混合编译**：应用安装时不整体编译，运行时先
解释执行，热点方法由 JIT 编译并记录到本机 profile（.prof），设备空闲且充电时由后台
`dexopt` 按 profile 做部分 AOT。这套方案节省安装时间与磁盘，但带来一个缺口：

```text
安装完成后的第一次冷启动
   │
   ▼
没有任何历史 profile 可参考
   │
   ▼
关键路径只能解释执行 + 边跑边 JIT
   │
   ▼
TTID/TTFD 最差、偶发卡顿，且用户此时印象最深
```

Baseline Profile 就是"出厂自带答案"：你在构建期就把应用的**关键路径**（启动、首屏、高频
交互）列成规则，系统在安装阶段就按规则 AOT 预编译这些类和方法，把第一次冷启动的性能
低谷填平。对自定义控件开发者来说，冷启动里最贵的是 LayoutInflater 膨胀、`onMeasure`
/`onDraw` 首次执行、资源加载与首帧合成，这些都在 profile 的覆盖范围内。

> **注意**：Baseline Profile 只优化"已列出的规则"对应的代码，不改变整体启动架构。先把
> 启动工作收敛到少量类、减少无用初始化，再上 profile，效果才可度量。

## 核心机制

### 规则从文本变成二进制

Baseline Profile 以**人类可读规则（human readable format，HRF）**表达，一行一条，例如：

```text
HSPLcom/example/app/MainActivity;->onCreate(Landroid/os/Bundle;)V
HLcom/example/app/widget/ChartView;->onDraw(Landroid/graphics/Canvas;)V
```

- `H` 表示"包含该方法的编译规则"，`S`/`P` 表示该规则属于启动 / 启动后阶段，可叠加；
- 类名使用点分隔，方法签名使用 JVM 描述符（`(...)V` 形式）；
- 该文本格式**不是稳定公开 API**，随 AGP/ART 版本可能调整，手工编写需谨慎（见常见陷阱）。

构建时 AGP 把 HRF 编译为二进制 `baseline.prof`（配 `baseline.profm` 元数据），打进
APK/AAB 的 `assets/dexopt/`。官方文档给出一个约束：**profile 编译后的体积必须小于
1.5 MB**，否则不会被打包。安装时 ART 依据二进制 profile 对命中的类/方法做 AOT 编译，
代码在第一次运行就直接以机器码执行。

### 不同 Android 版本的生效路径

Baseline Profile 不是"加上依赖就全局生效"。官方文档的编译行为表可以浓缩为：

```text
API 21–23（Android 5–6）
   安装时整体 AOT，无需 profile，基线即全量编译

API 24–27（Android 7–8.1）
   系统无法在安装时读取包内 profile
   -> 依赖 androidx.profileinstaller：首次运行时从 assets 安装
   -> ART 后续在空闲+充电时补充编译

API 28+（Android 9+，经 Google Play 分发）
   Play 在安装/更新时读取 baseline.prof，安装阶段即 AOT
   -> 之后 ART 上传本机 profile，Play 聚合为 Cloud Profile 惠及他人
```

| 阶段 | 谁在安装 profile | 首次冷启动是否立即受益 |
|---|---|---|
| API 21–23 | 无（全量 AOT） | 是，但代价是安装慢、占用大 |
| API 24–27 + Play | `ProfileInstaller`（首次运行） | 首次运行稍后 |
| API 24–27 + 非 Play | `ProfileInstaller`（首次运行） | 首次运行稍后 |
| API 28+ + Play | Play / 系统安装阶段 | 是 |
| API 28+ + 非 Play | 依赖后台 dexopt（通常次日） | 否（延迟） |

> **注意**：`androidx.profileinstaller` 不会"自动覆盖所有设备"。它在支持范围内从
> `assets` 安装二进制 profile，但真正的编译由设备上的 dexopt/Play 服务完成，且需要
> 设备空闲、充电等条件。对 Android 13+ 且经 Play 分发的应用，安装阶段已由系统处理，
> ProfileInstaller 在该场景基本是空操作。非 Play 渠道（侧载、企业分发）安装阶段不读
> profile，收益会推迟到后台 dexopt 之后，甚至被部分厂商的电池优化策略干扰。

### 与 Startup Profile、Cloud Profile 的关系

- **Startup Profile**（`startup-prof.txt`）：只有启动路径的规则，AGP 8.2+ 由 D8/R8
  用于 DEX 布局，把启动关键代码排进主 DEX，进一步加快启动。
- **Cloud Profile**：Play 聚合大量真实用户运行产生的 profile，分发到新安装/更新用户，
  是 Baseline Profile 的"补丁"；仅 API 28+ 且需要足够大的用户基数。
- Baseline Profile 通常应包含启动路径 + 少量高频交互路径，一般应小于 Cloud Profile
  事后优化的范围。

## 生成：自动采集与手工规则

### 方式一：Macrobenchmark 启动基线自动生成（推荐）

在独立 `:baseline-profile` 模块中写一个 `BaselineProfileRule` 测试，驱动真机/模拟器
走一遍关键路径（启动、进列表、滚动、返回），框架会把本次运行真正执行到的类和方法
采集为 HRF。依赖与规则类：

```kotlin
// :baseline-profile 模块的 build.gradle.kts
plugins {
    id("com.android.test")
    id("androidx.baselineprofile")
}

android {
    // 与目标 app 相同的 targetSdk 等配置
    defaultConfig {
        targetProjectPath = ":app"
    }
}

dependencies {
    implementation("androidx.benchmark:benchmark-macro-junit4:1.4.1")
    implementation("androidx.test.ext:junit:1.1.5")
    implementation("androidx.test.uiautomator:uiautomator:2.3.0")
}
```

```kotlin
// BaselineProfileGenerator.kt（:baseline-profile 模块）
import androidx.benchmark.macro.BaselineProfileRule
import androidx.benchmark.macro.junit4.Rule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BaselineProfileGenerator {

    @get:Rule
    val rule: BaselineProfileRule = Rule()

    @Test
    fun startupAndMainList() {
        rule.collect(
            packageName = "com.example.app",
            profileBlock = {
                // 启动：冷启动到首帧、完全显示
                startActivityAndWait()
                device.waitForIdle()
                // 高频路径：滚动主列表，覆盖 item 复用与首屏绘制
                val list = device.findObject(
                    By.res("com.example.app", "main_recycler")
                )
                list.fling(Direction.DOWN)
                list.fling(Direction.UP)
                pressBack()
            }
        )
    }
}
```

生成命令（AGP 8.0+ 配合 baseline profile 插件）：

```bash
./gradlew :app:generateBaselineProfile
# 或按变体：./gradlew :app:generateVariantBaselineProfile
```

生成结果会自动落到 `app/src/<variant>/generated/baselineProfiles/baseline-prof.txt`。
之后每次发布时，这条路径上的规则会被 AGP 编译进二进制 profile 并随包分发。

> **注意**：`generateBaselineProfile` 会真的在设备/模拟器上运行基准测试，需要准备好
> 目标设备与 release（可 profileable）构建，而不是直接以 debug 签名包代替。
> 官方已知问题：Firebase Test Lab（含 Gradle 托管的 Test Lab 设备）不支持生成；
> 部分 OnePlus 设备会因开发者选项里的"权限监控"导致生成失败，需先关闭。

### 方式二：手工编写规则

规则可以直接以 `src/main/baselineProfiles/baseline-prof.txt`（AGP 7.4 起为
`src/main/baseline-prof.txt`）提供，适合无法跑基准或只想补几条启动类时：

```text
HSPLcom/example/app/MainActivity;->onCreate(Landroid/os/Bundle;)V
HSPLcom/example/app/AppWidget;->inflate(Landroid/view/ViewGroup;)V
HPLcom/example/app/widget/ChartView;->onMeasure(II)V
HPLcom/example/app/widget/ChartView;->onDraw(Landroid/graphics/Canvas;)V
```

但注意：

- 手工规则只能覆盖你能预见的路径，容易漏掉框架回调链（如 `View` 的
  `dispatchDraw` 内部还调用哪些方法）；
- HRF 语法不是稳定公共 API，且与编译后的 profile 行为存在版本差异；
- 因此**优先用自动生成，再手工补几条已验证的启动类**，而不是整份手写。

## 集成到构建

官方给出配套工具链的最低推荐版本：

| 组件 | 最低版本 |
|---|---|
| Android Gradle plugin（AGP） | 8.0.0（AGP 7.4 起可消费 profile） |
| `androidx.benchmark:benchmark-macro-junit4` | 1.4.1 |
| `androidx.profileinstaller:profileinstaller` | 1.4.1 |

`:app` 模块侧配置：

```kotlin
plugins {
    id("com.android.application")
    id("androidx.baselineprofile")   // 关联 :baseline-profile 模块
}

dependencies {
    // 关键：让 API 24–27 与非 Play 渠道能在首次运行时安装 assets 中的 profile
    implementation("androidx.profileinstaller:profileinstaller:1.4.1")
    baselineProfile(project(":baseline-profile"))
}
```

- **版本边界（已与官方文档核对）**：AGP 8.0.0、`benchmark-macro-junit4` 1.4.1、
  `profileinstaller` 1.4.1 是官方文档列出的最低支持版本；发布前仍应到 AndroidX
  releases / AGP release notes 确认与你的 `compileSdk`、Gradle、Kotlin 插件版本兼容的组合。
- **debug 与 release 差异**：debug 构建通常是 debuggable 的，本身以 JIT 为主，
  profile 安装属于额外开销；建议只在 release（及 profileable 的测试构建）中启用
  ProfileInstaller。具体用变体配置实现，而不是全局 `implementation`。

```kotlin
android {
    buildTypes {
        release {
            isDebuggable = false
            // 其余 release 配置…
        }
    }
}
```

发布后验证生效情况：

```bash
# 安装非 debuggable 的 release 构建后，观察 profile 相关日志/文件
adb shell dumpsys package dexopt com.example.app
# 输出里应能看到 baseline 相关的编译模式与 profile 信息（格式因版本而异）
```

## 验证：TTID/TTFD 对比

用 `StartupTimingMetric` 在同一设备上对比两种编译模式：

```kotlin
// :benchmark 模块
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.StartupTimingMetric
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import org.junit.Rule
import org.junit.Test

class StartupBenchmarks {
    @get:Rule
    val rule = MacrobenchmarkRule()

    @Test
    fun startupNone() = startup(compilationMode = CompilationMode.None())

    @Test
    fun startupBaselineProfile() =
        startup(compilationMode = CompilationMode.BaselineProfile())

    private fun startup(compilationMode: CompilationMode) =
        rule.measureRepeated(
            packageName = "com.example.app",
            metrics = listOf(StartupTimingMetric()),
            iterations = 10,
            startupMode = StartupMode.COLD,
            compilationMode = compilationMode,
        ) {
            startActivityAndWait()
        }
}
```

对比维度：

- **TTID（time to initial display）**：首帧显示时间；
- **TTFD（time to full display）**：`ComponentActivity.reportFullyDrawn()` 上报的完整
  显示时间，异步加载完成后才调用。

> **性能提示**：对比必须同设备、同数据、同刷新率、同构建类型。Baseline Profile 通常
> 省下几十到一两百毫秒，噪声大于收益时，先固定环境再谈结论。

## 常见陷阱

| 现象 | 根因 | 修复 |
|---|---|---|
| profile 规则过多，APK 膨胀、启动不升反降 | AOT 编译了用不到的代码，dexopt 与磁盘 I/O 变长 | 只保留启动 + 高频路径；控制编译后体积 < 1.5 MB |
| 手工规则语法错误，构建期静默忽略 | HRF 不是稳定公开 API，版本间有差异 | 优先自动生成；手工规则按目标版本验证 |
| 改了规则但发布没生效 | profile 只进 release 变体，或 AAB 里没打包 | 检查 `assets/dexopt/baseline.prof` 是否在产物中 |
| 侧载/企业分发用户没看到收益 | 非 Play 渠道安装阶段不读 profile | 说明依赖后台 dexopt；或评估 Play 分发 |
| 本地测出收益，线上没有 | debug/debuggable 构建行为与 release 不同 | 用非 debuggable 构建做验收（AGP 8.4 起本地安装也会应用） |
| 生成任务在 CI 上跑失败 | 无设备、权限监控、Firebase Test Lab | 固定本地受控设备；生成与发布验收分开 |
| 依赖版本没跟上 AGP | 旧 AGP 不识别新 profile 目录/规则 | 核验 AGP、macro、profileinstaller 三者的兼容矩阵 |

## 实践检查清单

- [ ] 先做启动热点分析，明确要覆盖的类与路径，再生成 profile。
- [ ] 用 `BaselineProfileRule` 自动采集，手工规则只做少量补充。
- [ ] profile 编译后体积远小于 1.5 MB，规则按需最小化。
- [ ] release 构建包含 `androidx.profileinstaller`，debug 构建不启用。
- [ ] 同设备、同构建对比 TTID/TTFD 的 None 与 BaselineProfile 模式。
- [ ] 已确认目标受众的 Android 版本与分发渠道对应哪种生效路径。
- [ ] 截图、功能、无障碍与常规性能指标在加 profile 后无回归。

## 小结

Baseline Profile 把"系统事后才能发现的冷启动热点"提前到构建期声明，本质是**给
ART 一份启动关键路径的预编译清单**。它解决的是首次冷启动的性能低谷，不是缓存优化的
替代品。生效与否取决于 API 版本、是否 Play 分发、ProfileInstaller 是否打进 release
构建，以及设备 dexopt 是否运行——理解这条链路，比"加上依赖就期待变快"更能避免发布
后的性能事故。

## 延伸阅读

- [Baseline Profiles 概览](https://developer.android.com/topic/performance/baselineprofiles/overview)
- [创建 Baseline Profile](https://developer.android.com/topic/performance/baselineprofiles/create-baselineprofile)
- [Profile Installer API](https://developer.android.com/reference/androidx/profileinstaller/ProfileInstaller)
- [Macrobenchmark 入门](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview)
- [时间到首帧与完全显示](https://developer.android.com/topic/performance/vitals/launch-time)
