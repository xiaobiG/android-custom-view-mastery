# 实战五：生产级流程图编辑器——场景图、工具状态机与命令系统

## 学习目标

最后一个案例不再把所有逻辑堆在 View 中，而是搭建可演进的编辑器架构：不可变文档模型、场景渲染、相机矩阵、空间索引、工具状态机、选择与拖拽、吸附、命令式撤销重做、虚拟无障碍节点、序列化和性能边界。

## 需求与验收

- 文档包含矩形节点与有向连线；支持选择、框选、拖动、缩放和平移。
- 拖动节点时显示网格/对齐吸附；抬手只产生一条可撤销命令。
- 连接线端点跟随节点，箭头方向正确；命中顺序为控制柄、节点、连线、画布。
- 文档模型不含 View、Paint、Context；可 JSON 持久化和版本迁移。
- 相机变换与文档变换分离；所有命中都经逆矩阵进入世界坐标。
- 1,000 节点、2,000 连线时通过可见区裁剪与空间索引保持交互。
- TalkBack 可遍历节点并执行选择/移动；另提供列表式编辑入口。
- 进程重建恢复文档 URI、相机和选择，小型草稿可内联，大文档不可塞进 SavedState。

## 总体架构

```text
+---------------------- UI / View -----------------------+
| DiagramEditorView                                     |
|  MotionEvent -> InputRouter -> Active Tool state       |
|  Canvas <- Renderer <- SceneSnapshot <- DocumentStore  |
|  a11y <- ExploreByTouchHelper <- SceneSnapshot         |
+--------------------------|-----------------------------+
                           | Commands
+--------------------------v-----------------------------+
| EditorController                                       |
| selection | camera | undo/redo | snap engine           |
+--------------------------|-----------------------------+
                           | immutable update
+--------------------------v-----------------------------+
| DiagramDocument: nodes, edges, schemaVersion           |
| Repository: JSON/file/autosave/migration               |
+--------------------------------------------------------+

Thread boundary:
main thread: input + committed snapshot swap + draw
worker: routing/index rebuild/serialization from immutable snapshot
```

### 为什么不让每个节点成为子 View

少量表单节点可用 ViewGroup，但自由缩放画布上的数千元素会带来测量、布局、焦点与层级状态成本。场景图（scene graph）让编辑器统一变换、裁剪和批量绘制；代价是必须自行实现命中、焦点和无障碍虚拟子节点。

## 关键算法总览

编辑器的关键算法不是单一公式，而是一条保持一致性的管线：相机矩阵负责世界坐标与屏幕坐标互换；空间索引先做候选召回、精确几何再决定命中；工具状态机把连续手势归并为瞬时预览；命令在手势结束时原子提交，并用 `apply/revert` 实现撤销重做；渲染器只消费同一 revision 的不可变快照。后续各节逐一实现这些环节。

## 文档模型与不变量

ID 必须稳定，连线只能引用存在节点。坐标使用世界单位，不使用屏幕 px。模型以不可变值对象暴露，避免后台任务观察到修改一半的状态。

```kotlin
package com.example.diagram

import android.graphics.RectF

@JvmInline value class NodeId(val raw: String)
@JvmInline value class EdgeId(val raw: String)

data class Vec2(val x: Float, val y: Float)
data class Size2(val width: Float, val height: Float)

data class DiagramNode(
    val id: NodeId,
    val position: Vec2,
    val size: Size2,
    val title: String,
    val zIndex: Int = 0
) {
    init {
        require(position.x.isFinite() && position.y.isFinite())
        require(size.width.isFinite() && size.height.isFinite() &&
            size.width > 0f && size.height > 0f)
    }
    fun bounds(out: RectF): RectF = out.apply {
        set(position.x, position.y, position.x + size.width, position.y + size.height)
    }
}

data class DiagramEdge(
    val id: EdgeId,
    val from: NodeId,
    val to: NodeId,
    val label: String = ""
)

data class DiagramDocument(
    val schemaVersion: Int = 1,
    val revision: Long = 0,
    val nodes: Map<NodeId, DiagramNode> = emptyMap(),
    val edges: Map<EdgeId, DiagramEdge> = emptyMap()
) {
    fun validated(): DiagramDocument {
        require(schemaVersion in 1..CURRENT_SCHEMA)
        edges.values.forEach { edge ->
            require(edge.from in nodes && edge.to in nodes) {
                "dangling edge ${edge.id.raw}"
            }
            require(edge.from != edge.to) { "self edge is disabled in this editor" }
        }
        return this
    }

    companion object { const val CURRENT_SCHEMA = 1 }
}
```

