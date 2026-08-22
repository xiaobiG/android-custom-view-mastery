# 自定义属性与主题

## 学习目标

- 使用 `declare-styleable` 定义稳定、可发现的 XML 属性。
- 理解直接属性、style、`defStyleAttr`、`defStyleRes` 与主题的优先级。
- 正确读取并回收 `TypedArray`，保留颜色与 Drawable 的主题语义。
- 设计能被应用主题覆盖、又有组件默认值兜底的样式 API。

## 1. 属性、样式与主题分别解决什么

属性（attribute）是一个命名输入；样式（style）是一组属性值；主题（theme）是作用于一棵 Context/View 树的样式环境。一个可复用组件不应把颜色、尺寸散落为构造器常量，而应建立清晰的解析链。

```text
XML direct attribute        highest priority
        |
XML style
        |
defStyleAttr -> theme points to component style
        |
defStyleRes                  library fallback
        |
theme / platform defaults   lower priority
```

`Context.obtainStyledAttributes(attrs, styleable, defStyleAttr, defStyleRes)` 会按 Android 资源解析规则合并这些来源。`defStyleAttr` 是“主题里的属性 ID”，而不是 style 资源 ID；`defStyleRes` 才是最终备用 style。

## 2. 声明组件属性

`res/values/attrs.xml`：

```xml
<resources>
    <attr name="meterViewStyle" format="reference" />

    <declare-styleable name="MeterView">
        <attr name="meterProgress" format="float" />
        <attr name="meterTrackColor" format="color" />
        <attr name="meterIndicatorColor" format="color" />
        <attr name="meterThickness" format="dimension" />
        <attr name="meterShowLabel" format="boolean" />
        <attr name="meterLabelTextAppearance" format="reference" />
        <attr name="meterIcon" format="reference" />
    </declare-styleable>
</resources>
```

属性名应带组件或库前缀，避免应用合并资源时发生语义冲突。枚举/flag 适合有限选项，布尔值适合正交开关，不要用无文档整数承载模式。

默认样式：

```xml
<style name="Widget.Example.MeterView">
    <item name="meterTrackColor">?attr/colorOutline</item>
    <item name="meterIndicatorColor">?attr/colorPrimary</item>
    <item name="meterThickness">4dp</item>
    <item name="meterShowLabel">true</item>
    <item name="meterLabelTextAppearance">?attr/textAppearanceBodyMedium</item>
</style>

<style name="Theme.Example" parent="Theme.Material3.DayNight.NoActionBar">
    <item name="meterViewStyle">@style/Widget.Example.MeterView</item>
</style>
```

## 3. 四参数构造链

```kotlin
class MeterView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = R.attr.meterViewStyle,
    defStyleRes: Int = R.style.Widget_Example_MeterView,
) : View(context, attrs, defStyleAttr, defStyleRes) {

    private var progress = 0f
    private var trackColor = Color.GRAY
    private var indicatorColor = Color.BLUE
    private var thicknessPx = 0f
    private var showLabel = true

    init {
        context.obtainStyledAttributes(
            attrs,
            R.styleable.MeterView,
            defStyleAttr,
            defStyleRes,
        ).use { a ->
            progress = a.getFloat(R.styleable.MeterView_meterProgress, 0f)
                .coerceIn(0f, 1f)
            trackColor = a.getColor(
                R.styleable.MeterView_meterTrackColor,
                Color.GRAY,
            )
            indicatorColor = a.getColor(
                R.styleable.MeterView_meterIndicatorColor,
                Color.BLUE,
            )
            thicknessPx = a.getDimension(
                R.styleable.MeterView_meterThickness,
                4f * resources.displayMetrics.density,
            )
            showLabel = a.getBoolean(R.styleable.MeterView_meterShowLabel, true)
        }
    }
}
```

示例中的 `use` 是 AndroidX Core KTX 的 `androidx.core.content.res.use` 扩展，它会在 block 结束后调用 `recycle()`；未引入该扩展时，使用 `try/finally { a.recycle() }`。不要依赖平台 API 级别碰巧提供的 `AutoCloseable` 实现，无论哪种形式都必须回收。

