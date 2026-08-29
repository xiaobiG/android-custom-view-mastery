# Camera 三维变换

> 本章定位：理解 `android.graphics.Camera` 如何把 3D 旋转/平移投影成 2D Canvas 矩阵，
> 实现卡片翻转、翻页等透视效果，并说清它与 CameraX、硬件加速之间的边界。

## 学习目标

- 区分 `android.graphics.Camera`、CameraX（`androidx.camera`）与 `android.hardware.Camera`。
- 掌握 `rotateX/rotateY/rotateZ`、`translate`、`applyToCanvas`、`getMatrix` 的配合方式。
- 理解默认相机位置 `(0, 0, -8)` 带来的透视感，以及如何绕任意中心点变换。
- 用 `save/restore` 与 `Matrix` 的 `pre/post` 组合出卡片翻转、翻页效果。
- 知道硬件加速下的限制、性能代价与更廉价的替代方案。

## 先分清三个 Camera

Android 生态里"Camera"这个名字被用在了三个毫不相干的类上，混用会导致灾难：

| 类 | 所属包 | 用途 |
|---|---|---|
| `android.graphics.Camera` | 平台 SDK（API 1 起） | 3D 几何变换，输出到 `Matrix`/`Canvas`，本章主角 |
| `android.hardware.Camera` | 平台 SDK | 摄像头硬件 API，API 21 起已废弃，改用 Camera2 |
| CameraX | `androidx.camera` | Jetpack 相机库，围绕 `Preview`/`ImageCapture` 等用例 |

> **注意**：下文所有"Camera"均指 `android.graphics.Camera`。它不碰相机硬件，只是一个
> 计算 3D 旋转/平移并把结果投影到 2D 平面的几何工具。

## 问题场景：2D 绘制的透视感

普通的 `canvas.rotate()` 只是平面旋转，无法表达"绕 Y 轴转过去"的立体感。卡片翻转、
翻页、弹跳入场这些效果，需要一个额外的**深度维度**：让靠近观察者的边缘显得更大，
远离的显得更小。这正是 Camera 做的事——它把 3D 变换做投影，产出一个包含透视分量的
`Matrix`，再由 `Canvas.concat()` 应用到绘制上。

```text
3D 模型坐标（x, y, z）
   │  Camera.rotateY(deg) / translate(z)
   ▼
透视投影（观察者位于 z = -8）
   │  近大远小
   ▼
2D 齐次矩阵（Matrix，含 MPERSP 分量）
   │  canvas.concat(matrix)
   ▼
最终绘制（屏幕 2D）
```

## 核心机制：相机位置与投影

`android.graphics.Camera` 内部维护一个 3D 状态机，默认的相机位置是
`(0, 0, -8)`（官方源码注释：default location is set at `0, 0, -8`）。z 越大越靠近
"观察者"，z 为负表示在画布平面后方。对自定义 View 来说，实际视觉效果大致是：

```text
            观察者（相机，默认在 z=-8）
                  ▲
                  │ z 轴（指向观察者）
                  │
     ┌───────┐    │
     │ 画布  │----+----> x 轴
     └───────┘    │
                  ▼ 场景中的内容（x,y,z）
```

- `rotateX(deg)`：绕 x 轴翻转，出现"低头/仰头"的纵向透视；
- `rotateY(deg)`：绕 y 轴翻转，卡片左右翻转主要用它；
- `rotateZ(deg)`：绕 z 轴旋转，等效平面旋转；
- `translate(x, y, z)`：平移相机相对内容的位置；`z` 为正是靠近观察者（放大），为负
  是远离（缩小）。

关键点是：**Camera 的旋转中心永远是坐标原点**。要绕内容中心翻转，必须先移动画布
原点，再做变换，最后移回——这就是下面示例里 `canvas.translate(cx, cy)` 配合
`applyToCanvas` 的原因。

### 输出：`getMatrix` 与 `applyToCanvas`

- `getMatrix(matrix)`：把当前变换"拷贝"进一个 `Matrix`，便于你继续 `pre/post` 组合或
  离线缓存；
- `applyToCanvas(canvas)`：等价于"取当前矩阵并 concat 到画布"。平台源码里，硬件加速
  画布走 `getMatrix()` + `canvas.concat()`；软件画布走原生直接应用，结果一致。

```text
Camera 状态 ──getMatrix()──> Matrix ──pre/post 调整绕点----> concat 到 Canvas
Camera 状态 ──applyToCanvas()──> 直接生效（内部同样是 Matrix concat）
```

## Kotlin 示例：卡片翻转动画

