# 事件速查表

## 1. 触摸序列

```text
DOWN ── MOVE* ── POINTER_DOWN/MOVE/POINTER_UP* ── UP
  └──────────────── 任意时刻可被 CANCEL 终止 ─────────┘
```

| `actionMasked` | 含义 | 必做事项 |
|---|---|---|
| `ACTION_DOWN` | 手势序列开始 | 命中测试、记录 pointer ID、决定是否消费 |
| `ACTION_MOVE` | 一个或多个指针移动 | 用 ID 找 index；超过 touch slop 后再拖动 |
| `ACTION_POINTER_DOWN` | 非首指按下 | 读取 `actionIndex`，更新多指状态 |
| `ACTION_POINTER_UP` | 非末指抬起 | 若是活动指针，切换并重置 last 坐标 |
| `ACTION_UP` | 最后一指抬起 | 点击则 `performClick()`；清理状态/速度跟踪 |
| `ACTION_CANCEL` | 序列被系统或父容器取消 | 不提交点击；撤销 pressed；完整清理 |
| `ACTION_OUTSIDE` | 窗口外事件（特定窗口场景） | 普通 View 不应依赖它结束手势 |

> **注意**：`event.action` 包含 pointer index 位；分支判断通常使用 `actionMasked`。

## 2. pointer ID 与 index

```kotlin
val id = event.getPointerId(index)       // 稳定身份
val indexNow = event.findPointerIndex(id) // 每个事件重新查
if (indexNow >= 0) {
    val x = event.getX(indexNow)
    val y = event.getY(indexNow)
}
```

- ID 跨同一手势序列追踪某根手指；index 只是当前事件数组下标。
- `ACTION_POINTER_UP` 的抬起指针仍出现在该事件数组中，位置由 `actionIndex` 指明。
- 不要假定 ID 从 0 连续增长，也不要缓存 index 跨事件使用。

## 3. 坐标、历史点与轴

| API | 坐标空间/含义 |
|---|---|
| `x/y`、`getX/Y(index)` | 接收 View 的局部坐标 |
| `rawX/rawY` | 屏幕坐标语义；跨窗口/变换时谨慎 |
| `historySize` | MOVE 合批的历史样本数 |
| `getHistoricalX/Y` | 历史位置，可改善笔迹连续性 |
| `getAxisValue(axis)` | 鼠标滚轮、触控笔等通用轴值 |
| `source` | 输入源位掩码 |
| `toolType` | 手指、触控笔、鼠标、橡皮等工具类型 |

命中测试若内容经过 Matrix 变换，优先将触点逆变换到内容空间，而不是只映射对象包围盒。

## 4. 分发与拦截

```text
Activity/Window
    ↓ dispatchTouchEvent
ViewGroup.dispatchTouchEvent
    ├─ onInterceptTouchEvent == false → child.dispatchTouchEvent
    └─ onInterceptTouchEvent == true  → 该 ViewGroup 自身消费：
                                       后续事件交给自己的 onTouchEvent
```

`onInterceptTouchEvent` 返回 `true` 时，事件由**该 ViewGroup 自己**消费——它的 `onTouchEvent` 在自身调用，而不是“parent”。用“父容器”表述会让人误以为事件向上抛给了更外层的容器。实际上被拦截后原目标子 View 会收到 `CANCEL`，该 ViewGroup 从此接管整段序列，直到 `UP`/`CANCEL`。

| 返回值/动作 | 后果 |
|---|---|
| DOWN 返回 `true` | 当前目标愿意接收后续序列 |
| DOWN 返回 `false` | 当前 View 通常不会继续收到该序列 |
| 父容器中途拦截 | 原目标 View 收到 CANCEL，后续交给父容器 |
| `requestDisallowInterceptTouchEvent(true)` | 请求祖先暂不拦截，不等于全局锁定 |
| `onTouchListener` 返回 `true` | 消费事件，View 的 `onTouchEvent()` 不再处理它 |

容器策略：DOWN 先观察；MOVE 超过 touch slop 且方向明确后拦截；一旦拦截，保持到 UP/CANCEL，避免目标反复切换。

## 5. 点击、长按、拖动与 fling

| 交互 | 推荐组件/阈值 |
|---|---|
| 点击/双击/长按 | `GestureDetector` + `performClick()` |
| 拖动 | `ViewConfiguration.scaledTouchSlop` 后进入拖动态 |
| 缩放 | `ScaleGestureDetector` |
| 旋转 | 两指向量夹角；处理跨 ±180° 归一化 |
| 速度 | `VelocityTracker` |
| 惯性滚动 | `OverScroller` 或受控物理动画 |
| 边缘反馈 | `EdgeEffect`，并考虑拉伸/颜色/API 差异 |
| 嵌套滚动 | AndroidX `NestedScrollingChild/Parent` 协议 |

