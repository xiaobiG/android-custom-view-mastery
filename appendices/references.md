# 参考资料

以下链接以 Android Developers、AndroidX API Reference 与 AOSP 源码为主，按主题分类。API 细节、版本差异和兼容性应以链接中的当前官方文档与项目实际 `compileSdk`/依赖版本为准。

## 1. View 生命周期、测量与布局

- [Custom View：Create a view class](https://developer.android.com/develop/ui/views/layout/custom-views/create-view)
- [Create custom view components](https://developer.android.com/develop/ui/views/layout/custom-views/custom-components)
- [View API Reference](https://developer.android.com/reference/android/view/View)
- [ViewGroup API Reference](https://developer.android.com/reference/android/view/ViewGroup)
- [View.MeasureSpec API Reference](https://developer.android.com/reference/android/view/View.MeasureSpec)
- [ViewGroup.LayoutParams API Reference](https://developer.android.com/reference/android/view/ViewGroup.LayoutParams)
- [ViewGroup.MarginLayoutParams API Reference](https://developer.android.com/reference/android/view/ViewGroup.MarginLayoutParams)
- [AOSP View.java](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/View.java)
- [AOSP ViewGroup.java](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/ViewGroup.java)

## 2. Canvas、几何与文字

- [Custom View：Custom drawing](https://developer.android.com/develop/ui/views/layout/custom-views/custom-drawing)
- [Canvas API Reference](https://developer.android.com/reference/android/graphics/Canvas)
- [Paint API Reference](https://developer.android.com/reference/android/graphics/Paint)
- [Path API Reference](https://developer.android.com/reference/android/graphics/Path)
- [PathMeasure API Reference](https://developer.android.com/reference/android/graphics/PathMeasure)
- [Matrix API Reference](https://developer.android.com/reference/android/graphics/Matrix)
- [RectF API Reference](https://developer.android.com/reference/android/graphics/RectF)
- [Bitmap API Reference](https://developer.android.com/reference/android/graphics/Bitmap)
- [Drawable API Reference](https://developer.android.com/reference/android/graphics/drawable/Drawable)
- [StaticLayout API Reference](https://developer.android.com/reference/android/text/StaticLayout)
- [TextPaint API Reference](https://developer.android.com/reference/android/text/TextPaint)
- [Hardware acceleration](https://developer.android.com/develop/ui/views/graphics/hardware-accel)

## 3. 输入、事件与手势

- [Use touch gestures](https://developer.android.com/develop/ui/views/touch-and-input/gestures)
- [Make a custom view interactive](https://developer.android.com/develop/ui/views/layout/custom-views/making-interactive)
- [Manage touch events in a ViewGroup](https://developer.android.com/develop/ui/views/touch-and-input/gestures/viewgroup)
- [Track touch and pointer movements](https://developer.android.com/develop/ui/views/touch-and-input/gestures/movement)
- [Drag and scale](https://developer.android.com/develop/ui/views/touch-and-input/gestures/scale)
- [MotionEvent API Reference](https://developer.android.com/reference/android/view/MotionEvent)
- [ViewConfiguration API Reference](https://developer.android.com/reference/android/view/ViewConfiguration)
- [GestureDetector API Reference](https://developer.android.com/reference/android/view/GestureDetector)
- [ScaleGestureDetector API Reference](https://developer.android.com/reference/android/view/ScaleGestureDetector)
- [VelocityTracker API Reference](https://developer.android.com/reference/android/view/VelocityTracker)
- [OverScroller API Reference](https://developer.android.com/reference/android/widget/OverScroller)
- [EdgeEffect API Reference](https://developer.android.com/reference/android/widget/EdgeEffect)
- [KeyEvent API Reference](https://developer.android.com/reference/android/view/KeyEvent)
- [AOSP MotionEvent.java](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/MotionEvent.java)
- [AOSP ViewConfiguration.java](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/ViewConfiguration.java)

## 4. AndroidX 兼容与嵌套滚动

- [ViewCompat API Reference](https://developer.android.com/reference/androidx/core/view/ViewCompat)
- [NestedScrollingChild3 API Reference](https://developer.android.com/reference/androidx/core/view/NestedScrollingChild3)
- [NestedScrollingParent3 API Reference](https://developer.android.com/reference/androidx/core/view/NestedScrollingParent3)
- [NestedScrollingChildHelper API Reference](https://developer.android.com/reference/androidx/core/view/NestedScrollingChildHelper)
- [NestedScrollingParentHelper API Reference](https://developer.android.com/reference/androidx/core/view/NestedScrollingParentHelper)
- [WindowInsetsCompat API Reference](https://developer.android.com/reference/androidx/core/view/WindowInsetsCompat)
- [GestureDetectorCompat API Reference](https://developer.android.com/reference/androidx/core/view/GestureDetectorCompat)

## 5. 动画、帧与物理

- [Property animation overview](https://developer.android.com/develop/ui/views/animations/prop-animation)
- [ValueAnimator API Reference](https://developer.android.com/reference/android/animation/ValueAnimator)
- [AnimatorSet API Reference](https://developer.android.com/reference/android/animation/AnimatorSet)
- [TimeInterpolator API Reference](https://developer.android.com/reference/android/animation/TimeInterpolator)
- [Choreographer API Reference](https://developer.android.com/reference/android/view/Choreographer)
- [DynamicAnimation API Reference](https://developer.android.com/reference/androidx/dynamicanimation/animation/DynamicAnimation)
- [SpringAnimation API Reference](https://developer.android.com/reference/androidx/dynamicanimation/animation/SpringAnimation)
- [FlingAnimation API Reference](https://developer.android.com/reference/androidx/dynamicanimation/animation/FlingAnimation)
- [AOSP Choreographer.java](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/Choreographer.java)

## 6. 性能分析与渲染质量

- [Optimize a custom view](https://developer.android.com/develop/ui/views/layout/custom-views/optimizing-view)
- [Slow rendering / Android vitals](https://developer.android.com/topic/performance/vitals/render)
- [Inspect UI performance with GPU rendering](https://developer.android.com/topic/performance/rendering/inspect-gpu-rendering)
- [Perfetto documentation](https://perfetto.dev/docs/)
- [System tracing on Android](https://developer.android.com/topic/performance/tracing)
- [Macrobenchmark overview](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview)
- [JankStats](https://developer.android.com/topic/performance/jankstats)
- [Profile GPU rendering](https://developer.android.com/topic/performance/rendering/profile-gpu)
- [App startup and runtime performance best practices](https://developer.android.com/topic/performance)
- [AOSP HWUI renderer source](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/libs/hwui/)

> **注意**：刷新率决定理论帧间隔；不要把 16 ms 当作所有设备和所有帧的固定预算。以 FrameTimeline/Perfetto 的实际 deadline 与 jank 分类为准。

## 7. 状态、样式、RTL 与配置

- [Create a custom view class：Apply custom attributes](https://developer.android.com/develop/ui/views/layout/custom-views/create-view#customattr)
- [Saving UI states](https://developer.android.com/topic/libraries/architecture/saving-states)
- [View.BaseSavedState API Reference](https://developer.android.com/reference/android/view/View.BaseSavedState)
- [Support different languages and cultures](https://developer.android.com/training/basics/supporting-devices/languages)
- [Support different pixel densities](https://developer.android.com/training/multiscreen/screendensities)
- [Support different screen sizes](https://developer.android.com/guide/practices/screens_support)
- [Configuration API Reference](https://developer.android.com/reference/android/content/res/Configuration)
- [TypedArray API Reference](https://developer.android.com/reference/android/content/res/TypedArray)

## 8. 无障碍

- [Make apps more accessible](https://developer.android.com/guide/topics/ui/accessibility/apps)
- [Create a view class：Design for accessibility](https://developer.android.com/develop/ui/views/layout/custom-views/create-view#accessibility)
- [Develop custom accessibility services and views](https://developer.android.com/guide/topics/ui/accessibility/principles)
- [Test your app's accessibility](https://developer.android.com/guide/topics/ui/accessibility/testing)
- [ExploreByTouchHelper API Reference](https://developer.android.com/reference/androidx/customview/widget/ExploreByTouchHelper)
- [AccessibilityNodeInfoCompat API Reference](https://developer.android.com/reference/androidx/core/view/accessibility/AccessibilityNodeInfoCompat)
- [AccessibilityDelegateCompat API Reference](https://developer.android.com/reference/androidx/core/view/AccessibilityDelegateCompat)
- [AccessibilityEvent API Reference](https://developer.android.com/reference/android/view/accessibility/AccessibilityEvent)
- [TouchDelegate API Reference](https://developer.android.com/reference/android/view/TouchDelegate)
- [Espresso accessibility checking](https://developer.android.com/training/testing/espresso/accessibility-checking)

## 9. 测试

- [Test apps on Android](https://developer.android.com/training/testing)
- [Espresso](https://developer.android.com/training/testing/espresso)
- [Espresso basics](https://developer.android.com/training/testing/espresso/basics)
- [Espresso idling resources](https://developer.android.com/training/testing/espresso/idling-resource)
- [Espresso cheat sheet](https://developer.android.com/training/testing/espresso/cheat-sheet)
- [androidx.test API Reference](https://developer.android.com/reference/androidx/test/package-summary)
- [ActivityScenario API Reference](https://developer.android.com/reference/androidx/test/core/app/ActivityScenario)
- [UI Automator](https://developer.android.com/training/testing/other-components/ui-automator)
- [Test your app's activities](https://developer.android.com/guide/components/activities/testing)
- [Compose Preview screenshot testing](https://developer.android.com/studio/preview/compose-screenshot-testing)

## 10. Compose 与 View 互操作

- [Views in Compose](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose)
- [Compose in Views](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/compose-in-views)
- [AndroidView API Reference](https://developer.android.com/reference/kotlin/androidx/compose/ui/viewinterop/package-summary)
- [ComposeView API Reference](https://developer.android.com/reference/kotlin/androidx/compose/ui/platform/ComposeView)
- [ViewCompositionStrategy API Reference](https://developer.android.com/reference/kotlin/androidx/compose/ui/platform/ViewCompositionStrategy)

## 11. 阅读源码的方法

1. 先从 Android Developers API 契约确认公开行为与 API level。
2. 再在 AOSP `frameworks/base/core/java/android/view/` 查看 View、ViewGroup、输入和帧调度实现。
3. 图形管线进入 `frameworks/base/libs/hwui/`，但实现细节不是应用可依赖的稳定 API。
4. AndroidX 行为以对应版本源码和 release notes 为准；不要把主分支实现直接当成项目依赖版本。
5. 源码用于解释与调试，发布代码仍应依赖公开 API，不通过反射绑定内部实现。

## 12. 版本与引用原则

- 文中提到常量、返回值、线程或 API level 时，链接到具体 API reference。
- 教程解释“如何做”，API reference 定义“允许依赖什么”，AOSP 解释“当前实现为何如此”。三者用途不同。
- URL 使用稳定主题页、类页或 AOSP 路径，不链接搜索结果页。
- 引入 AndroidX 库时记录实际版本，并查阅对应 [AndroidX release notes](https://developer.android.com/jetpack/androidx/versions)。
- 涉及行为变更时查阅 [Android behavior changes](https://developer.android.com/about/versions) 与目标版本说明。