> **注意**：`RectF` 是可变 Android 类型，只作为调用方提供的临时输出，不保存在模型中。核心文档若需在 JVM 后端复用，应连该方法也移到 Android 适配层。

## 控制器与命令系统

每次 MOVE 都复制整份文档会产生大量垃圾；控制器在拖动时维护 `TransientOverlay`，渲染时叠加预览，UP 时提交一个命令。撤销栈保存语义命令而不是 Bitmap。

```text
Idle
  | pointer down on selected node
  v
Dragging(originDocument, selectedIds, delta=0)
  | MOVE -> update transient delta -> snap -> invalidate
  | UP   -> execute MoveNodesCommand(from,to) -> Idle
  | CANCEL -> discard transient -> Idle
```

```kotlin
interface EditorCommand {
    val label: String
    fun apply(document: DiagramDocument): DiagramDocument
    fun revert(document: DiagramDocument): DiagramDocument
    fun mergeWith(next: EditorCommand): EditorCommand? = null
}

data class MoveNodesCommand(
    val from: Map<NodeId, Vec2>,
    val to: Map<NodeId, Vec2>
) : EditorCommand {
    override val label = "移动 ${to.size} 个节点"
    override fun apply(document: DiagramDocument) = document.moveNodes(to)
    override fun revert(document: DiagramDocument) = document.moveNodes(from)
}

private fun DiagramDocument.moveNodes(positions: Map<NodeId, Vec2>): DiagramDocument {
    val updated = nodes.toMutableMap()
    positions.forEach { (id, position) ->
        val node = updated[id] ?: return@forEach
        updated[id] = node.copy(position = position)
    }
    return copy(revision = revision + 1, nodes = updated).validated()
}

class EditorController(initial: DiagramDocument) {
    var document: DiagramDocument = initial.validated()
        private set
    var selection: Set<NodeId> = emptySet()
        private set
    var transientDelta: Vec2? = null
        private set

    private val undo = ArrayDeque<EditorCommand>()
    private val redo = ArrayDeque<EditorCommand>()
    var onChanged: (() -> Unit)? = null

    fun select(ids: Set<NodeId>) {
        selection = ids.filterTo(linkedSetOf()) { it in document.nodes }
        onChanged?.invoke()
    }

    fun previewMove(delta: Vec2?) {
        transientDelta = delta
        onChanged?.invoke()
    }

    fun execute(command: EditorCommand) {
        document = command.apply(document)
        undo.addLast(command)
        redo.clear()
        transientDelta = null
        onChanged?.invoke()
    }

    fun undo(): Boolean {
        val command = undo.removeLastOrNull() ?: return false
        document = command.revert(document)
        redo.addLast(command)
        transientDelta = null
        onChanged?.invoke()
        return true
    }

    fun redo(): Boolean {
        val command = redo.removeLastOrNull() ?: return false
        document = command.apply(document)
        undo.addLast(command)
        onChanged?.invoke()
        return true
    }

    fun canUndo() = undo.isNotEmpty()
    fun canRedo() = redo.isNotEmpty()
}
```

生产版本还应为删除节点构造复合命令：命令同时保存被删节点和相邻连线。不能先执行“删节点”，再让模型短暂含悬空边。

## 相机、渲染和命中

`worldToView` 是唯一相机矩阵；绘制先裁剪再连接矩阵。控制柄大小应保持屏幕恒定，因此节点在世界空间绘制，控制柄可在恢复 Canvas 后按映射后的屏幕位置绘制。

