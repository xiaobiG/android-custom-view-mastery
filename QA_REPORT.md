# 质量验收报告

## 书稿规模

- `SUMMARY.md` 导航页面：58
- 非空白字符：379,818
- 正文行数：15,794
- Markdown 代码围栏标记：754（约 377 个代码或图示块）
- ASCII/text 图块：148，未发现超过 100 列的图
- 外部链接出现次数：335；唯一 URL：166
- 主要来源域名：`developer.android.com`、`cs.android.com`、`perfetto.dev`

## VitePress 构建

- VitePress：1.6.4
- 输出目录：`dist/`
- SUMMARY 导航页面：58/58 已生成且非空
- 总 HTML 页面：63（含导航外的构建、验收与写作辅助页面）
- 封面已输出为哈希化静态资源
- 本地搜索索引约 808 KB，保留以支持全书离线搜索
- 主题：默认文档主题 + 极简黑白 CSS；不使用自定义页面组件或动画

## 自动检查

```bash
npm run audit
npm run check
npm run build
git diff --check
```

验收结果：

- Critical 级 npm 审计门槛通过。
- 章节存在性、内部链接、最小章节长度、全书体量、标题和代码围栏检查通过：0 errors，0 warnings。
- VitePress 成功生成静态页面。
- `dist/` 中 58 个 SUMMARY 页面均有对应的非空 HTML 文件。
- 封面、主题 CSS、VitePress 本地搜索索引均已输出。
- Git 空白错误检查通过。
- 章节文本指纹检查未发现异常高相似度章节。

## 本地阅读

- Windows：运行 `read.cmd`
- 命令行：运行 `npm run read`
- 稳定阅读地址：`http://127.0.0.1:4000/`
- 编辑热更新：`npm run dev -- --port 4000`

阅读入口会在书稿较新或 `dist/` 缺失时自动检查并构建，随后用 Python 静态服务器提供内容。不要直接打开 `dist/index.html`。

## 人工/代理交叉审查

书稿按目录拆分并行编写后，另由独立审查代理分区复核：

- View/Measure/Layout/Draw、事件与 ViewGroup
- Canvas/Path/Matrix/文字/混合
- 动画、性能、状态与样式
- 无障碍、测试与 Compose 互操作
- 五个综合案例
- 附录、工具类、导航和参考资料

审查重点包括 Android/AndroidX API 名称与签名、坐标和矩阵结论、事件取消、多指 ID、生命周期释放、无障碍虚拟节点、测试 API、版本边界和文档排版。

## 已知边界

1. Markdown 中的代码既包含完整类，也包含教学片段；没有把所有片段拼成单一 Android App 编译。复制片段时需按正文说明补齐包名、资源和依赖版本。
2. 当前 VitePress/Vite 依赖存在 npm 报告的无上游兼容修复的开发服务器审计项。本项目开发服务器固定绑定 `127.0.0.1`，`dist/` 是不含 Node.js 运行时的纯静态文件；不要用开发服务器处理不受信任的项目内容。
3. 自动检查不能替代不同设备、API、字体缩放、RTL、TalkBack 和刷新率上的真机验证。
