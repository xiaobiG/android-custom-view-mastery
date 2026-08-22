# 虚拟节点与 ExploreByTouchHelper

## 学习目标

- 判断何时需要虚拟无障碍层级（virtual view hierarchy）。
- 掌握 `ExploreByTouchHelper` 的命中、枚举、填充、动作与失效完整范式。
- 保证虚拟 ID、边界、焦点和动态数据在生产环境中稳定。

## 1. 为什么需要虚拟节点

一个 `View` 可能在同一 Canvas 上画出多个独立操作项，例如星级评分、图表数据点和日历单元格。系统只能看到宿主 View；若不提供虚拟节点，TalkBack 无法逐项探索。

```text
真实 View 树                    辅助技术看到的虚拟树
Activity                        RatingStrip
└── RatingStrip (1 个 View)     ├── 星 1 [可点击]
    Canvas: ★ ★ ★ ★ ★          ├── 星 2 [可点击]
                                ├── 星 3 [可点击]
                                ├── 星 4 [可点击]
                                └── 星 5 [可点击]
```

适用条件：子区域有独立名称、状态或动作，但没有真实子 View。若本来就能使用标准 `Button`、`SeekBar` 或真实子 View，优先复用标准组件。

## 2. 五步完整范式

1. 为宿主创建 helper，并通过 `ViewCompat.setAccessibilityDelegate()` 安装。
2. `getVirtualViewAt()` 把宿主局部坐标映射到虚拟 ID。
3. `getVisibleVirtualViews()` 以逻辑顺序枚举当前可见 ID。
4. `onPopulateNodeForVirtualView()` 填完整节点语义和 `boundsInParent`。
5. `onPerformActionForVirtualView()` 执行动作；数据变化后失效节点。

```text
探索坐标 ─> hitTest ─> virtualId ─> populateNode ─> TalkBack 朗读
                                          │
ACTION_CLICK ─> performAction ─> setRating ┴─> invalidateVirtualView
```

## 3. 可运行的评分控件骨架

```kotlin
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.os.Bundle
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityEvent
import androidx.core.view.ViewCompat
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import androidx.customview.widget.ExploreByTouchHelper

class AccessibleRatingView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val helper = RatingTouchHelper(this)
    private val maxRating = 5
    var rating: Int = 0
        private set

    init {
        isFocusable = true
        // 操作属于虚拟子节点，宿主只承载结构，避免重复点击节点。
        ViewCompat.setAccessibilityDelegate(this, helper)
    }

    override fun dispatchHoverEvent(event: MotionEvent): Boolean =
        helper.dispatchHoverEvent(event) || super.dispatchHoverEvent(event)

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled) return false
        return when (event.actionMasked) {
            MotionEvent.ACTION_UP -> {
                val id = virtualIdAt(event.x, event.y)
                if (id != ExploreByTouchHelper.INVALID_ID) {
                    setRating(id + 1)
                    helper.sendEventForVirtualView(id, AccessibilityEvent.TYPE_VIEW_CLICKED)
                }
                true
            }
            MotionEvent.ACTION_DOWN -> true
            else -> super.onTouchEvent(event)
        }
    }

    private fun setRating(value: Int) {
        val newValue = value.coerceIn(0, maxRating)
        if (newValue == rating) return
        val old = rating
        rating = newValue
        invalidate()
        if (old > 0) helper.invalidateVirtualView(old - 1)
        if (rating > 0) helper.invalidateVirtualView(rating - 1)
        helper.invalidateRoot()
    }

    private fun cellBounds(id: Int, out: Rect) {
        val contentWidth = width - paddingLeft - paddingRight
        val cell = if (maxRating == 0) 0 else contentWidth / maxRating
        val left = paddingLeft + id * cell
        val right = if (id == maxRating - 1) width - paddingRight else left + cell
        out.set(left, paddingTop, right, height - paddingBottom)
    }

    private fun virtualIdAt(x: Float, y: Float): Int {
        val bounds = Rect()
        for (id in 0 until maxRating) {
            cellBounds(id, bounds)
            if (bounds.contains(x.toInt(), y.toInt())) return id
        }
        return ExploreByTouchHelper.INVALID_ID
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val bounds = Rect()
        for (id in 0 until maxRating) {
            cellBounds(id, bounds)
            paint.color = if (id < rating) 0xffffb300.toInt() else 0xff757575.toInt()
            canvas.drawCircle(bounds.exactCenterX(), bounds.exactCenterY(),
                minOf(bounds.width(), bounds.height()) * .3f, paint)
        }
    }

    private inner class RatingTouchHelper(host: View) : ExploreByTouchHelper(host) {
        override fun getVirtualViewAt(x: Float, y: Float): Int = virtualIdAt(x, y)

        override fun getVisibleVirtualViews(virtualViewIds: MutableList<Int>) {
            // 顺序就是默认探索/朗读顺序；只加入当前可见且可交互的项。
            for (id in 0 until maxRating) virtualViewIds += id
        }

        override fun onPopulateNodeForVirtualView(
            virtualViewId: Int,
            node: AccessibilityNodeInfoCompat,
        ) {
            require(virtualViewId in 0 until maxRating)
            val value = virtualViewId + 1
            node.className = android.widget.RadioButton::class.java.name
            // 用一个名称来源，避免 text 与 contentDescription 被重复朗读。
            node.text = "$value 星，共 $maxRating 星"
            node.isCheckable = true
            node.isChecked = rating == value
            node.isClickable = isEnabled
            node.isEnabled = isEnabled
            node.isFocusable = true
            node.setBoundsInParent(Rect().also { cellBounds(virtualViewId, it) })
            if (isEnabled) node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK)
        }

        override fun onPerformActionForVirtualView(
            virtualViewId: Int,
            action: Int,
            arguments: Bundle?,
        ): Boolean {
            return when (action) {
                AccessibilityNodeInfoCompat.ACTION_CLICK -> {
                    if (!isEnabled || virtualViewId !in 0 until maxRating) false
                    else {
                        setRating(virtualViewId + 1)
                        sendEventForVirtualView(
                            virtualViewId,
                            AccessibilityEvent.TYPE_VIEW_CLICKED,
                        )
                        true
                    }
                }
                else -> false
            }
        }
    }
}
```