VelocityTracker 模板：

```kotlin
var tracker: VelocityTracker? = null

// DOWN
tracker = VelocityTracker.obtain().also { it.addMovement(event) }
// 每个后续事件
tracker?.addMovement(event)
// UP
tracker?.computeCurrentVelocity(
    1000,
    ViewConfiguration.get(context).scaledMaximumFlingVelocity.toFloat(),
)
val vx = tracker?.getXVelocity(activePointerId) ?: 0f
tracker?.recycle()
tracker = null
```

比较是否 fling 时使用 `abs(vx) >= scaledMinimumFlingVelocity`，并按控件方向、边界和当前缩放折算速度。

## 6. 多点状态切换

```text
IDLE --DOWN--> POSSIBLE_CLICK --超过 slop--> DRAG
  ^                 | POINTER_DOWN              |
  |                 v                           |
  +--UP/CANCEL-- TRANSFORM(缩放/旋转) --UP/CANCEL+
```

- 模式切换时重置 last/focus/span，避免首帧跳变。
- 多指减少到单指后，明确选择继续拖动还是结束本次变换。
- detector 应看到完整事件流；不要只在 MOVE 时传入。
- 同时识别缩放与拖动时，以焦点变化处理平移，以 span/角度处理缩放旋转。

## 7. 非触摸输入

| 输入 | 入口 | 检查 |
|---|---|---|
| 键盘/D-pad | `onKeyDown/Up`、焦点 API | Enter/Space 激活，方向键移动焦点 |
| 鼠标按钮 | `onGenericMotionEvent`/按键状态 | hover、右键、滚轮，不假设只有触摸 |
| hover | `onHoverEvent` | TalkBack 触摸探索也使用 hover 语义 |
| 触控笔 | toolType、压力、倾斜、按钮 | 能力因设备而异，提供降级路径 |
| 旋钮/滚轮 | `ACTION_SCROLL` + axis | 读取 source 与对应 axis |
| IME | `InputConnection` 等 | 仅真正的文本编辑控件实现完整协议 |

## 8. 无障碍输入契约

- 可点击 View：`isClickable = true`，最终调用 `performClick()`，并在 override 中调用 `super.performClick()`。
- 键盘可操作：合理 `focusable`，视觉焦点清晰，Enter/Space 与无障碍 ACTION_CLICK 等价。
- 单个 Canvas 中多个交互对象：使用 `ExploreByTouchHelper` 暴露虚拟节点、边界、文本/描述、状态和动作。
- 触摸目标不应仅靠视觉大小判断；必要时用 `TouchDelegate` 扩大命中区，但语义边界也要合理。
- 不以颜色、手势或动画作为唯一信息通道；提供标签、动作和替代路径。

## 9. 故障定位

| 症状 | 优先检查 |
|---|---|
| 只收到 DOWN | DOWN 是否返回 true；父容器是否拦截 |
| 拖动首帧跳跃 | 模式切换/活动指针切换后是否重置 last 坐标 |
| 第二指抬起后崩溃 | 是否把 pointer ID 当 index；是否检查 `findPointerIndex` |
| 点击无 TalkBack 反馈 | 是否调用 `performClick()` 与 super |
| 滑动与父列表冲突 | touch slop、方向锁、disallowIntercept 或 nested scrolling |
| fling 方向错误 | 内容坐标与手指坐标符号是否混淆 |
| 笔迹断裂 | 是否读取历史批次、是否正确处理 CANCEL/边界 |
| 缩放后命中偏移 | 正逆 Matrix 是否同步，坐标空间是否一致 |

## 10. 最小清理清单

- [ ] UP 与 CANCEL 都释放 pressed、pointer、VelocityTracker、临时回调。
- [ ] 所有 pointer 查询都检查 index 是否 `>= 0`。
- [ ] 点击走 `performClick()`，不是只调用业务 listener。
- [ ] 阈值来自 `ViewConfiguration`，不写死 px。
- [ ] 真机覆盖 1 指、2 指、快速切指、来电/手势导航 CANCEL。
- [ ] 覆盖 TalkBack、键盘、鼠标/触控板（若产品声明支持）。

## 延伸阅读

- [触摸手势](https://developer.android.com/develop/ui/views/touch-and-input/gestures)
- [在 ViewGroup 中管理触摸事件](https://developer.android.com/develop/ui/views/touch-and-input/gestures/viewgroup)
- [跟踪触摸与指针移动](https://developer.android.com/develop/ui/views/touch-and-input/gestures/movement)
- [MotionEvent API](https://developer.android.com/reference/android/view/MotionEvent)
