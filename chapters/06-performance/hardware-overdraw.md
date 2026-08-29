# 硬件加速、图层与过度绘制

## 学习目标

- 理解硬件加速下 display list、RenderThread 与 GPU 的职责。
- 区分 View layer、`Canvas.saveLayer()` 与普通 `save()`。
- 用 bounded layer、短生命周期硬件层和遮挡裁剪减少真实成本。
- 使用 overdraw/HWUI/Perfetto 证据验收，而不是套用“GPU 一定更快”。

## 1. 硬件加速不是“`onDraw()` 在 GPU 上执行”

在硬件加速绘制模型中，应用 UI 线程仍执行 View 绘制代码，把 Canvas 操作记录为 display
list；RenderThread 处理渲染工作并向 GPU 提交。某个 View 未失效时，系统可复用其已记录命令，
但属性、内容、父级状态和平台策略都会影响是否重录或重放。

```text
UI thread                  RenderThread/GPU              Display

View traversal
     |
     v
onDraw(Canvas)
     |
     v
record/update display list -----> sync/prepare -----> execute commands
                                      |                    |
                                      v                    v
                                  GPU queue ----------> buffer
                                                           |
                                                           v
                                               SurfaceFlinger/display
```

> **注意**：`onDraw()` 里的 Kotlin 仍在 CPU 上运行。硬件加速改变的是绘制命令的记录与执行
> 模型，并不让业务循环、Path 构建或文本拼接自动迁移到 GPU。

运行时可检查当前 Canvas：

```kotlin
override fun onDraw(canvas: Canvas) {
    if (BuildConfig.DEBUG && !canvas.isHardwareAccelerated) {
        Log.d("MeterView", "software canvas: verify fallback rendering")
    }
    // draw...
}
```

不应仅因一个效果慢就关闭整个 Activity 的硬件加速。先确认操作支持情况、fallback 视觉结果
与实际瓶颈，再缩小作用范围。

## 2. display list：内容更新与属性更新不同

```text
内容改变（路径、文字、颜色由 onDraw 决定）
    -> invalidate() -> 可能重录 display list -> 执行

可合成属性改变（translation/alpha/scale 等）
    -> 属性更新 -> 复用已有内容的机会更大 -> 合成
```

这解释了为什么动画中移动一个复杂 View 常比每帧重建其内容便宜，但“机会更大”不是无条件
保证。测量时分别观察 UI 线程 recording、RenderThread 与 GPU。

## 3. View layer：纹理缓存有收益，也有代价

`setLayerType(View.LAYER_TYPE_HARDWARE, null)` 可把 View 渲染到硬件层，之后某些属性动画可复用
该纹理。创建/更新层需要显存、栅格化和上传；内容每帧变化时，层可能每帧重建，反而更慢。

短期动画可以显式管理生命周期：

```kotlin
fun View.fadeAndTranslate(onEnd: () -> Unit = {}) {
    animate().cancel()
    setLayerType(View.LAYER_TYPE_HARDWARE, null)
    animate()
        .alpha(0f)
        .translationY(height * 0.25f)
        .setDuration(220L)
        .withEndAction {
            setLayerType(View.LAYER_TYPE_NONE, null)
            onEnd()
        }
        .start()
}

override fun onDetachedFromWindow() {
    animate().cancel()
    setLayerType(LAYER_TYPE_NONE, null)
    super.onDetachedFromWindow()
}
```

如果动画被取消，`withEndAction` 不一定替你完成全部业务清理；生产代码应统一处理 cancel/end/
detach。更简洁时可使用 `withLayer()`，但仍须测量层建立成本与内存峰值。

### 3.1 何时考虑硬件层

| 证据 | 候选 | 风险 | 验证 |
|---|---|---|---|
| 复杂静态内容只做 alpha/translation | 动画期间硬件层 | 首帧建层尖峰、显存 | 预热后 trace，比较 p95 与内存 |
| 内容每帧重绘 | 通常不建层 | 纹理反复更新 | A/B 查看 Upload/DrawFrame |
| View 接近全屏 | 谨慎建层 | 大纹理、带宽 | GPU 时间与 PSS/显存代理指标 |
| 只需单个不支持效果的软件 fallback | View 级软件层 | CPU 与 Bitmap 成本 | 限定 View，验证滚动与视觉 |

### 3.2 动画期间的临时层：`withLayer()`

`ViewPropertyAnimator.withLayer()` 是"临时硬件层"的封装：动画开始时把 View 切换为
`LAYER_TYPE_HARDWARE`，动画结束（含取消路径）恢复为
`LAYER_TYPE_NONE`。动画期间 View 内容被栅格化进一个纹理，alpha、translation 等只改变
合成参数，逐帧更新不再重录整棵 display list。相比手写 `setLayerType` + `withEndAction`，
它把结束恢复纳入框架回调：