```kotlin
class Camera {
    val worldToView = android.graphics.Matrix()
    private val inverse = android.graphics.Matrix()
    private val values = FloatArray(9)
    private val point = FloatArray(2)

    var minScale = 0.25f
    var maxScale = 4f

    fun scale(): Float {
        worldToView.getValues(values)
        return values[android.graphics.Matrix.MSCALE_X]
    }

    fun panBy(dx: Float, dy: Float) { worldToView.postTranslate(dx, dy) }

    fun zoomBy(factor: Float, focusX: Float, focusY: Float) {
        val target = (scale() * factor).coerceIn(minScale, maxScale)
        worldToView.postScale(target / scale(), target / scale(), focusX, focusY)
    }

    fun viewToWorld(x: Float, y: Float): Vec2? {
        if (!worldToView.invert(inverse)) return null
        point[0] = x; point[1] = y
        inverse.mapPoints(point)
        return Vec2(point[0], point[1])
    }

    fun worldRectFor(viewport: RectF, out: RectF): RectF? {
        if (!worldToView.invert(inverse)) return null
        out.set(viewport)
        inverse.mapRect(out)
        return out
    }
}
```

### 空间索引

完整实现可用 R-tree；规则节点编辑器也可用均匀网格：按 `floor(x/cellSize), floor(y/cellSize)` 将节点 ID 放入桶。移动结束后增量更新受影响桶。查询可见矩形或命中容差矩形，最后仍要精确几何判断。

```kotlin
class GridSpatialIndex(private val cellSize: Float = 256f) {
    private val cells = mutableMapOf<Long, MutableSet<NodeId>>()
    private val tempBounds = RectF()

    fun rebuild(nodes: Collection<DiagramNode>) {
        cells.clear()
        nodes.forEach(::insert)
    }

    fun insert(node: DiagramNode) {
        node.bounds(tempBounds)
        forEachCell(tempBounds) { key -> cells.getOrPut(key, ::linkedSetOf).add(node.id) }
    }

    fun query(area: RectF, out: MutableSet<NodeId>) {
        out.clear()
        forEachCell(area) { key -> cells[key]?.let(out::addAll) }
    }

    private inline fun forEachCell(r: RectF, block: (Long) -> Unit) {
        val left = kotlin.math.floor(r.left / cellSize).toInt()
        val right = kotlin.math.floor(r.right / cellSize).toInt()
        val top = kotlin.math.floor(r.top / cellSize).toInt()
        val bottom = kotlin.math.floor(r.bottom / cellSize).toInt()
        for (y in top..bottom) for (x in left..right) {
            block((x.toLong() shl 32) xor (y.toLong() and 0xffffffffL))
        }
    }
}
```

边界恰在 cell 边缘时可能多查一个桶，但精确过滤会消除误报。超大节点跨越大量桶时应转用层级索引。

## Renderer：可见裁剪、边和节点