下面的自定义 View 用 `ValueAnimator` 驱动 `rotateY` 从 0° 到 180°，实现绕垂直中轴的
立体翻转。动画在 `onDetachedFromWindow()` 中取消，避免 detach 后继续回调。

```kotlin
package com.example.canvas

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Camera
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.View

class FlipCardView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    // 复用在 onDraw 中，避免每帧分配对象。
    private val camera = Camera()
    private val matrix = Matrix()
    private val front = Path()
    private val back = Path()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)

    private var rotationYDegrees = 0f
    private var animator: ValueAnimator? = null

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        val m = 40f
        front.reset()
        front.addRoundRect(
            android.graphics.RectF(m, m, width - m, height - m), 24f, 24f, Path.Direction.CW
        )
        back.set(front)
    }

    fun startFlip() {
        animator?.cancel()
        animator = ValueAnimator.ofFloat(0f, 180f).apply {
            duration = 600
            addUpdateListener { a ->
                rotationYDegrees = a.animatedValue as Float
                invalidate() // 驱动重绘；硬件加速下可换 postInvalidateOnAnimation()
            }
            start()
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f
        val cy = height / 2f
        val checkpoint = canvas.save()
        try {
            camera.save()
            // Camera 绕原点旋转：先把原点移到内容中心。
            camera.rotateY(rotationYDegrees)
            // 翻转超过 90° 后，内容在透视下变窄直至反转。
            camera.getMatrix(matrix)

            // 以内容中心为枢轴：先平移原点，应用变换，再移回。
            matrix.preTranslate(-cx, -cy)
            matrix.postTranslate(cx, cy)
            canvas.concat(matrix)

            val showFront = rotationYDegrees <= 90f
            paint.color = if (showFront) Color.rgb(63, 81, 181) else Color.rgb(38, 50, 56)
            paint.style = Paint.Style.FILL
            canvas.drawPath(if (showFront) front else back, paint)
            camera.restore()
        } finally {
            canvas.restoreToCount(checkpoint)
        }
    }

    override fun onDetachedFromWindow() {
        animator?.cancel()
        animator = null
        super.onDetachedFromWindow()
    }
}
```

要点：

- `camera.save()/restore()` 把临时变换隔离在本次绘制内，配合 `canvas.save/restore`
  双重保护，避免状态泄漏到后续绘制；
- `getMatrix` 后再用 `preTranslate/postTranslate` 绕中心旋转，这是与 Matrix
  pre/post 顺序联动的标准套路（详见下一节）；
- 动画属性只更新一个 `Float`，绘制读取它，符合"状态与绘制分离"的原则。

### 翻页效果的思路

翻页是翻转的变体：枢轴不在中心，而在书页的装订边（比如左缘）：

```kotlin
// 绕左缘翻页：原点先移到左边缘，而不是中心
val pageX = 0f
camera.rotateY(-angle)          // 页面向右翻开
matrix.preTranslate(-pageX, -cy)
matrix.postTranslate(pageX, cy)
canvas.concat(matrix)
```

配合 `translate(z)` 还能在翻转过程中让内容轻微靠近/远离观察者，增强"纸页飞起"的
立体感。注意翻页通常要叠加裁剪（只显示半页范围），否则会看到页面越出边界，这部分
交给 `canvas.clipRect` 处理。

## 与 Matrix 的 pre/post 顺序联动

`camera.getMatrix(m)` 写出的矩阵只表达 Camera 自身的旋转/平移，**不含你的枢轴调整**。
要绕任意点 `(px, py)` 旋转，等价于先平移到原点、旋转、再平移回去：

```text
最终变换 = T(px, py) · M_camera · T(-px, -py)

用 Android Matrix 的术语表达（对列向量从右往左读）：
  m.preTranslate(-px, -py)   → M = M_camera · T(-px, -py)
  m.postTranslate(px, py)    → M = T(px, py) · M
```

- `pre` 意味着"在矩阵的右边乘"：先发生，作用于最靠近原点的坐标；
- `post` 意味着"在矩阵的左边乘"：后发生。

常见错误是反过来写，导致翻转中心偏移或内容飞离视口。也可以不碰 Matrix，直接
`canvas.translate(px, py)` → `applyToCanvas` → `canvas.translate(-px, -py)`，两者等价，
选一种并保持一致即可。

## 硬件加速下的限制与已知问题

Camera 变换最终是带透视（`MPERSP` 分量）的矩阵 concat，硬件加速（API 11+ 默认开启）
一般能正确渲染，但有以下已知边界：

1. **文本渲染差异**：在带透视分量的矩阵下绘制文字，部分系统版本上可能出现渲染
   缺失、模糊或与软件渲染不一致。涉及文字翻转时，务必在目标 API 的真机上做截图对比。
