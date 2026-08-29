# ComposeView 反向互操作

> 本章定位：在仍以 View/XML 为主的界面里嵌入 Compose 内容，理解 `ComposeView` 的
> 生命周期桥接、组合复用行为，以及输入法、嵌套滚动、触摸边界在混合层级下的表现。

## 学习目标

- 把 `ComposeView` 放进 XML 布局，并正确设置 `setContent` 与组合策略。
- 理解 `ViewTreeLifecycleOwner` 等桥接为何由 `ComponentActivity` 自动提供。
- 处理 `ComposeView` 在 `RecyclerView` 复用中的组合状态与 `remember` 问题。
- 知道输入法、嵌套滚动、触摸命中在 View/Compose 边界上的行为差异。
- 用对比表明确"反向互操作（ComposeView）"与"正向互操作（AndroidView）"的分工。

## 问题场景：渐进引入 Compose

大多数项目不会一夜迁完。当某些界面想先用 Compose 提速迭代，而宿主仍是传统
Activity/XML 时，就需要把 Compose 内容"装进"一个 View 里：这个 View 就是
**`ComposeView`**（`androidx.compose.ui.platform.ComposeView`，继承
`AbstractComposeView`，本身是一个 `ViewGroup`）。它的角色是反向互操作：

```text
传统 View 树（Activity / Fragment / RecyclerView item）
        │
        ▼
  ┌─ ComposeView（一个普通 View）─────────┐
  │  │                                   │
  │  ├─ 拥有自己的 Composition           │
  │  ├─ 组合的生命周期与 View 绑定        │
  │  └─ 内部完全运行 Compose UI           │
  └──────────────────────────────────────┘
```

正向互操作（`AndroidView` 把传统 View 放进 Compose）与反向互操作常同时出现在迁移期，
两者的边界正好相反（见对比表）。

> **注意**：`ComposeView` 属于 Compose UI 运行时，依赖 `androidx.compose.ui:ui`；
> 若还想用 `ComponentActivity.setContent` 这种更简短的写法，还需要
> `androidx.activity:activity-compose`。`ComposeView` 自 Compose 1.0 起为稳定 API，
> `ViewCompositionStrategy` 自 1.1.0 引入；依赖与 Kotlin、AGP 的兼容矩阵以你锁定的
> Compose BOM 版本为准（本章示例基于 Compose 1.x 稳定版语义）。

## 核心机制：组合生命周期与 View 生命周期

Compose 的"组合（composition）"和 View 的"attach 生命周期"不是一回事，`ComposeView`
把两者桥接起来：

```text
ComposeView 创建
   │  setContent { ... }  记录内容 lambda
   ▼
onAttachedToWindow
   │  按 ViewCompositionStrategy 决定何时创建组合
   ▼
Composition 创建并执行 Composable
   │  remember{} 状态、LaunchedEffect、DisposableEffect 生效
   ▼
onDetachedFromWindow
   │  按策略决定是否销毁组合
   ▼
Composition 销毁（DisposableEffect.onDispose 触发）
```

### `setContent` 与生命周期桥接

在传统 View 树里，Compose 需要一个 `LifecycleOwner`、`SavedStateRegistryOwner` 与
`OnBackPressedDispatcherOwner`，用来驱动 `remember` 之外的组合副作用、保存状态和处理
返回键。`ComponentActivity.setContent` 会把这些 `ViewTree*Owner` 挂到窗口根视图上：

- `ViewTreeLifecycleOwner.set(...)`（生命周期桥接）
- `ViewTreeSavedStateRegistryOwner.set(...)`（`rememberSaveable` 依赖它）
- `ViewTreeOnBackPressedDispatcherOwner.set(...)`（返回键分派）