```kotlin
class DiagramRenderer {
    private val nodePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; style = Paint.Style.FILL
    }
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.DKGRAY; style = Paint.Style.STROKE
    }
    private val edgePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.GRAY; strokeWidth = 2f; style = Paint.Style.STROKE
    }
    private val selectedPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(33, 150, 243); strokeWidth = 3f; style = Paint.Style.STROKE
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.BLACK; textSize = 16f
    }
    private val rect = RectF()

    fun draw(
        canvas: Canvas,
        document: DiagramDocument,
        selection: Set<NodeId>,
        transientDelta: Vec2?,
        visibleIds: Set<NodeId>
    ) {
        document.edges.values.forEach { edge ->
            val from = document.nodes[edge.from] ?: return@forEach
            val to = document.nodes[edge.to] ?: return@forEach
            if (from.id !in visibleIds && to.id !in visibleIds) return@forEach
            val a = centerOf(from, selection, transientDelta)
            val b = centerOf(to, selection, transientDelta)
            canvas.drawLine(a.x, a.y, b.x, b.y, edgePaint)
            drawArrowHead(canvas, a, b)
        }
        document.nodes.values.asSequence()
            .filter { it.id in visibleIds }
            .sortedBy { it.zIndex }
            .forEach { node ->
                val d = if (node.id in selection) transientDelta else null
                rect.set(
                    node.position.x + (d?.x ?: 0f),
                    node.position.y + (d?.y ?: 0f),
                    node.position.x + node.size.width + (d?.x ?: 0f),
                    node.position.y + node.size.height + (d?.y ?: 0f)
                )
                canvas.drawRoundRect(rect, 12f, 12f, nodePaint)
                canvas.drawRoundRect(rect, 12f, 12f,
                    if (node.id in selection) selectedPaint else borderPaint)
                val fm = textPaint.fontMetrics
                val baseline = rect.centerY() - (fm.ascent + fm.descent) / 2
                canvas.drawText(node.title, rect.left + 12f, baseline, textPaint)
            }
    }

    private fun centerOf(n: DiagramNode, selected: Set<NodeId>, d: Vec2?): Vec2 {
        val dx = if (n.id in selected) d?.x ?: 0f else 0f
        val dy = if (n.id in selected) d?.y ?: 0f else 0f
        return Vec2(n.position.x + n.size.width / 2 + dx, n.position.y + n.size.height / 2 + dy)
    }

    private fun drawArrowHead(canvas: Canvas, from: Vec2, to: Vec2) {
        val angle = kotlin.math.atan2(to.y - from.y, to.x - from.x)
        val length = 12f
        for (offset in floatArrayOf(2.6f, -2.6f)) {
            canvas.drawLine(
                to.x, to.y,
                to.x - kotlin.math.cos(angle + offset) * length,
                to.y - kotlin.math.sin(angle + offset) * length,
                edgePaint
            )
        }
    }
}
```

> **性能提示**：连线是否可见不能只看端点是否可见：长线可能穿过视口而两端都在外面。示例是教学简化，生产版应查询边包围盒索引并做线段-矩形相交测试。

## 工具状态机与 View

工具（选择、连线、文本、手形）应实现统一接口，而不是在 `onTouchEvent()` 中堆叠模式布尔值。以下选择工具展示拖动事务。

```kotlin
sealed interface ToolResult {
    data object Ignored : ToolResult
    data object Consumed : ToolResult
    data class Commit(val command: EditorCommand) : ToolResult
}

interface EditorTool {
    fun onDown(world: Vec2, editor: EditorSession): ToolResult
    fun onMove(world: Vec2, editor: EditorSession): ToolResult
    fun onUp(world: Vec2, editor: EditorSession): ToolResult
    fun onCancel(editor: EditorSession)
}

class EditorSession(
    val controller: EditorController,
    val hitTest: (Vec2) -> NodeId?,
    val snap: (Vec2, Set<NodeId>) -> Vec2
)

class SelectionTool : EditorTool {
    private var start: Vec2? = null
    private var from: Map<NodeId, Vec2> = emptyMap()

    override fun onDown(world: Vec2, editor: EditorSession): ToolResult {
        val hit = editor.hitTest(world)
        if (hit == null) {
            editor.controller.select(emptySet()); return ToolResult.Consumed
        }
        if (hit !in editor.controller.selection) editor.controller.select(setOf(hit))
        start = world
        from = editor.controller.selection.associateWith {
            requireNotNull(editor.controller.document.nodes[it]).position
        }
        return ToolResult.Consumed
    }

    override fun onMove(world: Vec2, editor: EditorSession): ToolResult {
        val origin = start ?: return ToolResult.Ignored
        val raw = Vec2(world.x - origin.x, world.y - origin.y)
        editor.controller.previewMove(editor.snap(raw, editor.controller.selection))
        return ToolResult.Consumed
    }

    override fun onUp(world: Vec2, editor: EditorSession): ToolResult {
        val delta = editor.controller.transientDelta ?: return finishIgnored(editor)
        val originalFrom = from
        val to = originalFrom.mapValues { (_, p) -> Vec2(p.x + delta.x, p.y + delta.y) }
        reset(editor)
        return ToolResult.Commit(MoveNodesCommand(originalFrom, to))
    }

    override fun onCancel(editor: EditorSession) = reset(editor)

    private fun finishIgnored(editor: EditorSession): ToolResult {
        reset(editor); return ToolResult.Consumed
    }
    private fun reset(editor: EditorSession) {
        start = null; from = emptyMap(); editor.controller.previewMove(null)
    }
}
```

