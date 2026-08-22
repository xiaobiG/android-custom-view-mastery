# 输入、嵌套滚动与测试互操作

`AndroidView` 让两套 UI 树共享一个窗口，但并未把输入、滚动协议、语义和测试查询合并成
一棵树。触摸事件最终进入真实 View；Compose 修饰符位于它的外层。嵌套滚动需要双方都遵守
协议；测试时 Compose 节点与 View matcher 也必须分别查询。

## 学习目标

- 理解 Compose 修饰符与 Android View 之间的输入边界。
- 使用 `AndroidView` 自带的互操作桥连接 `NestedScrollingChild` 与 Compose 父容器，并区分
  方向相反的 `rememberNestedScrollInteropConnection()`。
- 处理点击、拖拽、焦点、键盘与无障碍语义的职责划分。
- 在同一测试中正确组合 Compose Test 与 Espresso，并处理同步边界。

## 1. 输入命中与消费边界

当指针命中 `AndroidView` 时，可以把路径理解为：

```text
窗口 MotionEvent
      │
      ▼
Compose 外层 Modifier
(pointerInput / nestedScroll / clickable ...)
      │ 未消费或继续派发
      ▼
AndroidViewHolder
      │ MotionEvent
      ▼
真实 View.dispatchTouchEvent()
      ├── ViewGroup.onInterceptTouchEvent()
      └── View.onTouchEvent()
```

不要在同一区域让 Compose `clickable` 与 View `OnClickListener` 同时表达同一业务点击。它们
可能竞争消费、产生双回调，并形成两个无障碍动作。通常选择一个所有者：

- 手势由旧 View 完整实现：Compose 只提供布局，事件从 View listener 上报。
- 手势迁移到 Compose：旧 View 退化为纯渲染表面，不再处理同一手势。
- 需要外层拦截（例如埋点/调试）时，不改变消费结果，并明确验证多指与取消事件。

## 2. 嵌套滚动互操作

Android 侧嵌套滚动（nested scrolling）由 parent/child 协议传递预滚动、剩余滚动与 fling。
当 `AndroidView` 内的根 View 是 `NestedScrollingChild`（如 `RecyclerView`）且外层 Compose
需要参与滚动时，启用该 View 的 nested scrolling，并让 Compose 父级安装自己的
`NestedScrollConnection`。`AndroidView` 会在两者之间桥接滚动增量；**不要**在这个方向使用
`rememberNestedScrollInteropConnection()`：该 API 专用于“View `NestedScrollingParent3` 父级 +
Compose 滚动子级”的反向场景。

```kotlin
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.viewinterop.AndroidView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LegacyFeedScreen(
    adapter: RecyclerView.Adapter<out RecyclerView.ViewHolder>
) {
    val behavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val density = LocalDensity.current

    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .nestedScroll(behavior.nestedScrollConnection),
        topBar = {
            TopAppBar(
                title = { androidx.compose.material3.Text("动态") },
                scrollBehavior = behavior
            )
        }
    ) { padding ->
        val topPaddingPx = with(density) {
            padding.calculateTopPadding().roundToPx()
        }
        AndroidView(
            modifier = Modifier
                .fillMaxSize(),
            factory = { context ->
                RecyclerView(context).apply {
                    layoutManager = LinearLayoutManager(context)
                    isNestedScrollingEnabled = true
                    this.adapter = adapter
                    setPadding(0, topPaddingPx, 0, 0)
                    clipToPadding = false
                }
            },
            update = { recycler ->
                if (recycler.adapter !== adapter) recycler.adapter = adapter
            },
            onRelease = { recycler ->
                recycler.adapter = null
            }
        )
    }
}
```

上例省略了底部/左右 inset 以突出协议，生产代码应完整应用 `PaddingValues`。代码在
`LocalDensity` 作用域内把 dp 转换成像素，避免在 View 中误用 dp。

更稳妥、可直接编译的 inset 转换写法如下：

```kotlin
val density = androidx.compose.ui.platform.LocalDensity.current
val topPx = with(density) { padding.calculateTopPadding().roundToPx() }
AndroidView(
    modifier = Modifier.fillMaxSize(),
    factory = { context ->
        RecyclerView(context).apply {
            isNestedScrollingEnabled = true
        }
    },
    update = { it.setPadding(0, topPx, 0, 0) }
)
```