因此只要 Activity 用 `setContent` 建立过 Compose 树，或宿主是 `ComponentActivity`，
XML 里的 `ComposeView` 就能自动找到这些 Owner。**在非 `ComponentActivity`、或
Fragment 视图等场景，Owner 的来源不同**：Fragment 自 1.2.0 起为视图树提供
`LifecycleOwner`（SavedState/OnBackPressed 的 ViewTree 属性由对应 AndroidX 组件
设置）。若缺失，组合内部使用 `LocalLifecycleOwner` 的地方会在运行时报错。

```xml
<!-- activity_main.xml -->
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:orientation="vertical"
    android:layout_width="match_parent"
    android:layout_height="match_parent">

  <TextView
      android:id="@+id/legacy_text"
      android:layout_width="wrap_content"
      android:layout_height="wrap_content" />

  <androidx.compose.ui.platform.ComposeView
      android:id="@+id/compose_section"
      android:layout_width="match_parent"
      android:layout_height="0dp"
      android:layout_weight="1" />

</LinearLayout>
```

```kotlin
class MixedActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        findViewById<ComposeView>(R.id.compose_section).apply {
            setViewCompositionStrategy(
                ViewCompositionStrategy.DisposeOnDetachedFromWindowOrReleasedFromPool
            )
            setContent {
                MaterialTheme {
                    ComposePanel() // 你的 Composable 内容
                }
            }
        }
    }
}
```

> **注意**：`setContent` 不要求 Activity 一定用 `ComponentActivity.setContent`——只要
> View 树里有正确的 `ViewTree*Owner` 即可。把 `ComposeView` 放进 XML 后，用
> `findViewById` 找到它再 `setContent` 是最常见的接入方式。

### `ViewCompositionStrategy`：组合何时销毁

`AbstractComposeView.setViewCompositionStrategy(...)` 决定组合销毁时机，官方文档给出
几个选项：

| 策略 | 行为 | 适用场景 |
|---|---|---|
| `DisposeOnDetachedFromWindow`（已弃用） | 脱离窗口即销毁 | 已被下者取代 |
| `DisposeOnDetachedFromWindowOrReleasedFromPool`（默认） | 脱离窗口即销毁；**但作为 RecyclerView 等池化容器的条目时，保留到容器脱离窗口或条目被淘汰** | View 树/混合屏、RecyclerView 条目 |
| `DisposeOnLifecycleDestroyed` | 随给定 `Lifecycle` 销毁 | Fragment 视图（手头有明确 Lifecycle） |
| `DisposeOnViewTreeLifecycleDestroyed` | 随 `ViewTreeLifecycleOwner` 的 Lifecycle 销毁 | Fragment 视图、LifecycleOwner 尚不明确时 |

Fragment 里嵌入 `ComposeView` 时推荐
`DisposeOnViewTreeLifecycleDestroyed`，让组合生命周期跟 Fragment 视图一致，避免
Fragment 已销毁而组合残留。

> **注意**：默认策略在不同 Compose 版本之间有过行为调整（例如池化容器的判定逻辑），
> 依赖"默认行为"的代码应显式声明策略，并在升级 Compose 版本后回归验证。

## ComposeView 在 RecyclerView 复用中的注意点

把 `ComposeView` 作为 RecyclerView 的 item 是常见的迁移手段，也是最容易踩坑的地方。

### 组合状态与 `remember` 复用冲突

默认策略 `DisposeOnDetachedFromWindowOrReleasedFromPool` 会让组合在条目回收后**仍然
存活**（只要还留在池里）。这意味着：

```text
条目滚动出屏 → View 进入池（组合保留，remember{} 状态保留）
条目滚动回屏 → 复用同一个 ComposeView（组合还在，还是旧数据！）
```

结果就是经典的"列表串项"：`remember { mutableStateOf(...) }` 里的旧条目数据被复用。
修复方向有三个，按推荐排序：

1. **把每项状态提升到条目之外**，用可观察状态驱动，`onBindViewHolder` 只更新状态源：
   ```kotlin
   // Adapter.onBindViewHolder
   holder.composeView.setContent {
       val item = itemStates[position]   // 或 collect 某个 Flow/State
       ItemCard(item = item, onOpen = { onClick(position) })
   }
   ```
   组合观察到状态变化后自动重组，不用每次重建组合。