吸附引擎先把屏幕容差转换为世界容差：`worldTolerance = 8dp / camera.scale()`。对候选节点边、中心和网格寻找绝对距离最小且小于容差的修正；x/y 独立吸附，并返回辅助线。不要把已经吸附的坐标再次当下一帧原点，否则会积累漂移。

View 只负责适配生命周期与 Android 输入：

```kotlin
class DiagramEditorView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null
) : View(context, attrs) {
    private val camera = Camera()
    private val renderer = DiagramRenderer()
    private val index = GridSpatialIndex()
    private val visible = linkedSetOf<NodeId>()
    private val viewport = RectF()
    private val worldViewport = RectF()
    private val scaleDetector = ScaleGestureDetector(context, ScaleListener())
    private var tool: EditorTool = SelectionTool()
    lateinit var controller: EditorController
        private set
    private lateinit var session: EditorSession

    fun bind(value: EditorController) {
        if (::controller.isInitialized && controller === value) return
        if (::controller.isInitialized) controller.onChanged = null
        controller = value
        controller.onChanged = {
            index.rebuild(controller.document.nodes.values)
            invalidate()
        }
        index.rebuild(controller.document.nodes.values)
        session = EditorSession(controller, ::hitNode, ::snapDelta)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (!::controller.isInitialized) return
        viewport.set(paddingLeft.toFloat(), paddingTop.toFloat(),
            (width - paddingRight).toFloat(), (height - paddingBottom).toFloat())
        camera.worldRectFor(viewport, worldViewport)?.let { index.query(it, visible) }
        canvas.save()
        canvas.clipRect(viewport)
        canvas.concat(camera.worldToView)
        renderer.draw(canvas, controller.document, controller.selection,
            controller.transientDelta, visible)
        canvas.restore()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaleDetector.onTouchEvent(event)
        if (scaleDetector.isInProgress || event.pointerCount > 1) {
            tool.onCancel(session)
            return true
        }
        val world = camera.viewToWorld(event.x, event.y) ?: return false
        val result = when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> tool.onDown(world, session)
            MotionEvent.ACTION_MOVE -> tool.onMove(world, session)
            MotionEvent.ACTION_UP -> tool.onUp(world, session)
            MotionEvent.ACTION_CANCEL -> { tool.onCancel(session); ToolResult.Consumed }
            else -> ToolResult.Ignored
        }
        if (result is ToolResult.Commit) controller.execute(result.command)
        if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
        return result !is ToolResult.Ignored
    }

    override fun performClick(): Boolean { super.performClick(); return true }

    private fun hitNode(world: Vec2): NodeId? {
        val tolerance = 8f * resources.displayMetrics.density / camera.scale()
        val area = RectF(world.x - tolerance, world.y - tolerance,
            world.x + tolerance, world.y + tolerance)
        index.query(area, visible)
        return visible.asSequence()
            .mapNotNull { controller.document.nodes[it] }
            .filter { n ->
                world.x >= n.position.x - tolerance &&
                world.x <= n.position.x + n.size.width + tolerance &&
                world.y >= n.position.y - tolerance &&
                world.y <= n.position.y + n.size.height + tolerance
            }
            .maxByOrNull { it.zIndex }?.id
    }

    private fun snapDelta(raw: Vec2, ids: Set<NodeId>): Vec2 {
        val grid = 16f
        val anchor = ids.firstOrNull()?.let { controller.document.nodes[it]?.position } ?: return raw
        val x = kotlin.math.round((anchor.x + raw.x) / grid) * grid - anchor.x
        val y = kotlin.math.round((anchor.y + raw.y) / grid) * grid - anchor.y
        return Vec2(x, y)
    }

    private inner class ScaleListener : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(d: ScaleGestureDetector): Boolean {
            camera.zoomBy(d.scaleFactor, d.focusX, d.focusY)
            invalidate(); return true
        }
    }

    override fun onDetachedFromWindow() {
        if (::controller.isInitialized) controller.onChanged = null
        super.onDetachedFromWindow()
    }
}
```

