# 减少分配、缓存与局部更新

## 学习目标

- 用分配记录和 GC 事件验证 `onDraw()` 热路径，而不是凭代码风格猜测。
- 正确缓存 `Paint`、`Path`、`RectF`、几何结果与 Bitmap。
- 用版本号/脏标记管理缓存失效，避免“快但画错”。
- 区分 `invalidate()`、局部失效与 `requestLayout()` 的适用边界。

## 1. 为什么绘制热路径中的分配危险

`onDraw()`、动画更新和触摸移动可能每个刷新周期执行。单次小分配不一定立刻造成问题，
但持续分配会增加分配器工作、堆增长与垃圾回收（GC）概率；Bitmap 还会消耗显著内存。
结论必须通过 allocation recording、GC trace 和帧数据共同验证。

```text
frame N:   input -> update -> onDraw [alloc alloc] -> submit
                                  |
                                  v
heap:      live + garbage + garbage + ... -> GC pause/work
                                              |
frame N+k: ---------------- deadline ----------X

目标不是“任何地方零分配”，而是让高频且可复用的对象不在帧循环中反复创建。
```

> **性能提示**：优化前先录制。若分配不在失败帧附近，改成缓存可能只增加状态复杂度，
> 甚至因缓存过大造成内存压力。

## 2. 反例：把工作留到 `onDraw()`

```kotlin
// 反例：每帧创建 Paint、Path、RectF、字符串和临时集合。
override fun onDraw(canvas: Canvas) {
    val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    val path = Path()
    val bounds = RectF(0f, 0f, width.toFloat(), height.toFloat())
    val visible = points.filter { it.x in 0f..width.toFloat() }
    canvas.drawText("${visible.size} points", 16f, 32f, paint)
    // ...
}
```

问题不只是对象数量：`filter` 创建列表，字符串模板创建文本，几何又在尺寸未变时重复计算。
先在 Android Studio Memory Profiler 录制同一手势，按分配次数和调用栈确认热点。

## 3. 对象缓存：长期对象只保存必要状态

```kotlin
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

class SparklineView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = resources.displayMetrics.density * 2f
    }
    private val plotBounds = RectF()
    private val linePath = Path()
    private var samples: FloatArray = FloatArray(0)
    private var geometryDirty = true

    fun setSamples(value: FloatArray) {
        // 防止调用方随后原地修改，建立明确所有权。
        samples = value.copyOf()
        geometryDirty = true
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        plotBounds.set(
            paddingLeft.toFloat(),
            paddingTop.toFloat(),
            (w - paddingRight).toFloat(),
            (h - paddingBottom).toFloat()
        )
        geometryDirty = true
    }

    private fun rebuildGeometryIfNeeded() {
        if (!geometryDirty) return
        linePath.rewind()
        if (samples.isNotEmpty() && plotBounds.width() > 0f) {
            val dx = plotBounds.width() / (samples.size - 1).coerceAtLeast(1)
            samples.forEachIndexed { index, normalizedY ->
                val x = plotBounds.left + index * dx
                val y = plotBounds.bottom -
                    normalizedY.coerceIn(0f, 1f) * plotBounds.height()
                if (index == 0) linePath.moveTo(x, y) else linePath.lineTo(x, y)
            }
        }
        geometryDirty = false
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        rebuildGeometryIfNeeded()
        canvas.drawPath(linePath, linePaint)
    }
}
```

这个实现仍可能在 `setSamples()` 分配一次，但数据更新通常远少于帧绘制；关键是用 profiler
验证分配已从每帧热路径移出。若数据也每帧更新，应使用有明确容量和所有权的可复用缓冲，
而不是盲目 `copyOf()`。

### 3.1 可复用缓冲而非无界对象池

```kotlin
private var xy = FloatArray(0)

private fun ensurePointCapacity(pointCount: Int) {
    val needed = pointCount * 2
    if (xy.size < needed) {
        xy = FloatArray(needed.coerceAtLeast(xy.size * 2).coerceAtLeast(32))
    }
}
```

容量增长应有上限与监控。为廉价小对象建立通用对象池，可能引入同步、悬挂引用和重置遗漏；
只有 profiler 证明收益时才采用。

