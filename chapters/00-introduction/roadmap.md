# 学习路线与项目地图

自定义控件横跨窗口、View 树、绘图、输入、动画、性能和无障碍。最有效的路线不是把所有 API 顺序读完，而是围绕逐步扩大的项目反复练习：先做一个尺寸明确的只读 View，再增加交互和容器能力，最后把它放进真实应用环境中验证。

## 学习目标

读完本章，你应当能够：

- 根据目标选择基础、交互、容器或性能路线；
- 理解全书各篇之间的依赖关系；
- 用递进项目覆盖测量、绘制、事件、动画和状态保存；
- 为每个阶段定义可执行的验收标准；
- 避免“效果先行、契约缺失”的学习方式。

## 一、知识依赖地图

第一篇是全书地基。若不理解 measure/layout/draw，后续绘图技巧很容易建立在错误尺寸或错误失效策略上；事件与动画又依赖坐标、状态和帧调度。

```text
                 +-------------------+
                 |  View 工作原理     |
                 +---------+---------+
                           |
           +---------------+----------------+
           v                                v
   +-------+--------+               +-------+--------+
   | Canvas 绘制体系 |               | 事件与手势      |
   +-------+--------+               +-------+--------+
           |                                |
           +---------------+----------------+
                           v
                  +--------+---------+
                  | ViewGroup / 动画  |
                  +--------+---------+
                           |
        +------------------+------------------+
        v                  v                  v
      性能优化          状态与样式          无障碍
        +------------------+------------------+
                           v
                    测试 / Compose 互操作
                           |
                           v
                       综合实战
```

这些并非严格的单向依赖。例如做手势时会回到性能篇检查每帧分配，做无障碍虚拟节点时会回到几何篇复用命中区域。回读不是退步，而是把局部知识接入完整系统。

## 二、四条阅读路线

### 1. 基础实现路线

适合第一次系统编写自定义 View 的读者：

`第一篇 → 第二篇 → 第七篇 → 第九篇`

目标是能实现一个支持 XML 属性、正确测量、状态保存和截图测试的展示控件。

### 2. 复杂交互路线

适合图表、画板、编辑器：

`第一篇 → 第二篇 → 第三篇 → 第五篇 → 第六篇 → 第八篇`

重点是坐标变换、手势状态机、多点触控、惯性、帧预算和虚拟无障碍节点。

### 3. 自定义容器路线

适合流式布局、标签布局、拖拽编排：

`第一篇 → 第四篇 → 第三篇 → 第九篇`

重点是为每个子 View 生成约束、保存布局参数、处理边距、确定位置并协调事件拦截。

### 4. 迁移与互操作路线

适合维护既有 View 组件并接入 Compose：

`第一篇 → 第七篇 → 第九篇 → 第十篇`

先明确 View 的状态和生命周期契约，再讨论 `AndroidView` 的复用与状态同步。Compose 不是把既有问题自动消除的开关。

## 三、递进项目地图

建议在同一个示例应用中建立五个独立模块或页面，每一阶段保留测试和性能基线。

| 阶段 | 项目 | 核心能力 | 验收证据 |
|---|---|---|---|
| A | 圆形进度控件 | 测量、Paint、属性 | 三种约束下尺寸正确，截图稳定 |
| B | 评分控件 | 触摸、RTL、状态 | 触摸/键盘/TalkBack 均可修改评分 |
| C | 可缩放折线图 | Path、Matrix、多点触控 | 缩放锚点稳定，连续手势无跳变 |
| D | FlowLayout | 子 View 测量与布局 | margin、换行、RTL 和滚动容器正确 |
| E | 签名画板/流程图 | 缓存、局部失效、保存 | 长时绘制不卡顿，旋转后状态可恢复 |

```text
ProgressView
   | + attributes + saved state
   v
RatingView
   | + gesture state machine + accessibility
   v
ZoomableChart
   | + matrix + multi-touch + frame budget
   v
FlowLayout
   | + child constraints + LayoutParams
   v
Editor / SignaturePad
     + architecture + profiling + tests
```

## 四、用验收标准驱动实现

每个项目开始前写出四类标准：

- **功能**：属性和操作产生什么可观察结果；
- **契约**：不同 `MeasureSpec`、RTL、字体缩放下如何表现；
- **生命周期**：分离窗口、配置变化、状态恢复时如何处理；
- **非功能**：帧时间、分配、无障碍和测试覆盖。