```kotlin
view.animate()
    .alpha(0f)
    .translationY(view.height * 0.25f)
    .setDuration(220L)
    .withLayer()          // 开始置 HARDWARE，结束自动恢复 NONE
    .withEndAction { /* 业务清理 */ }
    .start()
```

`setLayerType(type, paint)` 的三种类型差异：

| 类型 | 行为 | 典型用途 | 代价 |
|---|---|---|---|
| `LAYER_TYPE_NONE` | 不创建层，直接绘制 | 默认 | 无 |
| `LAYER_TYPE_HARDWARE` | 内容栅格化进 GPU 纹理，合成属性可复用 | 静态内容的 alpha/translation 动画 | 显存纹理、首帧建层尖峰 |
| `LAYER_TYPE_SOFTWARE` | CPU 绘制到 Bitmap 再上传 | 硬件加速下需软件 fallback 的效果 | CPU 栅格化、上传与内存 |

`paint` 参数：`LAYER_TYPE_NONE` 时忽略；硬件/软件层可传入携带 alpha 或 color filter 的
`Paint`，合成该层时生效（例如让整层半透明）。

何时该用、何时不该用：

- 该用：内容静态，动画只改变合成属性（alpha/translation/scale/rotation），且动画短暂。
- 不该用：内容每帧变化（进度条、逐帧重建的 Path、实时数据），此时层每帧重建，反而更慢、
  内存更高。
- 内存代价：硬件层占显存纹理，软件层占 Bitmap 内存；接近全屏的 View 代价最大。动画结束后
  应确认恢复为 `LAYER_TYPE_NONE`。

> **注意**：`withLayer()` 的“结束自动恢复”以动画正常走完为前提；若动画被取消或 View 提前
> detach，仍应按第 3 节方式兜底清理，不能只依赖 `withEndAction`。

## 4. `save()` 与 `saveLayer()` 不是一回事

`save()` 保存 Canvas 状态；`saveLayer()` 通常创建离屏渲染目标，把内容先画入该层，再按 Paint
合成回来。后者可实现 group alpha、复杂 blend/filter，却可能增加内存带宽与 fill-rate。

```text
saveLayer(bounds, paint)
        |
        v
allocate/reuse offscreen target [只应覆盖必要 bounds]
        |
        v
 draw children/effects into layer
        |
        v
restore -> composite layer back to parent target
```

使用紧边界，且只在效果语义确实需要隔离时调用：

```kotlin
override fun onDraw(canvas: Canvas) {
    super.onDraw(canvas)
    effectBounds.set(contentBounds)
    effectBounds.inset(-blurRadius, -blurRadius)

    val checkpoint = canvas.saveLayer(effectBounds, groupPaint)
    try {
        canvas.drawPath(fillPath, fillPaint)
        canvas.drawPath(highlightPath, highlightPaint)
    } finally {
        canvas.restoreToCount(checkpoint)
    }
}
```

`effectBounds` 必须覆盖描边、模糊和变换后的像素，否则会裁切。也不要机械地把 bounds 改成全屏；
应以截图正确性和 trace/GPU 时间双重验收。

## 5. 过度绘制（overdraw）与无效绘制

同一像素在最终呈现前被重复覆盖就是过度绘制。它可能来自窗口背景、容器背景、子 View 背景、
不可见区域、重叠装饰和大面积半透明层。

```text
pixel P:
window background  [1]
card background    [2]
opaque image       [3]
overlay tint        [4]  -> 前三次中可能有可消除工作
```

但颜色调试图不是性能结论：现代 GPU、blend、纹理采样、分辨率和遮挡处理都会影响成本。
先用过度绘制可视化找候选，再用帧/GPU 数据验证。

```bash
# 开发设备上开启/关闭过度绘制调试；不同系统版本可用项可能不同。
adb shell setprop debug.hwui.overdraw show
adb shell setprop debug.hwui.overdraw false

# 快速查看 HWUI 帧统计：
adb shell dumpsys gfxinfo com.example.app reset
adb shell dumpsys gfxinfo com.example.app framestats
```

也可在开发者选项中启用 **Debug GPU overdraw**。采集基线截图后逐层排查：

1. 去掉被不透明内容完全覆盖的 window/root 背景。
2. 合并相邻且语义相同的背景/装饰绘制。
3. 对大数据图只遍历可见索引，先做粗粒度裁剪。
4. 给 `saveLayer()` 设紧边界，避免全屏离屏层。
5. 逐项恢复并做 A/B，防止透明度、圆角和无障碍焦点视觉回归。

### 5.1 自定义 View 的可见范围裁剪