2. **用 `key(item.id)` 包住内容**，让条目身份变化时重置内部 `remember`：
   ```kotlin
   holder.composeView.setContent {
       key(item.id) {
           ItemCard(item = item, onOpen = { onClick(item.id) })
       }
   }
   ```
3. 需要彻底丢弃组合时，显式调用 `disposeComposition()` 或改用会销毁的策略。

### 不要在每次 bind 都重建组合

`setContent` 在已 attach 且已有组合的 `ComposeView` 上调用会替换内容并重建组合，
是昂贵且易丢状态的。正确姿势是：**在 `onCreateViewHolder` 阶段创建组合一次**，之后
`onBindViewHolder` 只更新可观察状态；或保证 `setContent` 幂等、内容 lambda 足够稳定。

> **性能提示**：列表条目频繁进出屏幕时，组合的创建/销毁本身有成本。条目内容简单时，
> 整页用 Compose、item 用 `LazyColumn` 往往优于"每个 item 一个 ComposeView"；条目
> 确实复杂时，至少把组合创建控制在"每个 ViewHolder 一次"。

### 保存状态

同一布局有多个 `ComposeView` 时，每个都要有唯一 ID，`rememberSaveable` 的实例状态
才能正确保存/恢复。

## 输入法、嵌套滚动与触摸边界

### 输入法与软键盘

Compose 侧用 `Modifier.imePadding()` 响应输入法 insets，但前提是窗口以
`adjustResize`（或等效）方式把 insets 发给视图，而不是 `adjustPan`。在
View/Compose 混合层级里：

- 输入法 insets 属于窗口级，ComposeView 无论嵌在哪都能读到；
- 但**边界上的滚动衔接**要小心：Compose 内容内部滚动 + 系统给 insets 时，应把
  `imePadding()` 放在滚动容器的修饰链上，而不是只给叶子组件。

> **注意**：混合界面里"输入框被键盘遮挡"的排查顺序：先确认 `windowSoftInputMode`，
> 再确认 `imePadding()` 挂在滚动容器上，最后用 `LocalWindowInfo` 打点验证 insets
> 是否真的下发了（不同 API 级别与厂商行为有差异，以真机验证为准）。

### 嵌套滚动

`Modifier.nestedScroll(...)` 只协调 Compose 内部的滚动层级；**View 与 Compose 之间
不存在自动的嵌套滚动协议**。当 `ComposeView` 放在 `ScrollView`/`RecyclerView` 里，
Compose 内部的滚动不会自动把剩余距离交给外层 View 容器。

可行的策略：

```text
场景 A：外层 View 滚动，ComposeView 内容不滚动
  -> 让 ComposeView 尺寸撑满内容，触摸事件由外层拦截即可，无需特殊处理

场景 B：ComposeView 内容自身要滚动
  -> 不在 View 滚动容器里嵌套可滚动 Compose；把滚动职责整体交给 Compose 侧，
     或用 Compose 的 LazyColumn 承接该区域

场景 C：必须在 View 容器里滚动 Compose 内容
  -> 在 onInterceptTouchEvent 层做事件仲裁，或评估把该区域提升为整页 Compose
```

### 触摸边界

`ComposeView` 是一个 View，参与 View 树的命中测试：

- 它覆盖的区域，触摸**不会自动穿透**到下面的传统 View；
- Compose 内容里没有 `clickable`/`pointerInput` 的空旷区域，通常不消费触摸，但
  `ComposeView` 本身仍是命中目标，下层 View 拿不到事件；
- 若需要"点击下层"，应调整布局让 `ComposeView` 只覆盖应有区域，而不是依赖穿透。