## 4. 几何缓存：列出所有失效来源

缓存 `Path` 的难点不是构建，而是失效。尺寸、padding、RTL、字体、density、数据、缩放、
样式都可能改变结果。推荐把依赖集中为版本号：

```text
inputVersion ----+
sizeVersion -----+--> geometryVersion --> Path/Rect/label positions
styleVersion ----+                         |
zoomVersion -----+                         v
                                      draw current cache

任一依赖变化 -> version++ -> 下一次绘制前重建一次
```

```kotlin
private var geometryVersion = 0L
private var builtVersion = -1L

fun setZoom(newZoom: Float) {
    if (zoom == newZoom) return
    zoom = newZoom
    geometryVersion++
    invalidate()
}

private fun ensureGeometry() {
    if (builtVersion == geometryVersion) return
    rebuildPathAndLabels()
    builtVersion = geometryVersion
}
```

对于会影响 `measuredWidth/Height` 的属性，调用 `requestLayout()`；只影响像素内容时调用
`invalidate()`。不要为颜色变化触发完整测量布局。

## 5. Bitmap 缓存：先算内存账，再测 GPU/CPU

把复杂静态背景栅格化到 Bitmap 可能减少重复 CPU 绘制，却增加内存、上传和缩放成本。
ARGB_8888 的粗略像素存储量是 `width × height × 4` 字节，尚未包含其他开销。

```kotlin
private var backgroundBitmap: Bitmap? = null
private var bitmapKey: CacheKey? = null

data class CacheKey(val width: Int, val height: Int, val themeId: Int)

private fun ensureBackgroundBitmap(key: CacheKey) {
    if (bitmapKey == key && backgroundBitmap?.isRecycled == false) return

    // API 11+ 通常让 GC 管理像素内存；清除独占引用即可。
    // 若要主动复用内存，应建立 inBitmap/缓冲复用协议，而不是立即 recycle。
    backgroundBitmap = null
    bitmapKey = null

    if (key.width <= 0 || key.height <= 0) return
    backgroundBitmap = Bitmap.createBitmap(
        key.width, key.height, Bitmap.Config.ARGB_8888
    ).also { bitmap ->
        drawStaticBackground(Canvas(bitmap))
    }
    bitmapKey = key
}

override fun onDetachedFromWindow() {
    backgroundBitmap = null
    bitmapKey = null
    super.onDetachedFromWindow()
}
```

> **注意**：API 11+ 通常不需要主动 `recycle()`；清除强引用后由运行时回收像素内存。
> 即使 Bitmap 由 View 创建，硬件渲染也可能仍在消费先前记录的绘制命令，过早 `recycle()`
> 会导致 “trying to use a recycled bitmap”。资源解码 Bitmap、共享缓存或异步绘制尤其需要
> 明确所有权与复用协议。

Bitmap 缓存候选必须做 A/B：比较 CPU 帧时间、GPU 时间、内存峰值和视觉质量。硬件加速
已经会记录 display list；“先画进 Bitmap”并不天然更快。

## 6. 局部失效：只在语义与测量都支持时使用

若只有一个游标移动，可失效旧、新区域的并集，而不是无条件刷新整个 View：

```kotlin
private val oldDirty = Rect()
private val newDirty = Rect()
private val unionDirty = Rect()

fun moveCursor(newX: Float) {
    cursorBounds(cursorX, oldDirty)
    cursorX = newX
    cursorBounds(cursorX, newDirty)
    unionDirty.set(oldDirty)
    unionDirty.union(newDirty)
    unionDirty.inset(-2, -2) // 覆盖抗锯齿、描边与阴影余量
    invalidate(unionDirty)
}
```

```text
old cursor bounds ----+
                      +--> union + effect margin --> invalidate(rect)
new cursor bounds ----+                               |
                                                      v
                                      重绘传播/裁剪由 View 层级决定
```

局部失效不是“保证 GPU 只处理这个矩形”的契约；父容器、变换、阴影、平台渲染策略可能扩大
区域。必须在 trace/HWUI 数据中确认收益。若脏区计算本身昂贵，整 View 失效可能更便宜。

## 7. 缓存策略诊断表

