# View 树与窗口渲染概览

在 Activity 中调用 `setContentView()` 后，我们看到的是一棵 View 树，但它并不是窗口本身。理解 `Window`、`DecorView`、`ViewRootImpl` 与业务根布局的概念边界，是解释测量起点、重绘上报和窗口生命周期的前提。

## 学习目标

读完本章，你应当能够：

- 区分 Window、DecorView、ViewRootImpl 和应用内容 View；
- 描述一次 View 树遍历从调度到绘制提交的大致路径；
- 解释为什么 ViewRootImpl 不是 View，也不能由应用当作普通节点操作；
- 识别窗口坐标、屏幕坐标和局部坐标的边界；
- 用公开 API 观察树结构，而不依赖内部实现。

## 一、四个容易混淆的角色

### Window：窗口抽象

`Window` 是顶层窗口外观与行为的抽象，Activity 通常使用 `PhoneWindow` 实现。它负责安装内容、窗口特性、背景以及与 WindowManager 的交互入口，但不是屏幕上的一个普通 View。

### DecorView：View 树的顶层 View

`DecorView` 是 `Window` 所持有的顶层 View，通常包含系统装饰相关区域与承载 `android.R.id.content` 的内容容器。应用通过 `setContentView()` 设置的布局位于内容容器内；业务布局根节点通常不等于 DecorView。

### ViewRootImpl：树与窗口系统之间的桥

`ViewRootImpl` 管理一棵已附着 View 树与窗口会话之间的连接，接收窗口尺寸、Insets、输入和 VSync 驱动的遍历请求，并发起 measure/layout/draw。名字里有 View，但它**不是 `View` 的子类**，也不在应用可枚举的 View 树中。

### 业务根 View：应用控制的内容

业务根 View 是布局资源或代码创建的根节点。它受 DecorView 内容区域、窗口 Insets 和父容器约束。应用可以覆盖它及其后代的回调，却不应尝试持有或反射操纵 ViewRootImpl。

```text
Activity
   |
   v
Window (通常是 PhoneWindow，非 View)
   |
   v
DecorView (顶层 View)
   +-- 系统/标题相关容器（因主题与版本而异）
   +-- content 容器: android.R.id.content
          |
          v
       业务根 View

ViewRootImpl (非 View)
   | 连接上面的 DecorView 与 WindowManager/输入/渲染调度
   +---------------------------------------------------->
```

> **注意**：DecorView 的内部子结构并非稳定公共契约。可以依赖 `android.R.id.content` 等公开入口，不要依赖某版本观察到的固定层级索引。

## 二、从添加窗口到首次遍历

Activity 可见过程中，WindowManager 将 DecorView 作为根 View 添加到窗口。ViewRootImpl 建立连接后，请求一次遍历。遍历不是每次请求都立即同步执行；系统会合并请求，在合适的帧时机进入 `performTraversals()` 一类内部流程。

概念上的首次渲染路径如下：

```text
setContentView()
      |
      v
Window 安装业务内容到 DecorView
      |
      v
WindowManager 添加顶层 View
      |
      v
ViewRootImpl 建立窗口连接
      |
      v
scheduleTraversals() -- 与帧调度协作、合并请求
      |
      v
performTraversals()
      |
      +--> measure（若需要）
      +--> layout （若需要）
      +--> draw   （若需要）
      |
      v
渲染管线生成并提交画面
```

`performTraversals()` 是理解源码的锚点，不是应用应直接调用的 API。是否执行某阶段受脏标记、尺寸变化、Insets、可见性等条件影响，不能假设每帧总是完整执行三阶段。

## 三、树遍历为何从根开始

父容器掌握对子元素的约束和位置，因此测量约束从根向下传播；子节点产生测量结果供父节点决策；布局时父级为每个子级调用 `layout()`；绘制时通过 `dispatchDraw()` 递归访问子节点。ViewRootImpl 负责顶层起点，DecorView 则以 View 身份参与遍历。

```text
约束向下: Root -> Parent -> Child
结果向上: Child -> Parent -> Root
位置向下: Root -> Parent.layout(child) -> Child
绘制递归: Root.draw -> Parent.dispatchDraw -> Child.draw
```

这解释了为什么子 View 不能凭空知道最终尺寸：它看到的是父级生成的 `MeasureSpec`；也解释了为什么 `requestLayout()` 要逐级上报，因为可能需要重新决定祖先和兄弟节点的位置。