```kotlin
override fun onDraw(canvas: Canvas) {
    super.onDraw(canvas)
    if (!canvas.getClipBounds(clipBounds)) return

    val first = data.indexAtOrBefore(clipBounds.left.toFloat())
    val last = data.indexAtOrAfter(clipBounds.right.toFloat())
    for (index in first.coerceAtLeast(0)..last.coerceAtMost(data.lastIndex)) {
        drawItem(canvas, index)
    }
}
```

`getClipBounds()` 是候选范围，不一定等于最终硬件 scissor 或可见像素。还要处理空数据、变换和
索引越界，并通过 trace 确认循环次数和 CPU 时间真的下降。

## 6. 诊断表：看哪条轨道，改哪一层

| 现象 | 证据位置 | 可能原因 | 反证/下一步 |
|---|---|---|---|
| UI 线程 `onDraw` 长 | 自定义 trace section | Path/文字/遍历构建重 | 缓存几何后 section 是否缩短 |
| UI 正常、RenderThread 长 | HWUI `DrawFrame` | 层同步、复杂 display list | 去掉 layer/effect 做 A/B |
| GPU 晚且大面积半透明 | FrameTimeline/GPU | blend、fill-rate、离屏层 | 缩小 bounds/分辨率后 GPU 是否下降 |
| 动画第一帧尖峰 | layer build/upload | 临时硬件层建立 | 延后开始/不建层对比 |
| 每帧都有 layer 更新 | RenderThread/HWUI | 层内容持续失效 | 移除硬件层，改属性/内容策略 |
| overdraw 颜色重但帧正常 | overdraw overlay + 帧指标 | 有重复覆盖但不是瓶颈 | 不为分数破坏正确层次 |
| 软件 fallback 视觉不同 | `canvas.isHardwareAccelerated` A/B | 操作支持/渲染差异 | 最小范围 fallback + 截图测试 |

## 7. 优化前后验收标准

| 维度 | 优化前需保存 | 通过标准示例 |
|---|---|---|
| FrameTimeline | 同场景 jank 类型与失败帧 | 目标 GPU/HWUI jank 显著下降 |
| CPU/RenderThread | 关键 slice p50/p95 | 目标 slice 降低，其他 slice 无转移性恶化 |
| GPU | GPU completion/相关 counters | p95 下降且不只是刷新率变化 |
| 内存 | 动画前后 PSS、层/Bitmap 代理指标 | 峰值不超过预算，结束后可回落 |
| overdraw | 关键页面调试截图 | 被证实无用的覆盖减少 |
| 正确性 | 硬件/软件、主题、缩放截图 | blend、阴影、圆角、透明度在容差内 |
| 生命周期 | cancel/end/detach 测试 | 不残留 layer、动画或 View 引用 |

示例实验应保持设备、显示模式、构建和手势一致，至少重复多次。若“GPU 降低 20%”但卡顿率、
CPU 或内存变差，应按预先写下的产品门槛判定，而非只挑最好看的指标。

## 8. 常见陷阱

- 把 `LAYER_TYPE_HARDWARE` 当永久加速开关。
- 为每个子 View 建层，导致大量纹理和首帧建立成本。
- `saveLayer(null, ...)` 无边界地扩大离屏区域。
- 删除背景后漏出窗口底色、破坏滚动瞬间或转场视觉。
- 用过度绘制颜色多少直接代替 GPU 性能测量。
- 只在一种 API/设备验证硬件与软件绘制差异。
- 动画取消或 View detach 后忘记撤销 layer。

## 9. 实践检查清单

- [ ] 已在 Perfetto 中区分 UI、RenderThread、GPU 与合成耗时。
- [ ] 临时硬件层只有明确建立/撤销时机，并覆盖 cancel/detach。
- [ ] 每个 `saveLayer()` 都有最小正确 bounds 和效果必要性说明。
- [ ] overdraw 候选经过 A/B 帧数据验证，而非只看颜色。
- [ ] 优化没有把 CPU 成本转移成更高 GPU/内存成本。
- [ ] 已运行视觉回归与生命周期测试。

## 小结

硬件加速的核心是 display list 记录、RenderThread 准备和 GPU 执行的协作。View layer 与
`saveLayer()` 都以额外表面、内存和带宽换取特定效果或复用机会；过度绘制只是候选信号。
先沿流水线定位，再做边界明确的单变量实验，最后以帧、GPU、内存和视觉结果共同验收。

## 官方资料

- [Hardware acceleration](https://developer.android.com/develop/ui/views/graphics/hardware-accel)
- [Canvas.saveLayer](https://developer.android.com/reference/android/graphics/Canvas#saveLayer(android.graphics.RectF,android.graphics.Paint))
- [View layers](https://developer.android.com/develop/ui/views/graphics/hardware-accel#layers)
- [Inspect GPU rendering speed and overdraw](https://developer.android.com/topic/performance/rendering/inspect-gpu-rendering)
- [Perfetto FrameTimeline data source](https://perfetto.dev/docs/data-sources/frametimeline)