```text
┌──────────────────────────────┐
│ ComposeView（命中目标）      │  ← 手指按在这里
│   没有可交互元素            │
│   Compose 不消费             │  但传统 View 层也被挡住
└──────────────────────────────┘
```

## 与 AndroidView 正向互操作对比

| 维度 | ComposeView（反向互操作） | AndroidView（正向互操作） |
|---|---|---|
| 谁在主导 | View 树是宿主，内部跑 Compose | Compose 是宿主，内部包传统 View |
| 接入位置 | Activity/XML、RecyclerView 条目 | `@Composable` 内部 |
| 组合策略 | `ViewCompositionStrategy` 决定销毁时机 | `update`/`onReset`/`onRelease` 回调管理 |
| 生命周期 | 依赖 `ViewTreeLifecycleOwner` 等桥接 | 由组合生命周期驱动 |
| 典型坑 | 复用串项、`remember` 残留、策略错配 | 每次重组重建 View、`update` 不幂等 |
| 适用 | 渐进引入 Compose，页面仍以 View 为主 | 把成熟重型 View 包进 Compose 页面 |

两条路都服务于同一次迁移：**状态所有权应集中在一边**，另一侧只做受控显示与事件上报，
避免双向镜像状态。

## 常见陷阱

1. **`setContent` 每个 bind 都调用**：组合反复重建，状态丢失、性能浪费。
2. **复用条目串数据**：默认策略保留组合，`remember` 残留旧 item；用提升状态或
   `key(itemId)`。
3. **`ComposeView` 放在非 ComponentActivity/Fragment 外，Owner 缺失**：用到
   `LocalLifecycleOwner` 的地方崩溃；先确认 `ViewTree*Owner` 已提供。
4. **依赖默认组合策略**：版本升级后行为变化；显式声明策略并回归验证。
5. **在 View 滚动容器里嵌套可滚动 Compose**：嵌套滚动协议不互通，滚动卡顿或丢失。
6. **期望触摸穿透**：ComposeView 覆盖区域命中它自己；调整布局而非幻想穿透。
7. **多个 ComposeView 无唯一 ID**：`rememberSaveable` 保存状态失败或串扰。
8. **忽略输入法 insets 来源**：`adjustPan` 下 `imePadding()` 拿不到 insets。

## 实践检查清单

- [ ] 已确认 `androidx.compose.ui:ui` 与 `activity-compose` 依赖及版本兼容。
- [ ] `ComposeView` 场景下 `ViewTreeLifecycleOwner` 等桥接有明确来源。
- [ ] Fragment 场景使用 `DisposeOnViewTreeLifecycleDestroyed`。
- [ ] RecyclerView 条目组合只创建一次，数据通过可观察状态/`key` 驱动。
- [ ] 混合层级输入法、嵌套滚动、触摸边界已在真机验证。
- [ ] 每个 `ComposeView` 有唯一 ID，`rememberSaveable` 行为符合预期。
- [ ] 状态所有权明确（Compose 或 View 单侧持有），无双向镜像。

## 小结

`ComposeView` 让传统 View 页面能逐步长出 Compose 内容，但它不是"透明玻璃"：组合
生命周期要依赖 `ViewTree*Owner` 桥接，销毁时机由 `ViewCompositionStrategy` 决定，
RecyclerView 复用会保留组合导致 `remember` 串项，而输入法、嵌套滚动、触摸命中在
边界上各有一套不互通的语义。把这些边界当成正式契约对待，反向互操作才可控。

## 延伸阅读

- [在 View 中使用 Compose（官方）](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/compose-in-views)
- [ComposeView API](https://developer.android.com/reference/kotlin/androidx/compose/ui/platform/ComposeView)
- [ViewCompositionStrategy API](https://developer.android.com/reference/kotlin/androidx/compose/ui/platform/ViewCompositionStrategy)
- [Compose 与 View 互操作概览](https://developer.android.com/develop/ui/compose/migrate/interoperability-apis)
- [AndroidView 与状态同步](android-view.md)
