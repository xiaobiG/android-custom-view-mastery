# Summary

* [前言](README.md)
* [如何使用本书](chapters/00-introduction/how-to-read.md)
* [学习路线与项目地图](chapters/00-introduction/roadmap.md)

## 第一篇 View 工作原理
* [View 树与窗口渲染概览](chapters/01-view-internals/view-tree.md)
* [Measure：约束如何向下传递](chapters/01-view-internals/measure.md)
* [Layout：位置如何向上确定](chapters/01-view-internals/layout.md)
* [Draw：绘制遍历与顺序](chapters/01-view-internals/draw.md)
* [Invalidate、requestLayout 与帧调度](chapters/01-view-internals/invalidation.md)

## 第二篇 Canvas 绘制体系
* [Canvas、Paint 与绘图状态](chapters/02-canvas/canvas-paint.md)
* [Path 与贝塞尔曲线](chapters/02-canvas/path-bezier.md)
* [Matrix 与坐标系统](chapters/02-canvas/matrix-coordinate.md)
* [Camera 三维变换](chapters/02-canvas/camera-3d.md)
* [Shader、混合与离屏图层](chapters/02-canvas/shader-blend.md)
* [文字测量与排版](chapters/02-canvas/text-layout.md)
* [Bitmap、Drawable 与资源管理](chapters/02-canvas/bitmap-drawable.md)

## 第三篇 事件与手势
* [触摸事件分发机制](chapters/03-input/event-dispatch.md)
* [滑动冲突与状态机](chapters/03-input/gesture-conflict.md)
* [多点触控与缩放旋转](chapters/03-input/multi-touch.md)
* [标准手势识别器](chapters/03-input/gesture-detectors.md)
* [速度、惯性与边缘效果](chapters/03-input/fling-scroll.md)
* [嵌套滚动协议](chapters/03-input/nested-scrolling.md)
* [键盘、鼠标与触控笔](chapters/03-input/multi-input.md)

## 第四篇 自定义 ViewGroup
* [测量子 View](chapters/04-viewgroup/measure-children.md)
* [布局算法与自定义 LayoutParams](chapters/04-viewgroup/layout-params.md)
* [容器事件拦截](chapters/04-viewgroup/interception.md)
* [实战：FlowLayout](chapters/04-viewgroup/flow-layout.md)

## 第五篇 动画系统
* [ValueAnimator 与属性动画](chapters/05-animation/value-animator.md)
* [插值器、估值器与时间系统](chapters/05-animation/timing.md)
* [弹簧、衰减与手势衔接](chapters/05-animation/physics.md)
* [帧同步与动画生命周期](chapters/05-animation/frame-lifecycle.md)

## 第六篇 性能优化
* [每帧预算与渲染流水线](chapters/06-performance/frame-budget.md)
* [减少分配、缓存与局部更新](chapters/06-performance/allocation-cache.md)
* [硬件加速、图层与过度绘制](chapters/06-performance/hardware-overdraw.md)
* [Perfetto、HWUI 与卡顿定位](chapters/06-performance/profiling.md)
* [Baseline Profile 与冷启动优化](chapters/06-performance/baseline-profile.md)

## 第七篇 状态与样式
* [自定义属性与主题](chapters/07-state-style/attributes-theme.md)
* [控件 API 与状态模型](chapters/07-state-style/component-api.md)
* [实例状态保存与恢复](chapters/07-state-style/saved-state.md)
* [RTL、字体缩放与配置变化](chapters/07-state-style/configuration.md)

## 第八篇 无障碍
* [自定义控件无障碍基础](chapters/08-accessibility/basics.md)
* [虚拟节点与 ExploreByTouchHelper](chapters/08-accessibility/virtual-nodes.md)
* [键盘焦点、语义与测试](chapters/08-accessibility/focus-testing.md)

## 第九篇 测试与调试
* [单元测试与测量测试](chapters/09-testing/unit-measure.md)
* [Espresso 手势与断言](chapters/09-testing/espresso.md)
* [截图测试与视觉回归](chapters/09-testing/screenshot.md)
* [调试清单与故障模式](chapters/09-testing/debugging.md)

## 第十篇 Compose 互操作
* [AndroidView 与状态同步](chapters/10-compose/android-view.md)
* [生命周期、复用与资源释放](chapters/10-compose/lifecycle-reuse.md)
* [输入、嵌套滚动与测试互操作](chapters/10-compose/input-testing.md)
* [迁移决策与边界](chapters/10-compose/migration.md)
* [ComposeView 反向互操作](chapters/10-compose/compose-in-view.md)

## 第十一篇 综合实战
* [圆形进度控件](examples/circular-progress.md)
* [评分控件](examples/rating-view.md)
* [可缩放折线图](examples/zoomable-chart.md)
* [签名画板](examples/signature-pad.md)
* [流程图编辑器架构](examples/diagram-editor.md)

## 附录
* [常用工具类](appendices/toolkit.md)
* [尺寸、颜色与文字速查](appendices/graphics-cheatsheet.md)
* [事件速查表](appendices/input-cheatsheet.md)
* [发布前检查清单](appendices/checklists.md)
* [术语表](appendices/glossary.md)
* [参考资料](appendices/references.md)
