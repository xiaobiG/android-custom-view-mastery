# 实例状态保存与恢复

## 学习目标

- 区分实例状态、业务持久化状态与可重建派生状态。
- 使用 `View.BaseSavedState` 和 Parcelable 保存自定义 View 状态。
- 正确保存/恢复父类状态，兼容进程重建和布局重新创建。
- 处理 View ID、动态层级、动画中间态与版本演进。

## 1. 应该保存什么

View 实例状态（instance state）用于短期重建，例如旋转、系统回收进程后恢复界面。它不是数据库，也不是跨设备持久化方案。

```text
source-of-truth business data ----> ViewModel / repository / SavedStateHandle
         |
         v
logical UI state -----------------> View.BaseSavedState
         |
         +-- selected index, user-entered value, expanded state
         x-- Paint, RectF, bitmap cache, animator, listener
                 (derived/runtime objects: rebuild them)
```

只保存恢复后无法从输入重新推导、且用户能感知的少量逻辑状态。像素坐标通常依赖当前尺寸，应保存比例、索引或领域值。

## 2. BaseSavedState 的标准实现

以下示例不依赖 `@Parcelize`，清楚展示 Parcelable 契约：

```kotlin
class StepCounterView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    var value: Int = 0
        private set
    private var isExpanded: Boolean = false

    override fun onSaveInstanceState(): Parcelable {
        val superState = super.onSaveInstanceState()
        return SavedState(superState).also { state ->
            state.value = value
            state.isExpanded = isExpanded
        }
    }

    override fun onRestoreInstanceState(state: Parcelable?) {
        if (state !is SavedState) {
            super.onRestoreInstanceState(state)
            return
        }
        super.onRestoreInstanceState(state.superState)
        value = state.value.coerceIn(minValue, maxValue)
        isExpanded = state.isExpanded
        updatePaintsAndSemantics()
        requestLayout()
        invalidate()
    }

    private class SavedState : BaseSavedState {
        var value: Int = 0
        var isExpanded: Boolean = false

        constructor(superState: Parcelable?) : super(superState)

        private constructor(source: Parcel, loader: ClassLoader?) : super(source, loader) {
            value = source.readInt()
            isExpanded = source.readInt() != 0
        }

        override fun writeToParcel(out: Parcel, flags: Int) {
            super.writeToParcel(out, flags)
            out.writeInt(value)
            out.writeInt(if (isExpanded) 1 else 0)
        }

        companion object CREATOR : Parcelable.ClassLoaderCreator<SavedState> {
            override fun createFromParcel(source: Parcel): SavedState =
                SavedState(source, null)

            override fun createFromParcel(
                source: Parcel,
                loader: ClassLoader?,
            ): SavedState = SavedState(source, loader)

            override fun newArray(size: Int): Array<SavedState?> =
                arrayOfNulls(size)
        }
    }

    private val minValue = 0
    private val maxValue = 100
    private fun updatePaintsAndSemantics() = Unit
}
```

关键点：

1. `onSaveInstanceState()` 总是先取得 `superState`。
2. 写入和读取顺序必须完全一致；`ClassLoaderCreator` 要把 loader 传给父状态读取。之所以需要
   带 loader 的 `createFromParcel(source, loader)`：进程被系统回收重建时，类可能由非默认
   `ClassLoader` 加载（如动态特性模块、Instant Run 类路径），父类内部字段的类类型解析需要
   正确的 loader；只实现普通 `Creator` 时框架退化为默认 loader，复杂场景可能解析失败。
3. 非自家状态类型要原样交给 `super`。
4. 恢复时先恢复父类，再提交自定义字段。
5. 不在恢复时播放入场动画或触发业务监听器，除非 API 明确要求。

> **注意**
> View 必须有稳定且非 `NO_ID` 的 ID，父层级才可按 ID 保存和匹配状态。XML 中使用 `android:id`；动态 View 使用 `View.generateViewId()` 并确保重建时结构/ID 可对应。

### 2.1 恢复时机与 setSaveEnabled

`onSaveInstanceState()` 在 Activity 的保存阶段（通常在 `onStop` 附近）随层级自上而下调用；
恢复则在 `onRestoreInstanceState()` 中按 View ID 分发，先于 Activity 的 `onStart`。因此恢复
回调里不应假设布局已完成测量——像素几何请推迟到 `onSizeChanged` 或绘制阶段再计算。

`setSaveEnabled(false)`（XML：`android:saveEnabled`）可关闭某个 View 的状态保存：它的
`onSaveInstanceState()` 会直接返回 `null`，父层级保存时也会跳过该 View。适用场景是内容完全
由父级或 ViewModel 驱动的叶子控件（如纯展示的图标），避免无意义地保存与分发；但要小心：
动态生成、依赖 ID 匹配的 View 若被关闭保存，重建后可能丢失交互值。默认 `saveEnabled=true`，
不要为“省一点 Bundle”而全局关闭。

## 3. Kotlin Parcelize 版本

启用 `kotlin-parcelize` 插件后可减少样板：

