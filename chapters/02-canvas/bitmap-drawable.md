# Bitmap、Drawable 与资源管理

## 学习目标

- 区分 Bitmap 像素内存、Drawable 绘制协议与资源密度缩放。
- 正确计算采样、缩放和像素内存成本。
- 管理缓存、生命周期和可变 Drawable 状态。

## 两层抽象

`Bitmap` 是像素缓冲；`Drawable` 是“给定 bounds 与 state 后如何绘制”的对象，可能由位图、矢量、形状或状态列表实现。

```text
resource / file / network
          │ decode
          ▼
 Bitmap pixels ── BitmapDrawable ─┐
 Vector XML ───── VectorDrawable ─┼─ setBounds → draw(Canvas)
 Shape XML ────── GradientDrawable┘
          │
          ▼
 Canvas target (screen / bitmap / picture)
```

ARGB_8888 的像素数据近似占用：

```text
bytes = rowBytes × height ≈ width × height × 4
```

一张 4000×3000 图仅像素约 48,000,000 字节；解码后尺寸而不是压缩文件大小决定主要内存。实际还包括对象、行对齐、缓存与中间缓冲。

## 密度与采样

放在 `drawable-hdpi` 的位图带有源密度。加载到 xhdpi 设备时，Android 会按目标密度缩放；若像素应原样使用，选择合适的 `drawable-nodpi`，但 UI 资源通常应提供密度变体或矢量。

大图先读取 bounds，再选择 `inSampleSize`。采样目标应覆盖最终显示尺寸，避免解码远大于目标，也避免过度采样后再放大而模糊。

## inBitmap 位图复用

连续解码多张相似图片时，每次 `decodeResource` 都会新分配一块像素内存。`BitmapFactory.Options.inBitmap` 让解码器把新位图的像素写入一块已有位图的内存而不是新分配，适合列表滚动中反复解码的缩略图、连拍帧等场景，能减少分配与 GC 压力。

```kotlin
// 调用方维护一个可复用池；只放“尺寸足够大且已无引用”的位图。
val reusePool = ArrayDeque<Bitmap>()

fun decodeWithReuse(resId: Int): Bitmap {
    val candidate = reusePool.lastOrNull()
    val options = BitmapFactory.Options().apply {
        inSampleSize = 2 // 与 inBitmap 组合需 API 19+；真实实现按目标尺寸计算
        if (candidate != null) {
            inBitmap = candidate // 复用 candidate 的像素内存
            inMutable = true     // 被复用的位图必须是可变的
        }
    }
    return requireNotNull(BitmapFactory.decodeResource(resources, resId, options)) {
        "Unable to decode resource $resId"
    }
}
```

适用条件与版本：

- API 11 起支持 `inBitmap`。API 11–18 限制严格：被复用位图必须与解码结果尺寸、配置完全相同，且 `inSampleSize` 必须为 1。
- API 19（KitKat）起放宽：被复用位图只要不小于解码结果即可，采样后的尺寸也可小于复用对象；配置仍需兼容。
- 被复用的位图必须 `isMutable`，且不能是硬件 Bitmap（HARDWARE 配置用于只读 GPU 绘制，不能复用）。
- `inJustDecodeBounds = true` 的第一次只读 bounds、不分配像素，与 `inBitmap` 无冲突；真正的复用发生在第二次实际解码时，此时可同时携带 `inSampleSize`。

> **注意**：复用失败会在解码时抛 `IllegalArgumentException`，典型原因包括 `inMutable` 为 false、尺寸/配置不兼容，或对象仍在绘制/使用中。把候选位图放回池前必须移除对其的全部引用。

> **性能提示**：`inBitmap` 省的是“分配新像素内存”的成本，解码与采样本身仍要执行。只有当候选池命中率高、对象生命周期可控时才值得维护；池与位图本身也是内存成本。

## 完整 Kotlin 示例：按目标尺寸采样并绘制 Drawable