> **注意**：代码中的显示字符串应移入 `strings.xml` 并按 locale 格式化。示例内联字符串只为突出节点范式。

### ID 与边界的不变量

虚拟 ID 是焦点身份，不是数组位置的临时别名。动态集合应使用稳定业务 ID 到 `Int` 的映射，并在项删除前清理焦点/发送变化；排序变化不能让原 ID 指向另一对象。

`boundsInParent` 必须是宿主局部坐标中的非空可见区域，包含 padding、滚动和 RTL 后的真实点击区域。不可用屏幕坐标，也不可给所有节点同一个宿主边界。

> **无障碍提示**：触摸命中与虚拟节点边界应调用同一几何函数，否则用户摸到 A、TalkBack 却聚焦 B。

## 4. 宿主、子节点与事件策略

宿主节点描述整体（如“评分，3/5”），子节点描述单项。不要让宿主和所有子节点都暴露同一个点击动作，造成重复焦点。数据变化时：

- 单节点属性变化：`invalidateVirtualView(id, changeType)`。
- 列表结构或多个节点变化：`invalidateRoot()`。
- 用户执行虚拟点击：完成状态更新后 `sendEventForVirtualView(id, TYPE_VIEW_CLICKED)`。
- 高频动画：只报告有意义的离散状态或最终值。

`ExploreByTouchHelper` 还管理无障碍焦点与键盘焦点；不要自己维护第二套“TalkBack 焦点”布尔值。

## 5. Kotlin 测试：逐个审计虚拟节点

```kotlin
import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.view.ViewCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RatingVirtualNodesTest {
    @Test
    fun fiveVirtualChildren_haveNamesBoundsAndClickAction() {
        ActivityScenario.launch(RatingActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val view = activity.findViewById<AccessibleRatingView>(R.id.rating)
                val provider = ViewCompat.getAccessibilityNodeProvider(view)
                    ?: error("AccessibilityNodeProvider missing")
                val root = provider.createAccessibilityNodeInfo(
                    AccessibilityNodeInfo.HOST_VIEW_ID,
                ) ?: error("host node missing")
                assertEquals(5, root.childCount)

                repeat(5) { id ->
                    val node = provider.createAccessibilityNodeInfo(id)
                        ?: error("virtual node $id missing")
                    val rect = Rect().also(node::getBoundsInScreen)
                    assertTrue(!node.text.isNullOrEmpty() || !node.contentDescription.isNullOrEmpty())
                    assertFalse(rect.isEmpty)
                    assertTrue(node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK })
                }
            }
        }
    }
}
```

不同 AndroidX/平台版本的 provider 暴露细节可能变化；仪器测试应锁定项目版本，并以 TalkBack 手动探索作为最终验收。

## 常见陷阱

- 忘记转发 `dispatchHoverEvent()`，触摸探索完全失效。
- `getVisibleVirtualViews()` 返回不可见项、重复 ID 或顺序随机。
- 节点没有文本/描述、没有非空边界，helper 会拒绝或服务无法使用。
- 数据刷新后不调用 `invalidateVirtualView()`/`invalidateRoot()`。
- 虚拟 ID 随排序复用，焦点跳到另一业务对象。
- 节点声称可点击，但 `onPerformActionForVirtualView()` 返回 `false`。
- 同时把宿主和每个子节点都设成可点击，产生重复操作。

## 实践检查清单

- [ ] 确认虚拟节点优于真实子 View，而非为省事滥用。
- [ ] helper 已安装，hover 事件已转发。
- [ ] 命中测试和节点边界复用同一几何来源。
- [ ] 每个 ID 稳定、唯一；枚举顺序符合阅读顺序。
- [ ] 每个节点有名称、角色、状态、边界和真实可执行动作。
- [ ] RTL、滚动、padding、裁剪和动态删除均有测试。
- [ ] 节点/结构变化发送最小充分的失效与事件。
- [ ] TalkBack 可逐项探索、激活并在刷新后保持合理焦点。

## 小结

`ExploreByTouchHelper` 的核心不是“生成几个节点”，而是建立稳定的身份、几何、语义、动作和变化通知。任何一环与绘制/触摸状态不一致，虚拟层级都会失真。

## 延伸阅读

- [AndroidX `ExploreByTouchHelper` API](https://developer.android.com/reference/kotlin/androidx/customview/widget/ExploreByTouchHelper)
- [Android Developers：自定义 View 的虚拟层级](https://developer.android.com/guide/topics/ui/accessibility/views/custom-views#virtual-hierarchy)
- [AndroidX `AccessibilityNodeProviderCompat`](https://developer.android.com/reference/kotlin/androidx/core/view/accessibility/AccessibilityNodeProviderCompat)
- [Android Developers：Android TV 自定义 View 无障碍](https://developer.android.com/training/tv/accessibility/custom-views)