> **版本与方向边界**：本节依赖 `androidx.compose.ui:ui` 的 `AndroidView` nested-scroll
> interop，以及 AndroidX Core 的 `NestedScrollingChild` 协议；具体版本由项目 BOM/version
> catalog 锁定并用滚动集成测试验证。`rememberNestedScrollInteropConnection()` 的公开契约是
> “Compose 子级向实现 `NestedScrollingParent3` 的 View 父级派发”，不能拿来替代本例的
> “Android View 子级向 Compose 父级派发”。内部 View 仍必须启用并正确实现 nested scrolling
> child API；自定义 View 若只在 `onTouchEvent` 修改坐标，外层不会凭空收到 pre-scroll 或 fling。

### 2.1 调试嵌套滚动

按以下顺序定位：

1. 不加外层 Compose 手势，确认 View 自己能滚动。
2. 确认 `isNestedScrollingEnabled == true`，并检查轴向是否一致。
3. 记录 down/move/up/cancel，确认没有父层过早消费 down。
4. 分别记录 pre-scroll、post-scroll、pre-fling、fling 的 consumed/available。
5. 测试到顶、到底、快速 fling、反向拖动与多指切换。

```text
手指 dy
  │
  ├─ preScroll ──> Compose parent 消费 A
  │
  ├─ 剩余 dy-A ──> Android View 自己消费 B
  │
  └─ postScroll ─> parent 获得 consumed=B / available=dy-A-B
```

## 3. 焦点、键盘与输入法

Compose focus 与 View focus 最终共享窗口焦点，但 API 不同。建议边界组件显式提供“请求焦点”
事件，而不是在每次 `update` 中调用 `requestFocus()`：

```kotlin
import android.view.inputmethod.InputMethodManager
import androidx.core.widget.doAfterTextChanged
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun LegacySearchField(
    query: String,
    focusRequestId: Long,
    onQueryChange: (String) -> Unit
) {
    val latestChange = rememberUpdatedState(onQueryChange)
    val fieldState = remember { mutableStateOf<LegacySearchEditText?>(null) }

    AndroidView(
        factory = { context ->
            LegacySearchEditText(context).apply {
                doAfterTextChanged { latestChange.value(it?.toString().orEmpty()) }
                fieldState.value = this
            }
        },
        update = { view ->
            fieldState.value = view
            if (view.text.toString() != query) {
                view.setText(query)
                view.setSelection(query.length)
            }
        },
        onRelease = { view ->
            view.clearFocus()
            if (fieldState.value === view) fieldState.value = null
        }
    )

    val field = fieldState.value
    LaunchedEffect(focusRequestId, field) {
        field?.let { view ->
            view.requestFocus()
            val imm = view.context.getSystemService(InputMethodManager::class.java)
            imm.showSoftInput(view, InputMethodManager.SHOW_IMPLICIT)
        }
    }
}
```

这个引用只存在于边界 Composable，并在释放时清空；绝不能把 View 引用放进 `ViewModel`。
若无需强制拉起 IME，优先让用户点击自然获得焦点。

> **无障碍提示**：不要同时给外层 Compose 节点和内部 View 设置重复的可点击语义。使用
> TalkBack 与键盘实际遍历，检查是否出现两个同名焦点、焦点陷阱或错误的遍历顺序。

## 4. 两棵测试树

在测试中，互操作边界仍是两套查询系统：

```text
ComposeTestRule
  └─ Semantics tree: onNodeWithTag("chart-host")
       └─ AndroidView 边界（不会展开成 View matcher）

Espresso
  └─ View hierarchy: onView(withTagValue("legacy-chart"))
       └─ ChartView / 其 View 子节点
```

Compose 测试用于外层语义、布局状态和 Compose 交互；Espresso 用于内部 View 的 ID、tag、
文本与自定义 matcher。不要期待 `onNodeWithText()` 找到 Android `TextView`，也不要期待
Espresso `withText()` 找到纯 Compose `Text`。

## 5. Espresso + Compose 完整边界测试

下面示例使用 `createAndroidComposeRule<ComponentActivity>()`，先通过 Compose 点击切换状态，
再由 Espresso 检查同屏的旧 View，最后执行 View 点击并回到 Compose 断言结果。

