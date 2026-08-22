# 控件 API 与状态模型

## 学习目标

- 设计单一事实来源（single source of truth）的控件状态。
- 区分立即赋值、动画命令、用户事件与观察回调。
- 让 XML、Kotlin 调用、无障碍操作和状态恢复走同一提交路径。
- 避免双向绑定回环、可变对象泄漏和监听器生命周期问题。

## 1. 先定义状态，再定义方法

控件 API 不应是 setter 的随机集合。先写出状态、不变量与事件，再决定哪些公开。

```text
           XML / Kotlin / restore / accessibility
                         |
                         v
                 validate + normalize
                         |
                         v
              immutable internal state
                 /       |        \
              draw    semantics   callback(event only)
```

以范围选择器为例，核心状态可以是：

```kotlin
@Immutable
data class RangeSelection(
    val start: Float,
    val end: Float,
) {
    init {
        require(start in 0f..1f)
        require(end in 0f..1f)
        require(start <= end)
    }
}
```

如果项目不是 Compose 工程，可省略 `@Immutable`；关键是对外返回不可变快照，不暴露内部可变集合、`Path` 或 `RectF`。

## 2. 明确 API 的命令与查询

```kotlin
class RangeSelectorView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    fun interface OnSelectionChangeListener {
        fun onSelectionChanged(
            view: RangeSelectorView,
            selection: RangeSelection,
            fromUser: Boolean,
        )
    }

    var selection: RangeSelection = RangeSelection(0.25f, 0.75f)
        private set

    var isSelectionEnabled: Boolean = true
        set(value) {
            if (field == value) return
            field = value
            isEnabled = value
            refreshDrawableState()
            invalidate()
        }

    private var listener: OnSelectionChangeListener? = null

    fun setOnSelectionChangeListener(listener: OnSelectionChangeListener?) {
        this.listener = listener
    }

    fun setSelection(
        selection: RangeSelection,
        animate: Boolean = false,
    ) {
        submitSelection(selection, fromUser = false, animate = animate)
    }

    private fun submitSelection(
        newValue: RangeSelection,
        fromUser: Boolean,
        animate: Boolean,
    ) {
        if (selection == newValue) return
        if (animate && isLaidOut) {
            animateSelection(selection, newValue, fromUser)
        } else {
            commitSelection(newValue, fromUser)
        }
    }

    private fun commitSelection(value: RangeSelection, fromUser: Boolean) {
        if (selection == value) return
        selection = value
        invalidate()
        updateContentDescription()
        listener?.onSelectionChanged(this, value, fromUser)
    }
}
```

公开 setter 默认表示“设为此值”，不应暗中总是动画。动画是调用方可见的策略参数或单独命令。对于频繁更新，可再提供 `jumpToSelection`，但命名必须表达语义。

> **无障碍提示**
> 用户触摸、键盘、无障碍 action 最终应调用同一个 `submitSelection(..., fromUser = true)`，这样边界、回调与语义更新不会分叉。

## 3. 事件回调不是状态源

监听器用于通知已经发生的变化，而不是请求外部把值“再设置回来”。推荐约定：

- 值真正变化时才回调。
- `fromUser` 表示输入来源，不表示线程或合法性。
- 程序设置是否回调要稳定并写入文档；上例选择回调。
- 连续拖拽与最终提交若都重要，拆成 `onSelectionChanged` 和 `onSelectionChangeFinished`。

双向绑定时使用相等判断阻断回环：

```kotlin
viewModel.selection.observe(viewLifecycleOwner) { value ->
    if (rangeView.selection != value) {
        rangeView.setSelection(value, animate = false)
    }
}

rangeView.setOnSelectionChangeListener { _, value, fromUser ->
    if (fromUser && viewModel.selection.value != value) {
        viewModel.setSelection(value)
    }
}
```

监听器持有 Fragment/Adapter 时，调用方应在对应生命周期清空。组件自身也不能把短生命周期对象存入单例。

## 4. 测量相关属性与绘制相关属性

属性 setter 应精确表达影响：