> **注意**
> 自定义 View 若只声明三参数构造器，仍可在构造器内部用四参数的 `obtainStyledAttributes` 获得 `defStyleRes` 兜底。API 21+ 的 `View(context, attrs, defStyleAttr, defStyleRes)` 可直接把默认样式传给父类。

## 4. Drawable、ColorStateList 与 TextAppearance

如果属性允许状态色，不要用 `getColor()` 提前压扁为单色：

```kotlin
private var indicatorColors: ColorStateList = ColorStateList.valueOf(Color.BLUE)
private var icon: Drawable? = null

context.obtainStyledAttributes(
    attrs,
    R.styleable.MeterView,
    defStyleAttr,
    defStyleRes,
).use { a ->
    indicatorColors = a.getColorStateList(
        R.styleable.MeterView_meterIndicatorColor,
    ) ?: ColorStateList.valueOf(Color.BLUE)
    icon = a.getDrawable(R.styleable.MeterView_meterIcon)?.mutate()
}

override fun drawableStateChanged() {
    super.drawableStateChanged()
    val newColor = indicatorColors.getColorForState(
        drawableState,
        indicatorColors.defaultColor,
    )
    if (paint.color != newColor) {
        paint.color = newColor
        invalidate()
    }
    icon?.let { drawable ->
        if (drawable.isStateful) drawable.state = drawableState
    }
}
```

若要让自定义 Drawable 接收状态，还应覆盖 `verifyDrawable`，在尺寸变化时设置 bounds，并在不再使用时解除 callback。文本样式应优先用 TextAppearance 资源与 `TextPaint`/`TextView` 支持库读取，避免只暴露若干零散字体属性后却无法表达 locale、font family 等语义。

## 5. 运行时主题覆盖

`ContextThemeWrapper` 可以为局部子树提供主题覆盖；组件读取资源时必须使用自己的 `context`，而不是 application context：

```kotlin
val themedContext = ContextThemeWrapper(context, R.style.ThemeOverlay_Example_Compact)
val meter = MeterView(themedContext)
```

主题在 View 构造时被解析。切换主题后，已有 View 不会自动重新执行构造器；通常由 Activity recreation 重建视图，或组件提供明确的重新应用接口。

## 6. 反例：跳过默认样式链

```kotlin
// 反例：只看 XML，库默认 style 与应用主题覆盖都失效。
val a = context.obtainStyledAttributes(attrs, R.styleable.MeterView)
trackColor = a.getColor(R.styleable.MeterView_meterTrackColor, Color.GRAY)
// 忘记 recycle()
```

另一个反例是把 `R.style.Widget_Example_MeterView` 误传给 `defStyleAttr`。它们都是 Int，编译器无法阻止，但解析语义完全不同。

## 7. 实践检查清单

- [ ] 属性名有稳定前缀，类型与语义清晰。
- [ ] 主题声明组件 style 属性，如 `meterViewStyle`。
- [ ] `defStyleAttr` 传 attr，`defStyleRes` 传 style。
- [ ] 通过四参数 obtainStyledAttributes 读取完整优先级链。
- [ ] 每个 TypedArray 都会 `recycle()` 或安全 `use`。
- [ ] 状态色保留为 `ColorStateList`，Drawable 正确传播状态。
- [ ] 资源读取使用 View 的 themed context。
- [ ] 直接 XML 属性能够覆盖 style 与组件默认值。

## 小结

良好的样式系统不是“多暴露几个 XML 参数”，而是建立属性、组件默认 style 与应用主题之间的契约。`defStyleAttr` 给应用全局定制入口，`defStyleRes` 给库可靠兜底，直接属性则保留实例级最高优先级。

## 延伸阅读

- [Android Developers：Create a custom view style](https://developer.android.com/develop/ui/views/layout/custom-views/create-view#customattr)
- [Applying styles and themes](https://developer.android.com/develop/ui/views/theming/themes)
- [Resources.Theme.obtainStyledAttributes API](https://developer.android.com/reference/android/content/res/Resources.Theme#obtainStyledAttributes(android.util.AttributeSet,int[],int,int))
- [ColorStateList API](https://developer.android.com/reference/android/content/res/ColorStateList)
- [ContextThemeWrapper API](https://developer.android.com/reference/android/view/ContextThemeWrapper)
