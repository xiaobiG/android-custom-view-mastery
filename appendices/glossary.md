# 术语表

本表给出本书统一译法。API 类名和方法名保留英文；首次出现时可写作“测量规格（MeasureSpec）”。

## A—C

| 中文 | English | 简明定义 |
|---|---|---|
| 无障碍 | accessibility | 让不同感知、动作和认知能力的用户可获取与操作界面。 |
| 无障碍动作 | accessibility action | 语义节点向辅助技术公开的可执行操作，如点击、滚动、设置进度。 |
| 无障碍节点 | accessibility node | 辅助技术感知的语义元素；可对应真实 View 或虚拟子元素。 |
| 活动指针 | active pointer | 当前手势状态机选择用来追踪拖动的 pointer ID。 |
| 透明度 | alpha | 像素或图层的不透明度分量。 |
| 抗锯齿 | anti-aliasing | 平滑几何或文字边缘的采样技术。 |
| 轴对齐包围盒 | axis-aligned bounding box, AABB | 边与坐标轴平行、包住目标几何体的最小矩形。 |
| 基线 | baseline | 文字字形对齐的水平参考线。 |
| 位图 | bitmap | 由像素数组表示的栅格图像。 |
| 混合模式 | blend mode | 源颜色与目标颜色的组合规则。 |
| 画布 | Canvas | Android 2D 绘制命令与变换/裁剪状态的入口。 |
| 子 View 测量规格 | child MeasureSpec | 父容器根据自身约束与子 LayoutParams 推导出的约束。 |
| 帧编排器 | Choreographer | 将帧回调与显示系统帧信号协调的组件。 |
| 裁剪 | clipping | 限制后续绘制可影响的区域。 |
| 颜色空间 | color space | 用于解释颜色分量及其色域/传递特性的模型。 |
| 合成 | compositing | 把多个图层或绘制结果组合成最终帧。 |
| 内容坐标 | content coordinates | 控件内部模型/场景使用、尚未映射到 View 的坐标空间。 |

## D—H

| 中文 | English | 简明定义 |
|---|---|---|
| 衰减动画 | decay animation | 速度随时间衰减并最终停止的惯性运动。 |
| 脏区域 | dirty region | 自上次绘制后内容发生变化、需要更新的区域。 |
| 分发 | dispatch | 输入事件沿 View 树选择目标并传递的过程。 |
| 显示列表 | display list | 记录绘制操作、供渲染线程/GPU 重放的中间表示。 |
| dp / 密度无关像素 | density-independent pixel | 经屏幕密度缩放的 UI 几何单位。 |
| 绘制遍历 | draw traversal | View 树执行背景、内容、子项、前景等绘制阶段的过程。 |
| 缓动 | easing | 动画进度随时间的非线性变化规则。 |
| 边缘效果 | EdgeEffect | 滚动到边界时的视觉反馈组件。 |
| 精确约束 | EXACTLY | MeasureSpec 模式：父容器要求使用给定尺寸。 |
| fling / 惯性滑动 | fling | 手势抬起后按估算速度继续并减速的滚动。 |
| 字体度量 | font metrics | ascent、descent、leading 等垂直排版参数。 |
| 帧预算 | frame budget | 在下一次显示截止前准备完一帧的可用时间。 |
| 帧步调 | frame pacing | 帧的产生与显示节奏；稳定性与平均帧率同样重要。 |
| 手势仲裁 | gesture arbitration | 点击、拖动、缩放及父子容器之间决定事件归属的过程。 |
| 字形 | glyph | 字体中用于呈现字符或字符组合的具体图形。 |
| GPU 过度绘制 | GPU overdraw | 同一像素在一帧中被多次不必要覆盖绘制。 |
| 硬件加速 | hardware acceleration | 由硬件渲染管线执行受支持绘制操作的模式。 |
| 命中测试 | hit testing | 根据输入坐标判断目标对象或语义节点的过程。 |
| hover / 悬停 | hover | 指针位于元素上方但未按下的输入状态；也用于触摸探索。 |
| HWUI | Hardware-accelerated UI renderer | Android 的硬件加速 UI 渲染系统。 |

## I—M

| 中文 | English | 简明定义 |
|---|---|---|
| 失效 | invalidation | 标记 View/区域需要在后续帧重绘。 |
| 插值器 | interpolator | 把线性时间比例映射为动画进度的函数。 |
| 卡顿 | jank | 帧错过显示时限造成的不流畅视觉体验。 |
| 布局 | layout | 为测量后的 View 确定边界位置的阶段。 |
| LayoutParams / 布局参数 | layout parameters | 子 View 向父容器表达尺寸和布局意图的数据。 |
| 图层 | layer | 可独立绘制或合成的中间表面/缓存。 |
| 局部坐标 | local coordinates | 相对当前 View 原点的坐标空间。 |
| 长按 | long press | 指针在阈值时间内保持按下且移动未超限的手势。 |
| 主线程 | main thread / UI thread | 默认执行 View 生命周期、输入和大多数 UI 修改的线程。 |
| 矩阵 | Matrix | 表示平移、缩放、旋转、斜切/透视等坐标变换的对象。 |
| 测量 | measure | 父约束向下传递、View 计算 measured dimensions 的阶段。 |
| 测量规格 | MeasureSpec | 把约束模式和尺寸打包在一个 Int 中的 View 测量协议。 |
| 已测尺寸 | measured dimensions | `measuredWidth/Height`，measure 阶段产生的结果。 |
| 运动事件 | MotionEvent | 表示触摸、鼠标、触控笔等指针运动的输入事件。 |
| 多点触控 | multi-touch | 同一手势序列中同时追踪多个指针。 |