```kotlin
package com.example.canvas

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Rect
import android.graphics.drawable.Drawable
import android.util.AttributeSet
import android.view.View
import androidx.appcompat.content.res.AppCompatResources
import com.example.R
import kotlin.math.max

fun decodeSampledBitmap(
    context: Context,
    resId: Int,
    reqWidth: Int,
    reqHeight: Int
): Bitmap {
    require(reqWidth > 0 && reqHeight > 0)
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeResource(context.resources, resId, bounds)

    var sample = 1
    var halfW = bounds.outWidth / 2
    var halfH = bounds.outHeight / 2
    while (halfW / sample >= reqWidth && halfH / sample >= reqHeight) {
        sample *= 2
    }
    val options = BitmapFactory.Options().apply {
        inSampleSize = max(1, sample)
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }
    return requireNotNull(BitmapFactory.decodeResource(context.resources, resId, options)) {
        "Unable to decode resource $resId"
    }
}

class DrawableCardView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private val icon: Drawable = requireNotNull(
        AppCompatResources.getDrawable(context, R.drawable.ic_android)
    ).mutate()
    private val target = Rect()

    init {
        icon.callback = this
        icon.setTint(0xFF3F51B5.toInt())
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        target.set(paddingLeft, paddingTop, w - paddingRight, h - paddingBottom)
        icon.bounds = target
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        icon.draw(canvas)
    }

    override fun verifyDrawable(who: Drawable): Boolean =
        who === icon || super.verifyDrawable(who)

    override fun drawableStateChanged() {
        super.drawableStateChanged()
        if (icon.isStateful) icon.state = drawableState
    }

    override fun onDetachedFromWindow() {
        icon.callback = null
        super.onDetachedFromWindow()
    }
}
```

`Drawable.draw()` 依赖 `bounds`；忘记 `setBounds()` 常得到“什么也没画”。`mutate()` 让后续 tint/state 修改不再影响共享 ConstantState 派生的其他实例。可动画 Drawable 还应在脱离窗口时 `stop()`。

## centerCrop 坐标推导

源图 `(sw,sh)` 填满目标 `(dw,dh)`：

```text
s = max(dw / sw, dh / sh)
```

缩放后尺寸 `(sw·s, sh·s)`，居中平移：

```text
dx = (dw - sw × s) / 2,  dy = (dh - sh × s) / 2
```

`dx` 或 `dy` 为负代表裁掉超出目标的部分。可用 Matrix 或 BitmapShader 应用该变换；若用 `drawBitmap(src, dst, paint)`，应先按相同比例计算需要裁剪的源 `src` 矩形。不要先创建一个同尺寸临时 Bitmap 只为裁剪。

## 所有权、缓存与回收

现代 Android 中 Bitmap 像素内存由运行时管理；不要对仍可能被 Canvas、Drawable、缓存或其他组件使用的 Bitmap 调用 `recycle()`。更可靠的是明确所有权、移除引用并让 GC 回收。缓存应按字节成本计量而非张数，可用 `bitmap.allocationByteCount`（API 19+）估算条目成本。

网络图片生产代码优先使用成熟图片库处理解码、复用、缓存、生命周期与硬件 Bitmap。硬件 Bitmap 适合只读 GPU 绘制，但不能直接访问像素，也不适用于所有软件 Canvas/可变操作；请求前应根据后续操作选择配置。

> **性能提示**：不要在 `onDraw()` 解码资源或创建缩放副本。尺寸已知后预解码，数据变化时替换，并限制内存缓存。

> **注意**：`BitmapFactory.Options.inMutable=true` 不保证任意来源/配置都可变；修改像素前检查 `isMutable`。`Bitmap.Config` 也会影响色彩与内存，不能只按“每像素 4 字节”盲算所有格式。

## 常见陷阱

1. 按 JPEG/PNG 文件大小估算内存，忽略解码尺寸与配置。
2. 忽略资源 density，出现重复缩放或尺寸不一致。
3. Drawable 未设 bounds，或者共享实例 tint 后污染其他位置。
4. 在 `onDraw()` 解码/缩放，造成掉帧和内存峰值。
5. 过早 `recycle()` 导致 “trying to use a recycled bitmap”。
6. 缓存只限张数，不按字节和设备内存预算控制。
7. 对硬件 Bitmap 调用像素读写 API。

## 实践检查清单

- [ ] 解码目标尺寸来自真实显示区域，并使用采样。
- [ ] 预算基于解码像素字节，不基于压缩文件大小。
- [ ] Drawable 已设置 bounds、state、callback，必要时 mutate。
- [ ] 解码、缩放和副本创建均不在 `onDraw()`。
- [ ] 缓存有字节上限，移除时没有仍在使用的强制回收。
- [ ] 动画 Drawable/回调在脱离窗口时停止并释放。

## 小结

Bitmap 管像素与内存，Drawable 管绘制行为与状态。正确的目标尺寸、采样、bounds、所有权和缓存预算，决定了图片绘制能否在真实设备上稳定运行。

## 延伸阅读

- [Bitmap API](https://developer.android.com/reference/android/graphics/Bitmap)
- [BitmapFactory.Options](https://developer.android.com/reference/android/graphics/BitmapFactory.Options)
- [Drawable API](https://developer.android.com/reference/android/graphics/drawable/Drawable)
- [高效加载大位图](https://developer.android.com/topic/performance/graphics/load-bitmap)
- [管理位图内存](https://developer.android.com/topic/performance/graphics/manage-memory)