示例省略单指空白画布平移。生产设计通常提供“手形工具”或 Space+拖动，避免与框选冲突；也可让双指手势同时平移和缩放。

## XML 与 Compose 使用

```xml
<com.example.diagram.DiagramEditorView
    android:id="@+id/editor"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:contentDescription="@string/diagram_editor" />
```

```kotlin
val controller = EditorController(repository.load(documentId))
binding.editor.bind(controller)
binding.undo.setOnClickListener { controller.undo() }
binding.redo.setOnClickListener { controller.redo() }
```

Compose 互操作应让 controller 稳定：

```kotlin
@Composable
fun DiagramEditorHost(
    controller: EditorController,
    modifier: Modifier = Modifier
) {
    AndroidView(
        modifier = modifier,
        factory = { context -> DiagramEditorView(context).apply { bind(controller) } },
        update = { view ->
            // bind 应检测实例，或宿主保证 controller 引用稳定。
            view.bind(controller)
        }
    )
}
```

更完整的 API 可提供 `if (boundController !== value) bind(value)`，避免重组时重复索引。Compose 顶部工具栏、对话框与文件选择器仍使用标准 Compose 控件，画布保留为高性能 View。

## 无障碍：虚拟节点与替代视图

> **无障碍提示**：场景图没有真实子 View，需要 `ExploreByTouchHelper` 暴露虚拟节点。每个节点提供稳定 virtual ID、屏幕 bounds、标题、选中状态，以及选择、向四向移动、删除等动作。连线通常以关系描述附加到节点，而不是全部变成焦点项。

核心映射：

```kotlin
class DiagramA11yHelper(
    host: DiagramEditorView,
    private val snapshot: () -> DiagramDocument,
    private val hitTest: (Float, Float) -> NodeId?,
    private val nodeScreenBounds: (DiagramNode, Rect) -> Unit,
    private val select: (NodeId) -> Unit
) : ExploreByTouchHelper(host) {
    private val idToVirtual = mutableMapOf<NodeId, Int>()
    private val virtualToId = mutableMapOf<Int, NodeId>()

    override fun getVirtualViewAt(x: Float, y: Float): Int =
        hitTest(x, y)?.let(::stableVirtualId) ?: INVALID_ID

    override fun getVisibleVirtualViews(ids: MutableList<Int>) {
        snapshot().nodes.keys.forEach { id -> ids += stableVirtualId(id) }
    }

    override fun onPopulateNodeForVirtualView(id: Int, node: AccessibilityNodeInfoCompat) {
        val item = snapshot().nodes[virtualToId[id]] ?: run {
            node.contentDescription = "不可用节点"; node.setBoundsInParent(Rect())
            return
        }
        node.contentDescription = item.title
        node.className = "android.widget.Button"
        node.isFocusable = true
        val bounds = Rect(); nodeScreenBounds(item, bounds); node.setBoundsInParent(bounds)
        node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK)
    }

    override fun onPerformActionForVirtualView(id: Int, action: Int, args: Bundle?): Boolean {
        val nodeId = virtualToId[id] ?: return false
        return if (action == AccessibilityNodeInfoCompat.ACTION_CLICK) {
            select(nodeId); sendEventForVirtualView(id, AccessibilityEvent.TYPE_VIEW_CLICKED); true
        } else false
    }

    private fun stableVirtualId(id: NodeId): Int {
        return idToVirtual.getOrPut(id) {
            var candidate = id.raw.hashCode() and 0x7fffffff
            while (candidate in virtualToId && virtualToId[candidate] != id) candidate++
            virtualToId[candidate] = id
            candidate
        }
    }
}
```