```kotlin
var labelTextSizePx: Float = defaultTextSize
    set(value) {
        require(value > 0f)
        if (field == value) return
        field = value
        textPaint.textSize = value
        requestLayout() // 文本可能改变期望尺寸
        invalidate()
    }

var indicatorColor: Int = Color.BLUE
    set(value) {
        if (field == value) return
        field = value
        indicatorPaint.color = value
        invalidate() // 只影响像素
    }
```

如果一次配置会改多个字段，提供批量 API，最后只触发一次布局/重绘：

```kotlin
data class RangeAppearance(
    @ColorInt val activeColor: Int,
    @ColorInt val inactiveColor: Int,
    val strokeWidthPx: Float,
)

fun setAppearance(value: RangeAppearance) {
    require(value.strokeWidthPx >= 0f)
    if (appearance == value) return
    val sizeChanged = appearance.strokeWidthPx != value.strokeWidthPx
    appearance = value
    updatePaints(value)
    if (sizeChanged) requestLayout()
    invalidate()
}
```

## 5. Drawable state 与业务状态

`pressed`、`focused`、`selected`、`enabled` 属于 View drawable state，可交给 `ColorStateList`/StateListDrawable。复杂业务状态（加载、错误、空数据）不应全部硬塞进 `isSelected`。

自定义 drawable state 的示例：

```kotlin
private var hasError = false

fun setErrorVisible(visible: Boolean) {
    if (hasError == visible) return
    hasError = visible
    refreshDrawableState()
}

override fun onCreateDrawableState(extraSpace: Int): IntArray {
    val state = super.onCreateDrawableState(extraSpace + 1)
    if (hasError) mergeDrawableStates(state, STATE_ERROR)
    return state
}

private companion object {
    val STATE_ERROR = intArrayOf(R.attr.state_error)
}
```

`attrs.xml` 中需声明 `<attr name="state_error" format="boolean" />`。只有样式系统确实需要选择器响应此状态时才增加自定义 state，避免状态组合爆炸。

## 6. 线程、幂等与批处理

View API 只能在主线程调用。控件可用 `check(Looper.myLooper() == Looper.getMainLooper())` 在开发期尽早暴露错误，但通常不应悄悄 `post`，因为这会改变调用顺序。

幂等 setter 是性能与双向绑定安全的基础：新旧值相等就立即返回。浮点状态可先量化到合法步长，再比较，避免噪声造成持续重绘。

## 7. 反例：公开可写字段与含糊回调

```kotlin
// 反例：绕过校验、失效和无障碍更新。
var start = 0f
var end = 1f
var listener: ((Float, Float) -> Unit)? = null

// 反例：setter 同时开动画且立刻回调目标值，显示状态与回调状态不一致。
fun setRange(start: Float, end: Float) {
    animateTo(start, end)
    listener?.invoke(start, end)
}
```

改为不可变值对象、私有 setter、统一提交函数，并明确回调报告“当前帧值”还是“最终提交值”。多数业务回调只应报告稳定的逻辑值，动画视觉进度保持内部实现细节。

## 8. 实践检查清单

- [ ] 核心状态由不可变值对象表达并验证不变量。
- [ ] XML、程序设置、恢复和用户输入共用提交路径。
- [ ] setter 幂等，并只触发必要的 layout/draw。
- [ ] 动画策略在 API 上显式可见。
- [ ] 回调语义、频率与 `fromUser` 规则有文档。
- [ ] 双向绑定通过相等判断避免回环。
- [ ] 对外不泄漏可变内部对象。
- [ ] 监听器可清除，调用方按生命周期解除。
- [ ] View API 只从主线程调用。

## 小结

可维护的控件 API 围绕状态不变量建立：所有输入统一校验和提交，绘制与语义读取同一事实源，事件只通知真实变化。显式动画策略、幂等 setter 与不可变快照，会显著降低绑定、恢复和测试中的偶发问题。

## 延伸阅读

- [Android Developers：Create custom view components](https://developer.android.com/develop/ui/views/layout/custom-views/create-view)
- [View drawable state API](https://developer.android.com/reference/android/view/View#onCreateDrawableState(int))
- [ColorStateList state specifications](https://developer.android.com/reference/android/content/res/ColorStateList)
- [Android accessibility principles](https://developer.android.com/guide/topics/ui/accessibility/principles)
- [LiveData overview](https://developer.android.com/topic/libraries/architecture/livedata)
