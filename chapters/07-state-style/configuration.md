# RTL、字体缩放与配置变化

## 学习目标

- 让自定义控件在从右到左（RTL）布局方向下保持逻辑与视觉一致。
- 正确响应 `fontScale`，避免把 sp 当作固定像素或重复缩放。
- 使用主题资源支持 night mode，而不是缓存旧配置颜色。
- 在 configuration、尺寸与 locale 变化时重建必要缓存并取消失效动画。

## 1. 配置变化影响的是坐标、资源与语义

自定义 View 常见的配置依赖不只屏幕方向：

```text
Configuration changes
   |
   +-- layoutDirection (LTR / RTL) ---> logical start/end mapping
   +-- fontScale / density ----------> text metrics, desired size
   +-- uiMode night -----------------> colors, drawables, theme
   +-- locale -----------------------> text, digits, shaping
   +-- screen size ------------------> geometry, breakpoints
                 |
                 v
       cancel stale animation -> rebuild cache -> layout/draw
```

首要原则是保存逻辑状态，几何与资源从当前 `resources`、theme 和尺寸推导。

## 2. RTL：使用 start/end，不是 left/right 猜测

方向无关的进度可映射到视觉 X：

```kotlin
private fun xForProgress(progress: Float): Float {
    val p = progress.coerceIn(0f, 1f)
    val left = paddingLeft.toFloat()
    val right = (width - paddingRight).toFloat()
    return if (layoutDirection == LAYOUT_DIRECTION_RTL) {
        right - p * (right - left)
    } else {
        left + p * (right - left)
    }
}
```

`progress = 0` 对应逻辑 start；在 RTL 中 start 位于右侧。若业务本身是物理方向（例如罗盘的西/东、音频波形时间轴按产品规定不镜像），则不要盲目翻转。先区分“逻辑 start/end”与“物理 left/right”。

自定义 Drawable 要传递布局方向：

```kotlin
private fun updateIconDirection() {
    icon?.let { DrawableCompat.setLayoutDirection(it, layoutDirection) }
}

override fun onRtlPropertiesChanged(layoutDirection: Int) {
    super.onRtlPropertiesChanged(layoutDirection)
    runningAnimator?.cancel()
    updateIconDirection()
    geometryDirty = true
    requestLayout()
    invalidate()
}
```

XML 与布局参数优先使用 `paddingStart`/`paddingEnd`、`marginStart`/`marginEnd`。Canvas 本身不会自动镜像你手写的坐标。

> **注意**
> 文本对齐与布局方向不是同一概念。数字、URL 或混合双向文本可能有自己的段落方向；优先使用 Android 文本布局与 BidiFormatter，不要手工反转字符串。

## 3. fontScale：sp 只转换一次

文本尺寸通常来自 `sp` 资源或 TextAppearance，资源系统会结合 `scaledDensity` 转为像素：

```kotlin
private fun spToPx(sp: Float): Float =
    TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_SP,
        sp,
        resources.displayMetrics,
    )

private fun rebuildTextMetrics() {
    textPaint.textSize = resources.getDimension(R.dimen.meter_label_text_size)
    val metrics = textPaint.fontMetrics
    labelHeightPx = metrics.descent - metrics.ascent
}
```

如果 `R.dimen.meter_label_text_size` 定义为 `14sp`，`getDimension()` 已返回 px，不能再乘 `scaledDensity`。更好的组件 API 是接受 px（与 Android View API 一致）或 TextAppearance，并在名字/注解中写清单位。

字体缩放会改变 `FontMetrics`、换行和期望尺寸。因此相关变化后要清除 `StaticLayout`、文字宽度等缓存并 `requestLayout()`，而不仅仅 `invalidate()`。

> **无障碍提示**
> 不要为了保持控件高度而强行忽略大字体。允许多行、增高或提供替代布局；在常见的大字体设置下验证文字不裁切、不重叠。

## 4. Night mode：从主题解析，不硬编码

颜色应来自 day/night 资源或主题属性：

```xml
<!-- values/colors.xml -->
<color name="meter_track">#33000000</color>

<!-- values-night/colors.xml -->
<color name="meter_track">#33FFFFFF</color>
```

```kotlin
@ColorInt
private fun resolveThemeColor(@AttrRes attr: Int): Int {
    val value = TypedValue()
    check(context.theme.resolveAttribute(attr, value, true)) {
        "Required theme attribute is missing: $attr"
    }
    return if (value.resourceId != 0) {
        ContextCompat.getColor(context, value.resourceId)
    } else {
        value.data
    }
}
```

大多数应用切换 night mode 时会重建 Activity，构造器重新读取主题。如果应用自行处理 `uiMode` 而不重建，就必须显式重新解析主题属性、替换 Drawable/ColorStateList 并失效；仅调用 `invalidate()` 不会让缓存的颜色自动变化。

## 5. configuration 变化的处理边界

View 可覆盖：