下面是可复用的 Kotlin 验证辅助 View。它把期望内容尺寸交给系统约束解析，可作为项目 A 的起点。

```kotlin
package com.example.customview.roadmap

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

class MilestoneView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 6f * resources.displayMetrics.density
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desired = (96f * resources.displayMetrics.density).toInt()
        val desiredWidth = desired + paddingLeft + paddingRight
        val desiredHeight = desired + paddingTop + paddingBottom
        setMeasuredDimension(
            resolveSize(desiredWidth, widthMeasureSpec),
            resolveSize(desiredHeight, heightMeasureSpec)
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val contentWidth = width - paddingLeft - paddingRight
        val contentHeight = height - paddingTop - paddingBottom
        val radius = min(contentWidth, contentHeight) / 2f - paint.strokeWidth / 2f
        if (radius > 0f) {
            canvas.drawCircle(
                paddingLeft + contentWidth / 2f,
                paddingTop + contentHeight / 2f,
                radius,
                paint
            )
        }
    }
}
```

这里刻意把 padding 纳入测量和绘制。下一步可以加入 `progress` 属性：值变化但尺寸不变时调用 `invalidate()`；若增加可变宽度文字并让其影响期望尺寸，则调用 `requestLayout()`。

> **注意**：验收标准要描述外部可观察行为，不要绑定 `onMeasure()` 必须调用几次等实现细节。

## 五、阶段性练习

### 第一阶段：约束与像素

- 在 `EXACTLY`、`AT_MOST`、`UNSPECIFIED` 下记录结果；
- 支持 padding 和最小尺寸；
- 不在 `onDraw()` 创建 Paint、Path 或临时集合。

### 第二阶段：输入与状态

- 把触摸坐标转换为业务值；
- 使用 `performClick()` 保持点击语义；
- 实现键盘操作和 `onSaveInstanceState()`。

### 第三阶段：容器与性能

- 为子 View 生成正确的 MeasureSpec；
- 使用 Perfetto 观察拖动和动画帧；
- 只在证据支持时使用缓存或硬件层。

> **无障碍提示**：项目验收必须包含至少一次 TalkBack 实机检查。自动化扫描能发现部分问题，但不能替代完整操作流程。

> **性能提示**：高刷新率设备的单帧预算更短。不要把“16.6 ms”当作所有设备恒定预算，应以目标设备的 VSync 周期和实际 trace 为准。

## 六、常见陷阱

1. **先做复杂编辑器**：问题横跨太多层，难以定位失败原因。
2. **只验视觉截图**：尺寸契约、输入语义和生命周期仍可能错误。
3. **跳过第一篇直接学 Canvas**：能画出图，不代表能正确协商尺寸和重绘。
4. **把示例项目做成复制仓库**：没有主动改变约束，就难以形成迁移能力。
5. **优化没有基线**：缓存或图层可能使内存和更新成本更高。
6. **只测默认字体和 LTR**：文字截断、焦点顺序和镜像问题会上线后出现。

## 七、实践检查清单

- [ ] 我已选择一条主路线，并知道缺少哪些前置知识。
- [ ] 每个递进项目都有功能、契约、生命周期和非功能标准。
- [ ] 项目 A 能在固定尺寸、`wrap_content` 和 `match_parent` 下运行。
- [ ] 项目 B 支持触摸、键盘、TalkBack 和状态恢复。
- [ ] 项目 C/E 有真实设备的帧 trace，而不只是主观“流畅”。
- [ ] 项目 D 覆盖 margin、padding、RTL 和可滚动父容器。
- [ ] 所有持续回调和动画都在窗口分离时释放。

## 小结

全书路线以 View 工作原理为根，再向绘图、输入、容器和动画分叉，最终在性能、状态、无障碍与测试中汇合。用五个递进项目承载知识，并为每一步保留可观察的验收证据，比完成 API 清单更能形成工程能力。

## 官方延伸阅读

- [Custom view components](https://developer.android.com/develop/ui/views/layout/custom-views/custom-components)
- [Layouts](https://developer.android.com/develop/ui/views/layout/declaring-layout)
- [Input events overview](https://developer.android.com/develop/ui/views/touch-and-input/input-events)
- [Accessibility principles](https://developer.android.com/guide/topics/ui/accessibility/principles)
- [Inspect performance with system tracing](https://developer.android.com/topic/performance/tracing)
- [Using Views in Compose](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose)