2. **离屏图层行为**：`saveLayer`/`alpha` 等离屏路径与 Camera 透视矩阵叠加时，
   中间缓冲区的边界可能比直觉更大或结果不同。优先给 `saveLayer` 传紧致的 `bounds`，
   而不是传 `null` 让整层离屏。
3. **裁剪**：旋转后内容超出 View 边界会被裁掉，`canvas.save()` 的区域或
   `clipRect` 要与动画包络一致。
4. **逐帧分配**：`getMatrix` 与 `applyToCanvas` 在硬件加速画布上会触达 `Matrix`
   对象；在 `onDraw` 里每次 `new Camera()`/`new Matrix()` 会造成分配与 GC，应复用
   字段。

> **性能提示**：Camera 是 CPU 侧计算，每一帧都要重新做一次 3D→2D 投影。单块内容
> 翻转的开销可以忽略，但大量同时翻转的条目会明显占用 UI 线程时间。若只是让**整个
> View** 做 3D 旋转，优先使用平台自带的 `View.setRotationX/setRotationY`（API 11）加
> `setCameraDistance`（API 12），它们走渲染线程的显示列表，比在
> `onDraw` 里手算更省。

> **注意**：不同厂商/版本的硬件加速管线对透视矩阵的支持程度并不完全一致。把 Camera
> 效果当作"性能敏感绘制"来对待：受控真机矩阵验收（截图 + 帧时间），而不是只在模拟器
> 上看一眼。

## 适用场景与性能代价

- **适合**：单块/少量内容的卡片翻转、翻页、入场立体动画；`Canvas` 场景内嵌元素。
- **不适合**：列表条目级大量并行翻转（改走 `View` 自带 3D 属性或降低动画数量）；
  需要真实光照/深度排序的 3D 场景（应评估 `OpenGL`/`Vulkan`，而不是 Camera）。
- **代价**：每次绘制多一次矩阵生成与 concat；透视绘制打断某些渲染合并，可能导致
  该区域绘制成本上升。

## 常见陷阱

1. **忘掉默认相机位置**：以为有近大远小，其实是 `(0,0,-8)` 的固定投影；要改透视强度
   用 `setLocation(x, y, z)`（z 越大透视越平）。
2. **旋转中心不对**：Camera 绕原点转，内容没先平移到中心，翻转变成"绕左上角甩动"。
3. **pre/post 写反**：枢轴调整顺序错，内容飞出视口或抖动。
4. **在 onDraw 里 new Camera/Matrix**：每帧分配，GC 抖动。
5. **detach 后动画继续**：`ValueAnimator` 未在 `onDetachedFromWindow()` 取消，
   回调里 `invalidate()` 一个已 detach 的 View。
6. **透视矩阵下画文字不验收**：某些版本渲染异常，截图对比才靠得住。
7. **把 Camera 当 3D 引擎**：没有深度排序与光照，实现不了复杂场景，反而引入性能
   与一致性问题。

## 实践检查清单

- [ ] 正文与注释明确写的是 `android.graphics.Camera`，不引入 CameraX 依赖。
- [ ] 变换前把原点平移到内容中心/枢轴，变换后移回。
- [ ] `getMatrix` 与 `pre/post` 的顺序已写成坐标链验证过。
- [ ] Camera/Matrix 作为字段复用，不在 `onDraw` 分配。
- [ ] 动画在 `onDetachedFromWindow()` 取消，detach 后不 invalidate。
- [ ] 涉及文字或 `saveLayer` 的场景，在目标 API 真机截图对比软/硬件渲染。
- [ ] 整 View 翻转优先考虑 `setRotationX/Y` + `setCameraDistance`。

## 小结

`android.graphics.Camera` 是一个把 3D 状态投影成 2D 矩阵的轻量工具，配合
`canvas.translate` 绕枢轴、`Matrix.pre/post` 调整顺序，就能做出卡片翻转与翻页。
它不会替你做深度排序，也不会让你绕过硬件加速的边界——理解默认相机位置、枢轴处理
和逐帧分配，是把它用得可靠的前提。

## 延伸阅读

- [Camera API（android.graphics.Camera）](https://developer.android.com/reference/android/graphics/Camera)
- [CameraX（androidx.camera，与之无关）](https://developer.android.com/camera)
- [硬件加速官方说明](https://developer.android.com/guide/topics/graphics/hardware-accel)
- [Matrix API](https://developer.android.com/reference/android/graphics/Matrix)
- [View.setRotationX](https://developer.android.com/reference/android/view/View#setRotationX(float))