## N—R

| 中文 | English | 简明定义 |
|---|---|---|
| 嵌套滚动 | nested scrolling | 父子 View 按协议预消费、消费并分配滚动距离/速度。 |
| 离屏图层 | offscreen layer | 在中间缓冲区绘制后再合成的图层，常用于复杂透明/混合。 |
| 画笔 | Paint | 保存颜色、描边、文字、Shader 等绘制参数的对象。 |
| 路径 | Path | 由线段、曲线和轮廓组成的矢量几何描述。 |
| 指针 ID | pointer ID | 在单次手势序列中标识某个指针的稳定整数。 |
| 指针下标 | pointer index | 指针在当前 MotionEvent 数组中的临时位置。 |
| 预乘透明度 | premultiplied alpha | RGB 分量已乘 alpha 存储/计算的颜色表示。 |
| 属性动画 | property animation | 随时间计算值并更新对象属性的动画体系。 |
| px / 像素 | pixel | 绘制 API 最终使用的设备像素单位。 |
| 栅格化 | rasterization | 将矢量/字形/图元转换成像素覆盖值。 |
| RectF / 浮点矩形 | floating-point rectangle | 以 Float 表示 left/top/right/bottom 的矩形。 |
| RenderThread / 渲染线程 | RenderThread | Android 渲染管线中处理显示列表、动画和 GPU 工作提交的线程。 |
| 重绘 | redraw | 因失效而再次执行相关绘制工作的过程。 |
| 重布局请求 | requestLayout | 请求未来重新执行测量/布局遍历。 |
| 资源密度 | resource density | 资源限定与解码缩放所依据的密度信息。 |
| RTL / 从右到左 | right-to-left | 阿拉伯语、希伯来语等界面的布局/阅读方向。 |

## S—Z

| 中文 | English | 简明定义 |
|---|---|---|
| 保存实例状态 | saved instance state | View 在重建后恢复用户可见状态的机制。 |
| 缩放手势 | scale gesture | 通常由两个或更多指针 span 变化形成的缩放输入。 |
| 语义 | semantics | 控件对辅助技术/自动化公开的角色、名称、状态和动作。 |
| Shader / 着色器 | shader | 为绘制提供渐变、位图采样或其他逐像素颜色来源。 |
| 软件渲染 | software rendering | 主要由 CPU 软件 Canvas 执行绘制的路径。 |
| sp / 可缩放像素 | scale-independent pixel | 同时考虑密度和用户字体缩放的文字单位。 |
| 弹簧动画 | spring animation | 由刚度、阻尼等参数描述的物理动画。 |
| StaticLayout | StaticLayout | Android 对静态多行文本进行换行与布局的类。 |
| 触摸代理 | TouchDelegate | 由父 View 扩展子 View 触摸命中区域的机制。 |
| 触摸阈值 | touch slop | 系统建议的最小移动阈值，用于区分点击抖动与拖动。 |
| 变换 | transform | 从一个坐标空间到另一个坐标空间的映射。 |
| TypedArray / 类型化属性数组 | TypedArray | 读取主题/XML styleable 属性值的容器，使用后必须回收。 |
| 未指定约束 | UNSPECIFIED | MeasureSpec 模式：父容器不给尺寸上限。 |
| 速度跟踪器 | VelocityTracker | 根据 MotionEvent 样本估算指针速度的工具。 |
| View 树 | view hierarchy / view tree | 由 ViewGroup 与子 View 构成的层次结构。 |
| ViewGroup / 视图组 | ViewGroup | 可测量、布局、绘制和分发事件给子 View 的容器。 |
| 虚拟节点 | virtual view / virtual node | 不对应真实子 View、但向无障碍系统暴露的语义子元素。 |
| 可见边界 | visual bounds | 元素实际绘制覆盖的边界，可能不同于布局或触摸边界。 |
| 窗口坐标 | window coordinates | 相对当前应用窗口原点的坐标空间。 |
| 包裹内容 | wrap_content | 请求按内容期望尺寸布局、同时服从父约束的 LayoutParams 值。 |

## 容易混淆的成对概念

| 概念 A | 概念 B | 区别 |
|---|---|---|
| `measuredWidth` | `width` | 前者是测量结果；后者是 layout 后 `right-left`。 |
| `left/top` | `x/y` | 前者是布局边界；后者还包含 translation。 |
| pointer ID | pointer index | ID 跨事件稳定；index 每个事件都可能变化。 |
| invalidate | requestLayout | 前者请求重绘；后者请求测量/布局，通常也带来绘制。 |
| View 局部坐标 | 屏幕坐标 | 原点和变换链不同，不能直接混算。 |
| Paint alpha | View alpha | 前者影响单次绘制；后者影响整个 View 合成。 |
| 字形边界 | 文字 advance | 可见像素范围不等于排版前进距离。 |
| 布局边界 | 触摸边界 | 可通过 TouchDelegate 扩大命中，二者不必相同。 |
| 裁剪 | 遮罩/混合 | clip 限制覆盖区域；遮罩常需要图层与混合。 |
| 帧率 | 帧步调 | 平均 fps 高仍可能因帧间隔不均而卡顿。 |