上段需导入 `androidx.customview.widget.ExploreByTouchHelper`、`AccessibilityNodeInfoCompat`、`Rect` 和 `AccessibilityEvent`。`hitTest` 必须复用 View 的“屏幕坐标 → 逆矩阵 → 空间索引 → 精确几何”命中管线；未命中时返回 `INVALID_ID`，不能返回代表宿主节点的 `HOST_ID`。创建后还要用 `ViewCompat.setAccessibilityDelegate(host, helper)` 安装 delegate，并在宿主 `dispatchHoverEvent()` 中先调用 `helper.dispatchHoverEvent(event)`，否则触摸探索不会进入虚拟节点。

即便有虚拟节点，仍应提供“节点列表”替代界面：用户可搜索、重命名、调整位置和连接关系。复杂二维拖拽不应成为唯一操作方式。

## 状态保存、序列化与自动保存

保存分层：

```text
SavedState (小且同步): documentId/URI, camera[9], selected IDs, active tool
ViewModel (会话): current immutable document, undo/redo, dirty flag
Repository (持久): versioned JSON, atomic temp-write + rename, autosave
```

View 的 `SavedState` 不应直接保存数千节点。文档 JSON 示例：

```json
{
  "schemaVersion": 1,
  "revision": 42,
  "nodes": [
    {"id":"start","x":64,"y":80,"width":160,"height":72,"title":"开始"}
  ],
  "edges": []
}
```

序列化读取必须：检查 schema、拒绝重复 ID/非有限数字/悬空边、设置节点与字符串数量上限，然后迁移到当前版本。自动保存从不可变快照开始，在后台写临时文件并 `fsync` 后原子替换；用 revision 防止旧任务覆盖新文档。

相机矩阵可仿第三章保存 9 个 float，恢复到新尺寸后约束。选择集合只保存仍存在的稳定 ID。undo 栈是否持久化是产品决策；通常进程死亡后只恢复文档，不恢复完整历史。

## 性能工程

> **性能提示**：不要凭“节点很多”就开软件层或缓存整个无限画布。先记录帧时间、对象分配、可见元素数量和索引查询耗时，再定位瓶颈。

生产预算建议：

- 主线程每次 MOVE：逆变换、索引候选查询、吸附候选、更新 transient overlay，目标 < 4ms。
- 只绘制 world viewport 与预取边界相交的元素。
- 文本布局按 `(nodeId,title,width,textStyle)` 缓存，标题变化时失效。
- 连接路由在 worker 线程根据 immutable snapshot 计算；结果带 revision，过期即丢弃。
- 索引在节点提交移动后增量更新，不在每帧 rebuild。示例中的全量 rebuild 仅适合教学规模。
- 大型操作批量成一个命令和一次状态发布，避免观察者风暴。
- 性能追踪用 `Trace.beginSection("diagram.draw")`/Perfetto 和 Macrobenchmark。

### 一致性与并发

后台路由结果格式应为 `(revision, edgePaths)`。主线程仅当结果 revision 等于当前文档 revision 时交换缓存。Renderer 在一帧中读取同一个 `SceneSnapshot`，不能一半节点来自 r10、另一半边来自 r11。

## 测试策略

### 纯 JVM 测试

- 文档校验：重复/悬空/自环/NaN 数据被拒绝。
- `MoveNodesCommand.apply` 后 `revert` 恢复结构相等。
- undo 后执行新命令，redo 栈清空。
- 相机正反变换误差、缩放边界、屏幕容差转换。
- 网格索引查询不漏掉跨桶节点，允许误报但精确过滤后无误报。
- 吸附阈值边界和负坐标网格。