```kotlin
override fun onConfigurationChanged(newConfig: Configuration) {
    super.onConfigurationChanged(newConfig)
    runningAnimator?.cancel()
    rebuildConfigurationDependentResources()
    geometryDirty = true
    requestLayout()
    invalidate()
}
```

但这个回调不能替代 Activity 的配置管理：若 Activity 被系统重建，旧 View 会 detach，新 View 由新 Context 构造；若 Activity 声明自己处理配置，才更依赖运行时刷新。

按依赖分类缓存：

| 缓存 | 失效条件 |
|---|---|
| Path/Rect 几何 | size、padding、layoutDirection |
| 文本宽度/StaticLayout | text、locale、fontScale、typeface、width |
| 主题颜色/Drawable | theme、uiMode、drawable state |
| dp 转 px 的常量 | density |

不要比较整个 `Configuration` 后全部重建；记录真正依赖的值，精确失效。

## 6. Locale 与格式化

显示数字和日期时使用当前 locale：

```kotlin
private fun formatPercent(value: Float): String {
    val formatter = NumberFormat.getPercentInstance(resources.configuration.locales[0])
    return formatter.format(value.coerceIn(0f, 1f))
}
```

频繁绘制时不要在 `onDraw()` 每帧创建 formatter；在 locale 或配置变化时重建缓存。API 24 以下访问 locale 需兼容分支，现代项目可使用 AndroidX `ConfigurationCompat.getLocales(resources.configuration)` 统一读取。

## 7. 尺寸变化与动画坐标

从旧宽度动画到旧像素终点，在旋转或分屏调整后会落错位置。正确做法是动画逻辑值：

```kotlin
private var animatedProgress = 0f

private fun setAnimatedProgress(value: Float) {
    animatedProgress = value.coerceIn(0f, 1f)
    invalidate()
}

override fun onDraw(canvas: Canvas) {
    val x = xForProgress(animatedProgress) // 每次按当前尺寸映射
    canvas.drawCircle(x, centerY, thumbRadius, thumbPaint)
}
```

若动画内部保存的 evaluator 仍依赖旧几何，`onSizeChanged`/`onRtlPropertiesChanged` 时取消并用当前逻辑状态重新启动或直接提交终态。

## 8. 反例：构造时缓存所有像素与颜色

```kotlin
// 反例：后续 fontScale/density/theme 改变后全部过期。
private val textSize = 14f * resources.displayMetrics.density
private val color = Color.BLACK
private val startX = paddingLeft.toFloat()

// 反例：为 RTL 反转文字，破坏 Unicode 双向算法。
val shown = if (isRtl) label.reversed() else label
```

`14sp` 应使用 scaled density/资源系统；主题颜色应从 themed context 解析；几何应在尺寸和 padding 已知后计算；文本方向交给文本引擎。

## 9. 测试矩阵

至少覆盖：

```text
LTR + day + 1.0 fontScale
RTL + day + 1.0 fontScale
LTR + night + large font
RTL + night + large font
portrait <-> landscape / split screen resize
locale with Latin digits <-> locale with different shaping
```

用截图测试检查镜像、裁切和对比度，用行为测试检查逻辑 start/end 与触摸命中。配置测试不只看“没有崩溃”，还要断言状态保持且旧动画/缓存没有继续写入。

## 10. 实践检查清单

- [ ] 区分逻辑 start/end 与物理 left/right。
- [ ] 手写 Canvas 坐标在需要时显式镜像，字符串不手工反转。
- [ ] sp 通过 scaledDensity/资源系统只转换一次。
- [ ] 大字体会触发布局重算，文本不裁切。
- [ ] day/night 颜色来自主题或限定资源，而非硬编码。
- [ ] 不重建 Activity 时会主动重新解析主题资源。
- [ ] 缓存按 size、RTL、locale、fontScale、density、uiMode 精确失效。
- [ ] 配置变化时取消依赖旧坐标系的动画。
- [ ] 测试矩阵包含 RTL、night、大字体和窗口尺寸变化。

## 小结

配置适配的核心是将逻辑状态与当前环境下的呈现分离：状态保存进度和选择，几何根据尺寸与方向计算，文字根据 locale/fontScale 排版，颜色根据主题解析。如此才能在 RTL、夜间模式、大字体和窗口变化中保持一致行为。

## 延伸阅读

- [Android Developers：Support different languages and cultures](https://developer.android.com/training/basics/supporting-devices/languages)
- [Android Developers：Support RTL](https://developer.android.com/training/basics/supporting-devices/languages#SupportRtl)
- [App resources overview and qualifiers](https://developer.android.com/guide/topics/resources/providing-resources)
- [Dark theme](https://developer.android.com/develop/ui/views/theming/darktheme)
- [Configuration API](https://developer.android.com/reference/android/content/res/Configuration)
- [BidiFormatter API](https://developer.android.com/reference/androidx/core/text/BidiFormatter)
