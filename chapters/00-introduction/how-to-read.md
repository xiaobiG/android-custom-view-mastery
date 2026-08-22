# 如何使用本书

自定义控件的难点不在于记住若干回调，而在于建立一套可验证的心智模型：谁发起遍历、约束怎样传递、坐标在哪里确定、画面何时真正提交，以及输入、动画和生命周期如何共同改变状态。本书以经典 View 体系为主线，面向已经能使用 Kotlin 编写 Android 应用、理解 Activity/Fragment 生命周期和基本布局 XML 的读者。

## 学习目标

读完本章，你应当能够：

- 选择适合自己的阅读路线，而不是从 API 列表开始死记；
- 用“状态—约束—几何—像素—输入”五层模型分析控件问题；
- 把示例改造成最小可复现工程，并用工具验证推断；
- 区分平台契约、源码实现细节与经验性优化；
- 建立每章都可重复使用的实践和复盘方法。

## 一、先问为什么，再进入回调

一个可靠的自定义 View 通常同时承担五类职责：

1. **状态（state）**：公开属性、交互状态、可保存状态；
2. **约束（constraints）**：读取 `MeasureSpec`，给出期望尺寸；
3. **几何（geometry）**：确定内容区、命中区和子元素位置；
4. **像素（pixels）**：按确定顺序绘制，并控制重绘范围；
5. **输入与语义（input & semantics）**：处理触摸、键盘和无障碍操作。

```text
外部属性 / 用户输入
        |
        v
     [状态模型]
        |
        +----尺寸变化----> requestLayout()
        |
        +----像素变化----> invalidate()
        v
  measure -> layout -> draw
        |
        v
 屏幕像素 + 无障碍语义
```

遇到问题时，不要先猜该覆盖哪个回调。先判断变化属于哪一层：文字变长可能影响尺寸和像素；高亮颜色只影响像素；拖动位置可能只需重绘，也可能改变布局。分类正确，调用 `requestLayout()` 还是 `invalidate()` 往往自然清晰。

## 二、推荐的阅读闭环

每章建议按以下顺序使用：

1. **读学习目标**：把目标改写成待回答的问题；
2. **看流程图**：先获得调用关系，再阅读细节；
3. **运行最小示例**：不要直接嵌入复杂业务页面；
4. **加入日志或断点**：验证回调次数、参数和线程；
5. **故意制造错误**：例如返回超出约束的尺寸；
6. **完成检查清单**：把“看懂”转化为“能验收”；
7. **记录边界**：注明 API 级别、父容器和硬件加速条件。

> **注意**：Android 开源项目（AOSP）源码有助于理解实现，但应用应优先依赖公开 API 契约。内部字段、调用次数和优化策略可能随版本变化。

## 三、建立可验证的实验控件

下面的 Kotlin 控件把三个关键遍历回调记录出来。它不是产品代码，而是用于观察父约束、最终尺寸和绘制时机的实验探针。

```kotlin
package com.example.customview.lab

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.util.AttributeSet
import android.util.Log
import android.view.View

class LifecycleProbeView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredWidth = 160.dp
        val desiredHeight = 80.dp
        setMeasuredDimension(
            resolveSize(desiredWidth, widthMeasureSpec),
            resolveSize(desiredHeight, heightMeasureSpec)
        )
        Log.d("Probe", "measure spec=($widthMeasureSpec,$heightMeasureSpec) " +
            "result=${measuredWidth}x$measuredHeight")
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        Log.d("Probe", "size $oldw x $oldh -> $w x $h")
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.rgb(40, 120, 220))
        Log.d("Probe", "draw size=${width}x$height")
    }

    private val Int.dp: Int
        get() = (this * resources.displayMetrics.density + 0.5f).toInt()
}
```

分别把它放进 `FrameLayout`、`LinearLayout` 和可滚动容器，比较日志。改变 `layout_width` 为 `wrap_content`、固定 dp 和 `match_parent`，记录父容器给出的模式及结果。你会发现“控件自己决定大小”是不准确的：它只能在父级传下来的约束中协商。

> **性能提示**：日志和方法追踪会改变时序。性能结论应在关闭调试日志、使用接近发布配置的设备上，以 Perfetto 或帧时间数据验证。

## 四、如何阅读代码与源码

书中的 Kotlin 示例分为三类：

- **契约示例**：只使用公开 API，可直接作为实现起点；
- **实验示例**：为暴露回调和边界而写，不强调封装与性能；
- **伪源码**：用流程图或伪代码压缩系统实现，不可复制进应用。

阅读平台源码时，建议从入口向两侧展开：例如从 `ViewRootImpl.performTraversals()` 观察测量、布局、绘制；从 `View.draw()` 观察绘制顺序；再回到公开回调确认应用可依赖的边界。源码中的 `mPrivateFlags` 等字段只能用来解释现象，不应通过反射访问。

## 五、验证工具箱

- **Layout Inspector**：检查运行时 View 树、尺寸和属性；
- **Developer options**：用“显示布局边界”“GPU 呈现模式分析”快速观察；
- **Perfetto / System Trace**：定位帧调度、主线程阻塞和渲染阶段；
- **Profile GPU Rendering**：粗看连续帧是否超出预算；
- **单元与仪器测试**：固定约束后断言测量尺寸、状态恢复与操作结果。

> **无障碍提示**：视觉正确不等于控件可用。每个交互控件都要验证 TalkBack 描述、键盘焦点、最小触摸目标和自定义操作；不要把无障碍留到视觉完成之后。

## 六、常见陷阱

1. **按章节复制最终代码，却不运行实验**：会记住写法而无法迁移到新问题。
2. **把一次日志当作稳定调用次数**：遍历可能因父容器、动画或窗口状态重复发生。
3. **只在一台设备验证**：密度、字体缩放、RTL 和刷新率都会暴露假设。
4. **在 `onDraw()` 中持续分配对象**：功能正常，却产生频繁 GC 和帧抖动。
5. **忽略生命周期**：未在 `onDetachedFromWindow()` 停止回调、动画或监听器。
6. **把硬件层当万能开关**：图层有内存和更新成本，必须基于数据选择。

## 七、实践检查清单

- [ ] 我能把需求中的变化归类为状态、尺寸、位置、像素或输入。
- [ ] 我能说明示例依赖的是公开契约还是某版本源码实现。
- [ ] 我在至少两种父容器和三种尺寸参数下运行过实验控件。
- [ ] 我用日志、Layout Inspector 或 Perfetto 验证过至少一个推断。
- [ ] 我检查过密度、字体缩放、RTL、暗色主题和配置变化。
- [ ] 我为可交互控件检查了 TalkBack 与键盘操作。
- [ ] 我能说明何时释放动画、监听器和帧回调。

## 小结

学习自定义控件的核心是形成“提出模型—制造实验—观察证据—修正模型”的闭环。把状态、约束、几何、像素和输入分层后，复杂问题会从回调猜谜变为因果分析。后续章节将沿窗口到 View 树的完整路径，逐层拆解 measure、layout、draw 和帧调度。

## 官方延伸阅读

- [Create a custom view](https://developer.android.com/develop/ui/views/layout/custom-views/create-view)
- [Custom drawing](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing)
- [App performance guide](https://developer.android.com/topic/performance)
- [Inspect your app's layout](https://developer.android.com/studio/debug/layout-inspector)
- [Test your app's accessibility](https://developer.android.com/guide/topics/ui/accessibility/testing)