```kotlin
@Test fun moveCommandRoundTrips() {
    val before = fixtureDocument()
    val id = NodeId("a")
    val command = MoveNodesCommand(
        from = mapOf(id to requireNotNull(before.nodes[id]).position),
        to = mapOf(id to Vec2(320f, 160f))
    )
    assertThat(command.revert(command.apply(before)).nodes)
        .isEqualTo(before.nodes)
}
```

### 仪器化与端到端

1. 注入拖动序列，MOVE 期间文档 revision 不变，UP 后只增加一次。
2. CANCEL 丢弃 transient overlay，不产生 undo 项。
3. 双指缩放时 SelectionTool 收到 cancel，节点不误移动。
4. 无障碍虚拟节点 bounds 随相机变化，点击动作选择正确 ID。
5. JSON 损坏、旧版本迁移、原子写中断都有恢复测试。
6. Macrobenchmark 使用固定生成器构造 100/1k/10k 节点，报告 P50/P95 帧时间与内存；不要只给“流畅”结论。
7. 截图测试覆盖缩放、吸附线、选框、RTL 标题、深色/高对比主题。

### 属性测试

随机生成合法文档与命令序列，验证：

```text
revert(apply(doc, command), command) == doc
all edge endpoints exist after every committed command
viewToWorld(worldToView(p)) ~= p
spatialIndex(query(node.bounds)) contains node.id
```

## 常见陷阱

- **布尔状态爆炸**：`isDragging/isConnecting/isPanning` 可同时为真；改为互斥 Tool 状态。
- **MOVE 直接改模型**：撤销栈上千条、后台任务泛滥；用 transient overlay，UP 提交。
- **屏幕坐标入库**：缩放后数据变形；模型只保存世界坐标。
- **命中不走逆矩阵**：缩放和平移后选错对象。
- **删除节点留下边**：文档不变量被破坏；用原子复合命令。
- **虚拟 ID 用列表索引**：排序后 TalkBack 焦点跳动；映射稳定业务 ID。
- **SavedState 塞整个文档**：Binder 事务过大；只放引用和小 UI 状态。
- **后台直接读可变 Map**：竞态崩溃；传不可变 snapshot 和 revision。

## 实践检查清单

- [ ] View、控制器、文档、Renderer、Repository 职责分离
- [ ] 工具是显式状态机，CANCEL 有定义
- [ ] 预览状态与提交命令分离
- [ ] 坐标空间统一，命中使用逆矩阵
- [ ] 文档不变量在每次提交后成立
- [ ] 可见裁剪、索引、缓存均有失效策略
- [ ] 虚拟无障碍节点稳定，并有列表替代入口
- [ ] 大文档持久化有版本、限额、原子写和冲突保护

## 扩展练习

1. 实现框选工具：从屏幕拖拽矩形反变换到世界区域，定义“相交”与“完全包含”模式。
2. 实现连接工具：端口命中、拖线预览、循环依赖校验与创建命令。
3. 将 Grid 索引替换为 R-tree，比较超大节点与稀疏场景。
4. 实现正交连线路由，后台计算并用 revision 丢弃过期结果。
5. 添加协作编辑：命令携带 actor/lamport 时间，研究 CRDT 与本地 undo 语义。
6. 用 Compose 实现工具栏与属性面板，View 画布通过稳定 controller 互操作。

## 小结

生产级编辑器首先是架构问题，其次才是绘制问题。不可变文档保证一致性，工具状态机约束输入，命令系统承载撤销，场景图与空间索引保障规模，相机正逆变换统一视觉和命中。把这些边界建立后，新增节点类型、连线工具和协作能力才不会让一个 View 演化成无法测试的巨型类。

## 延伸阅读

- [自定义 View 无障碍](https://developer.android.com/guide/topics/ui/accessibility/custom-views)
- [ExploreByTouchHelper](https://developer.android.com/reference/androidx/customview/widget/ExploreByTouchHelper)
- [保存界面状态](https://developer.android.com/topic/libraries/architecture/saving-states)
- [Android 性能分析概览](https://developer.android.com/topic/performance)