## 四、附着与坐标边界

View 只有附着到窗口后，才拥有对应的 `ViewRootImpl` 链路、窗口令牌和稳定的窗口级交互能力。`isAttachedToWindow` 可用于判断附着状态，`onAttachedToWindow()` / `onDetachedFromWindow()` 是注册和释放窗口相关资源的边界。

常用坐标层次：

- `left/top/right/bottom`：相对父 View 的布局边界；
- `x/y`：布局位置叠加 translation 后的视觉属性；
- Canvas 局部坐标：通常以当前 View 左上角为原点，并受变换影响；
- `getLocationInWindow()`：相对窗口；
- `getLocationOnScreen()`：相对屏幕。

## 五、用公开 API 观察边界

以下 Kotlin 代码在业务根 View 上观察附着、可见窗口区域与根节点身份。`view.rootView` 通常可到达当前 View 层级的顶层 View，但不要据此推断 DecorView 内部固定结构。

```kotlin
package com.example.customview.internals

import android.graphics.Rect
import android.util.Log
import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.doOnAttach

fun View.installWindowProbe() {
    doOnAttach { attached ->
        val visibleFrame = Rect()
        attached.getWindowVisibleDisplayFrame(visibleFrame)
        val insets = ViewCompat.getRootWindowInsets(attached)

        Log.d("WindowProbe", buildString {
            append("attached=")
            append(attached.isAttachedToWindow)
            append(", root=")
            append(attached.rootView.javaClass.name)
            append(", windowFrame=")
            append(visibleFrame)
            append(", systemBars=")
            append(insets?.getInsets(
                androidx.core.view.WindowInsetsCompat.Type.systemBars()
            ))
        })
    }

    addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
        override fun onViewAttachedToWindow(v: View) = Unit

        override fun onViewDetachedFromWindow(v: View) {
            Log.d("WindowProbe", "detached: cancel callbacks owned by this View")
        }
    })
}
```

代码使用 AndroidX Core 的 `ViewCompat`、`WindowInsetsCompat` 与 `doOnAttach`。生产代码中，匿名监听器若需移除，应保存实例并在合适边界调用 `removeOnAttachStateChangeListener()`。

> **无障碍提示**：DecorView 层级与无障碍节点树并非一一对应。无障碍服务消费的是语义节点；自定义绘制的多个可操作区域可能需要暴露虚拟节点。

## 六、常见陷阱

1. **把 ViewRootImpl 当根 View**：它是桥接对象，不是 `ViewGroup`，不能通过 `findViewById()` 找到。
2. **把业务 XML 根节点当 DecorView**：二者之间通常还有 content 容器。
3. **依赖 DecorView 私有层级**：主题、系统版本和窗口模式都可能改变结构。
4. **未附着就读取窗口级信息**：Insets、窗口位置或令牌可能尚不可用。
5. **在 `onAttachedToWindow()` 注册后不释放**：导致帧回调、观察者或监听器泄漏。
6. **假设一次请求对应一次完整遍历**：请求可合并，各阶段也可能被跳过。

## 七、实践检查清单

- [ ] 我能画出 Window、DecorView、业务根 View 与 ViewRootImpl 的关系。
- [ ] 我能明确说出 ViewRootImpl 不是 View，也不是可公开操作的 API。
- [ ] 我没有依赖 DecorView 的固定子节点索引。
- [ ] 窗口相关读取发生在附着之后。
- [ ] 在附着时注册的回调会在分离时成对释放。
- [ ] 我能区分父坐标、窗口坐标和屏幕坐标。
- [ ] 我用 Layout Inspector 或日志验证过实际根层级。

## 小结

Window 提供顶层窗口抽象，DecorView 是参与遍历的顶层 View，业务内容位于其内容容器内，ViewRootImpl 则在树外连接窗口系统并发起遍历。把这些角色分开后，后续的约束来源、失效上报、Insets 与生命周期问题都有了明确边界。

## 官方延伸阅读

- [View](https://developer.android.com/reference/android/view/View)
- [Window](https://developer.android.com/reference/android/view/Window)
- [Window insets](https://developer.android.com/develop/ui/views/layout/edge-to-edge)
- [View source (AOSP)](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/View.java)
- [ViewRootImpl source (AOSP, implementation reference)](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/ViewRootImpl.java)