| 症状/证据 | 候选措施 | 必须同时检查 | 不应采用的情况 |
|---|---|---|---|
| `onDraw` 每帧大量 `Paint/Path/RectF` | 变为字段并重置内容 | 分配栈、GC、线程所有权 | 对象只在低频配置路径创建 |
| 尺寸不变却重复建 Path | 脏标记/版本缓存 | 所有失效依赖、视觉回归 | 几何每帧确实变化 |
| 静态复杂背景 CPU 录制昂贵 | 有界 Bitmap 缓存 | 内存峰值、上传、缩放质量 | 大尺寸/多主题导致缓存爆炸 |
| 大 View 仅小区域变化 | `invalidate(Rect)` | 阴影、描边、变换、父级传播 | 脏区接近全屏或计算更贵 |
| 周期性 GC 对齐卡顿 | 移出热路径分配 | 活对象增长、泄漏 | GC 与失败帧无时间相关性 |
| 缓存命中高但内存上涨 | 限额/LRU/生命周期清理 | 命中率、淘汰率、PSS | 为极少复用项长期保留 |

## 8. 优化前后验收标准

先写门槛再改代码。示例：

| 指标 | 优化前 | 验收标准 |
|---|---:|---:|
| 固定 10 s 拖动期间 `onDraw` 分配次数 | profiler 实测 | 目标类分配为 0，其他分配下降且可解释 |
| GC 事件 | trace 实测 | 热交互窗口内不再出现由该 View 分配触发的 GC |
| 帧卡顿率与 p95 | Macrobenchmark 实测 | 不劣化，并达到预先约定的改善幅度 |
| Java/native PSS 峰值 | `dumpsys meminfo` 实测 | 不超过产品内存预算 |
| Bitmap 缓存命中/淘汰 | 日志或计数器实测 | 命中率达到预期，无尺寸变化抖动 |
| 视觉结果 | 截图基线 | 浅色/深色、RTL、缩放、旋转均在容差内 |

```bash
adb shell dumpsys gfxinfo com.example.app reset
# 执行固定手势后：
adb shell dumpsys gfxinfo com.example.app framestats
adb shell dumpsys meminfo com.example.app
```

`gfxinfo` 适合快速对照，不替代 Perfetto 与 Macrobenchmark 的完整归因和自动化统计。

## 9. 常见陷阱

- 缓存缺少 theme、density、RTL 或 zoom 等 key，旋转/切主题后画错。
- 为避免一次分配而保留 Activity/View 引用，造成更严重的泄漏。
- 在多个线程共享可变 `Paint`、`Path` 或 Bitmap，却没有所有权约束。
- 复用 `Path` 前忘记调用 `reset()`/`rewind()`，导致上一版轮廓残留；两者都会清空几何且保留 fill type，`rewind()` 还会保留内部存储以便复用。
- 把 `requestLayout()` 当通用刷新 API，引发不必要的 measure/layout。
- 只看分配次数，不看活对象、GC 与帧 deadline 的时间关联。

## 10. 实践检查清单

- [ ] allocation recording 已覆盖真实高频交互。
- [ ] `onDraw()` 中没有未经证据支持的对象/集合/字符串创建。
- [ ] 每个缓存都有 key、上限、失效条件、所有者和释放时机。
- [ ] 局部失效包含旧区域、新区域和抗锯齿/效果边界。
- [ ] Bitmap 缓存已核算内存，并与 display list 方案做 A/B。
- [ ] 前后使用相同脚本复测帧分布、GC、内存和截图。

## 小结

减少分配的目标是移除已证实的热路径压力；缓存的本质是用内存和失效复杂度交换重复计算。
对象、几何、Bitmap 与局部失效都必须有可观察指标、完整缓存键和生命周期。只有当前后 trace、
分配记录、内存与视觉测试共同通过，优化才成立。

## 官方资料

- [Manage your app's memory](https://developer.android.com/topic/performance/memory)
- [Managing Bitmap memory](https://developer.android.com/topic/performance/graphics/manage-memory)
- [Analyze memory usage with the Memory Profiler](https://developer.android.com/studio/profile/memory-profiler)
- [Custom drawing](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing)
- [View.invalidate(Rect)](https://developer.android.com/reference/android/view/View#invalidate(android.graphics.Rect))