```kotlin
@Parcelize
private class SavedState(
    val parentState: Parcelable?,
    val value: Int,
    val expanded: Boolean,
) : View.BaseSavedState(parentState), Parcelable
```

然而继承 Parcelable 基类时，不同 Kotlin/AGP 组合的支持细节需通过工程构建验证。库组件若重视跨版本可控性，可保留显式 `CREATOR`。无论采用哪种方式，都要做真实 Parcel round-trip 测试。

## 4. 恢复要走“无副作用提交”

公开 setter 可能通知监听器、写分析日志或启动动画。恢复应使用内部路径：

```kotlin
private fun applyValue(
    newValue: Int,
    notify: Boolean,
    animate: Boolean,
) {
    val normalized = newValue.coerceIn(minValue, maxValue)
    if (value == normalized) return
    value = normalized
    if (animate) animateVisualTo(normalized) else syncVisualImmediately()
    updateContentDescription()
    invalidate()
    if (notify) listener?.onValueChanged(this, normalized, false)
}

override fun onRestoreInstanceState(state: Parcelable?) {
    if (state !is SavedState) {
        super.onRestoreInstanceState(state)
        return
    }
    super.onRestoreInstanceState(state.superState)
    applyValue(state.value, notify = false, animate = false)
}
```

恢复发生时尺寸可能仍为 0。不要立即把逻辑值换算成最终像素；把值保存下来，在 `onSizeChanged` 或绘制前根据当前尺寸计算几何。

## 5. 动画运行中保存哪个状态

需要预先定义语义：

- **业务值已提交，动画只是视觉过渡**：保存目标业务值，恢复时直接显示终态。
- **动画过程就是用户可编辑状态**：保存当前逻辑值，但通常不保存 animator 的播放时间。
- **流程型动画必须续播**：把阶段和进度放到更高层状态机，而非试图序列化 Animator。

多数自定义控件选择第一种，恢复稳定且不会因时长缩放不同而错乱。

## 6. 状态大小与兼容性

Bundle/Parcel 通过 Binder 传递时有大小限制；View 状态只放小型值。Bitmap、大列表、Drawable、Context 和回调都不应进入 SavedState。

库升级后字段可能变化。Parcelable 不是长期磁盘格式，通常只需兼容同一安装版本的短期重建；但动态特性或热更新可能放大差异。可以增加 `version` 字段并在读取时采取默认值，但 Parcel 本身没有字段名，写读协议仍要同步维护。

## 7. 反例：丢失父类状态

```kotlin
// 反例：父类的 enabled、scroll 等可保存状态链被截断。
override fun onSaveInstanceState(): Parcelable = Bundle().apply {
    putInt("value", value)
}

override fun onRestoreInstanceState(state: Parcelable?) {
    value = (state as Bundle).getInt("value")
    // 没有 super.onRestoreInstanceState(...)
}
```

另一个反例是把 `context`、listener 或正在运行的 animator 写入 Parcel：它们要么不可序列化，要么把生命周期错误固化为状态。

## 8. 测试策略

```kotlin
@Test
fun savedState_parcelRoundTrip_preservesFields() {
    val original = createSavedState(value = 42, expanded = true)
    val parcel = Parcel.obtain()
    try {
        original.writeToParcel(parcel, 0)
        parcel.setDataPosition(0)
        val restored = SavedState.CREATOR.createFromParcel(parcel)
        assertThat(restored.value).isEqualTo(42)
        assertThat(restored.isExpanded).isTrue()
    } finally {
        parcel.recycle()
    }
}
```

再使用 ActivityScenario 的 `recreate()` 做集成测试，确认 View 有 ID、父层级参与保存，且恢复不产生额外监听事件。

## 9. 实践检查清单

- [ ] 只保存小型、用户可感知且不可轻易推导的逻辑状态。
- [ ] `superState` 被完整保存并优先恢复。
- [ ] Parcel 写入/读取类型和顺序一一对应。
- [ ] 非自家 SavedState 会交给父类处理。
- [ ] View 有稳定 ID，动态层级重建后能对应。
- [ ] 恢复不启动装饰动画、不重复发送业务事件。
- [ ] 几何缓存从新尺寸重新计算，不保存旧像素。
- [ ] 有 Parcel round-trip 与 Activity recreate 测试。

## 小结

BaseSavedState 是 View 状态链的一环，而不是通用持久化容器。保存最小逻辑状态、保留父类 Parcelable、以无副作用路径恢复，并让几何与运行时对象重新构建，才能正确应对旋转和进程重建。

## 延伸阅读

- [View.onSaveInstanceState API](https://developer.android.com/reference/android/view/View#onSaveInstanceState())
- [View.BaseSavedState API](https://developer.android.com/reference/android/view/View.BaseSavedState)
- [Parcelable API](https://developer.android.com/reference/android/os/Parcelable)
- [Parcelize](https://developer.android.com/kotlin/parcelize)
- [Save UI states](https://developer.android.com/topic/libraries/architecture/saving-states)