```kotlin
import android.view.View
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.viewinterop.AndroidView
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withTagValue
import org.hamcrest.CoreMatchers.`is`
import org.junit.Rule
import org.junit.Test

class InteropCounterTest {
    @get:Rule
    val rule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun composeAndView_shareOneState() {
        rule.setContent {
            var count by remember { mutableIntStateOf(0) }

            Column {
                Text(
                    text = "count=$count",
                    modifier = Modifier.testTag("count")
                )
                Button(
                    onClick = { count++ },
                    modifier = Modifier.testTag("compose-add")
                ) { Text("Compose +1") }

                AndroidView(
                    modifier = Modifier.testTag("legacy-host"),
                    factory = { context ->
                        LegacyCounterButton(context).apply {
                            tag = "legacy-add"
                            setOnClickListener { count++ }
                        }
                    },
                    update = { it.renderCount(count) }
                )
            }
        }

        rule.onNodeWithTag("compose-add").performClick()
        rule.onNodeWithTag("count").assertTextEquals("count=1")

        onView(withTagValue(`is`("legacy-add")))
            .check(matches(isDisplayed()))
            .perform(click())

        rule.onNodeWithTag("count").assertTextEquals("count=2")
    }
}
```

实际项目应给 View 使用稳定资源 ID；tag 只为示例避免依赖资源文件。自定义绘制内容无法用
`withText()` 查询时，应让 View 暴露可访问状态，或编写类型安全的自定义 matcher：

```kotlin
import android.view.View
import org.hamcrest.Description
import org.hamcrest.TypeSafeMatcher

fun withRenderedCount(expected: Int) = object : TypeSafeMatcher<View>() {
    override fun describeTo(description: Description) {
        description.appendText("LegacyCounterButton renderedCount=$expected")
    }

    override fun matchesSafely(view: View): Boolean =
        view is LegacyCounterButton && view.renderedCount == expected
}
```

## 6. 同步与异步边界

Compose rule 和 Espresso 能等待各自已登记的主线程/重组工作，但不会自动理解自定义线程、
播放器、网络回调或 View 内部长期动画。测试不能用固定 `Thread.sleep()` 猜完成时间。

选择方式：

- 异步结果最终进入 Compose state：用 `waitUntil` 等待可观察状态/语义。
- 旧 View 在后台加载：为该组件提供 Espresso `IdlingResource`。
- 动画只影响视觉：关闭系统动画或提供可注入时钟/立即完成模式。
- 跨边界操作后：先让对应框架执行动作，再由目标树断言；避免缓存旧 View 引用。

> **注意**：不要对同一事实在两棵树都做脆弱断言。测试边界契约：状态是否传入、用户事件
> 是否传出；View 自身的细节行为留给纯 Espresso 测试，Compose 外层留给 Compose 测试。

## 7. 常见陷阱

| 陷阱 | 结果 | 修复 |
|---|---|---|
| 外层 `clickable` 与 View 点击并存 | 双回调或事件丢失 | 为每个手势指定唯一所有者 |
| 把 `rememberNestedScrollInteropConnection()` 加到 `AndroidView` | 用反了桥接方向，Compose 父级仍收不到正确协议 | 依赖 `AndroidView` 桥接；View 启用 child，Compose 父级安装自己的 connection |
| `update` 每次 `requestFocus()` | 键盘反复弹出、焦点抢夺 | 用一次性事件或显式请求 ID |
| Compose 查询内部 TextView | 节点找不到 | 内部 View 用 Espresso 查询 |
| Espresso 查询 Compose Text | matcher 找不到 | Compose 内容用 semantics 查询 |
| 用 sleep 等异步 | 慢且偶发失败 | `waitUntil` 或 `IdlingResource` |
| 只测慢速拖动 | fling/边界仍有 bug | 覆盖边界、反向与快速 fling |

## 8. 实践检查清单

- [ ] 每种点击/拖拽只有一个输入所有者。
- [ ] 嵌套滚动 child 已启用，pre/post scroll 与 fling 均验证。
- [ ] 焦点请求由事件触发，不在每次 `update` 抢焦点。
- [ ] 无障碍遍历不存在内外重复语义。
- [ ] Compose 语义用 Compose Test，内部 View 用 Espresso。
- [ ] 自定义异步工作注册 idling 机制，没有固定 sleep。
- [ ] 测试覆盖状态向下同步和用户事件向上回传。

## 小结

互操作共享窗口，却保留输入协议和测试树的边界。嵌套滚动必须由 Compose connection 与
Android nested scrolling child 双方配合；焦点和点击应有唯一所有者；测试则分别使用
Compose semantics 与 Espresso View matcher，并通过可观测状态或 idling resource 同步。

## 延伸阅读

- [嵌套滚动互操作](https://developer.android.com/develop/ui/compose/touch-input/pointer-input/scroll#nested-scrolling-interop)
- [Compose 测试](https://developer.android.com/develop/ui/compose/testing)
- [Espresso](https://developer.android.com/training/testing/espresso)
- [Compose 与 View 互操作测试](https://developer.android.com/develop/ui/compose/testing/interoperability)
