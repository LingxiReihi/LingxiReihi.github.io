# 前端页面设计文档

> 项目：personal-web 个人博客站 ｜ 版本：v1.1 ｜ 日期：2026-09-22
> v1.1 变更：主题定为 **B 靛蓝科技（深色默认，可切亮色）+ 强调色 #39C5BB**；渲染架构改为 **vite-ssg 构建期预渲染**（百度推送合规）；About 联系方式仅社交链接。
> 配套文档：[后端架构设计文档](./backend-architecture.md) · [接口文档](./api-reference.md)

---

## 1. 概述

个人博客网站前端，包含 **5 个前台栏目**（落地主页 / 博客 / 模型 / 杂谈 / 个人主页）与 **1 个管理后台**（内容上传、站点设置、访问监控）。本文档定义技术栈、设计系统、信息架构、逐 Flow 页面规格与响应式规范。

## 2. 技术栈（已确认）

| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | Vue 3.5 + `<script setup>` + TypeScript | Composition API |
| 构建 | Vite | 已初始化 |
| 路由 | vue-router 4 | history 模式 + 滚动行为控制 |
| 状态 | Pinia | auth / site-config / theme 三个 store |
| 后台 UI | **Naive UI** | DataTable / Form / Upload / Tabs / Modal / Message |
| 前台样式 | **Tailwind CSS 4** + CSS 变量 token | 前台页面全部手写个性化组件 |
| Markdown | markdown-it（+ sub/sup/mark 插件 + KaTeX）+ Shiki | **构建期（vite-ssg）渲染进 HTML**，水合后交互一致（见 §10） |
| 3D/媒体 | `@google/model-viewer`（glb）、原生 `<video>` + Artplayer、photoswipe 风格自研 Lightbox | 模型页专用 |
| 图表 | ECharts（按需引入）或 vue-echarts | 后台监控看板 |
| HTTP | axios（实例 + 拦截器：token 刷新、错误统一 toast） | |

### 2.1 主题（已定稿：方案 B 靛蓝科技，强调色 #39C5BB）

**B. 靛蓝科技**：深蓝黑底、单一青绿强调色 `#39C5BB`、渐变辉光点缀、玻璃拟态卡片（仅 Hero/重点区块使用，正文区禁用）。**深色为默认主题**，可切换亮色（亮色下强调色加深为 `#0d9488` 保证对比度）。参考 Linear / Vercel 官网质感，标题改用现代无衬线（放弃 v1.0 方案 A 的衬线标题）。

排印规则调整：大标题字重 700、可叠加 `#39C5BB` 渐变文字效果（限 Hero 一处）；正文保持高可读，不跟趋势做全屏辉光。

## 3. 设计系统（Design Tokens）

### 3.1 颜色（CSS 变量，明暗双主题）

```css
:root {                       /* 深色 —— 默认主题（靛蓝科技） */
  --c-bg:        #0b1220;     /* 页面底：深蓝黑 */
  --c-surface:   #111a2e;     /* 卡片 */
  --c-elevated:  #18233c;     /* hover/填充 */
  --c-glass:     rgb(17 26 46 / .65);  /* 玻璃卡片底（backdrop-blur 用） */
  --c-text:      #e6edf3;     /* 主文本 */
  --c-text-2:    #9fb0c3;     /* 次文本 */
  --c-text-3:    #5f7185;     /* 弱文本/时间戳 */
  --c-border:    #1f2c47;
  --c-primary:   #39c5bb;     /* 强调色（用户指定） */
  --c-primary-2: #5ee0d6;     /* hover/渐变亮端 */
  --c-glow:      rgb(57 197 187 / .18); /* 辉光/渐变尾色，仅点缀 */
  --c-danger:    #f87171;
  --c-success:   #4ade80;
  --c-warning:   #fbbf24;
}
.light {                      /* 亮色 —— 可切换 */
  --c-bg:        #f8fafc;
  --c-surface:   #ffffff;
  --c-elevated:  #f1f5f9;
  --c-glass:     rgb(255 255 255 / .7);
  --c-text:      #0f172a;
  --c-text-2:    #475569;
  --c-text-3:    #94a3b8;
  --c-border:    #e2e8f0;
  --c-primary:   #0d9488;     /* 亮色下加深保对比度 */
  --c-primary-2: #14b8a6;
  --c-glow:      rgb(13 148 136 / .12);
  /* danger/success/warning 同名加深镜像 */
}
```

规则：**禁止硬编码色值**，全部走 token；Naive UI 后台通过 `themeOverrides` 注入同名色板，保证前后台视觉统一。`#39C5BB` 深底上对比 ≈ 8:1（过 AA）；用于大字号/图标/边框/渐变，正文小字仍用 `--c-text`；渐变辉光、玻璃拟态仅限 Hero 与重点卡片，阅读区（博客/杂谈正文）禁止叠加装饰层。

### 3.2 字体与排印

| 用途 | 字体 | 规格 |
|---|---|---|
| 正文/UI | system-ui / HarmonyOS Sans SC / Noto Sans SC | 16px / 1.75 行高 |
| 大标题（Hero/文章标题） | 同上，字重 700；Hero 一处可用 #39C5BB 渐变文字 | clamp(28px, 4.5vw, 44px) |
| 代码 | JetBrains Mono / ui-monospace | 14px / 1.7 |
| 层级 | h1 32 / h2 24 / h3 19 / body 16 / small 13 / meta 12 | |

### 3.3 间距 / 圆角 / 阴影 / 动效

- 间距：4px 栅格（Tailwind 默认 scale），区块间 `py-16 md:py-24`，卡片内 `p-5`
- 圆角：卡片 `rounded-xl(12px)`，按钮 `rounded-lg(8px)`，标签 `rounded-full`
- 阴影：亮色 `0 1px 2px rgb(0 0 0/.05)`，hover 提升一档；暗色不用阴影改用 border
- 动效：入场 `fade-slide-up 0.4s ease-out`（respect `prefers-reduced-motion`）；页面切换 250ms；hover 位移 ≤ 4px

## 4. 信息架构与路由表

```
/                 落地主页（Flow A）
/blog             博客列表（Flow B-1/2）
/blog/:slug       文章详情（Flow B-3/4）
/models           模型 Gallery（Flow C-1，Tabs: all/3d/render/animation）
/models/:slug     模型详情（Flow C-2/3）
/chats            杂谈时间线（Flow D-1/2）
/about            个人主页（Flow D-3/4）
/feed.xml         RSS（后端直出）
/admin/login      后台登录（Flow E）
/admin            → /admin/dashboard
/admin/dashboard  监控看板（Flow H）
/admin/content    内容管理（Flow F，query: type=article|model|chat）
/admin/content/new | /admin/content/:id/edit   编辑器
/admin/media      素材库（Flow F-3 的独立页）
/admin/settings   站点设置（Flow G，tab 参数）
```

导航模式：**前台 Top Nav**（5 栏目 + 暗色切换 + 移动端 Hamburger Drawer）；**后台左侧 Sidebar**（仪表盘 / 内容管理 / 素材库 / 设置 + 底部退出登录），路由守卫按 `auth` store 分流。

## 5. 页面规格（按 Flow）

> 每页均预留 **空态 / 加载态（骨架屏）/ 错误态（重试）** 三个 slot。

### Flow A 落地主页

| 屏 | 布局 | 关键元素 | 状态 |
|---|---|---|---|
| A1 Hero | 双栏（左文右图，移动端上下堆叠）| 姓名+定位一句话、副标语、`[阅读博客]` `[查看作品]` 双 CTA、头像/主视觉（glb 渲染图当主视觉呼应模型栏目）、社交图标。**首页现状以 v1.4 改版为准**：眉题/大标题/正文取自站点信息前三项，右侧圆图取 `site.icon`（见 §Flow G 站点信息），双 CTA 下面另有一行「友站」外链，数据源是 `footer.links`（非 http(s) 的地址前端丢掉，见 §Flow G 导航与页脚） | 数据来自 `/home` 聚合接口；失败仅隐藏动态区，静态文案照常渲染 |
| A2 精选区 | 分节纵向滚动 | 「最新文章 ×3」卡片、「精选模型」横向轮播（移动端 snap-scroll）、「杂谈碎片 ×2」 | 区块级骨架屏；某区块空 → 整块隐藏 |
| A3 页脚 | — | 归档入口、RSS、备案/版权、回到顶部 | — |

交互：锚点平滑滚动；导航项当前栏目高亮；卡片整卡可点（禁用嵌套链接二次点击）。

### Flow B 博客

**B1 列表页**：搜索框（300ms 防抖、URL query 同步 `?q=&tag=&page=`）、标签 Chip 行（单选）、文章卡片两列栅格（封面 16:9、标题、摘要 2 行截断、日期/标签/阅读时长 meta）。分页用「加载更多」按钮（无限滚动的可控替代）。
**B2 筛选态**：已选条件以可移除 Chip 展示 + 结果计数；空态插画 + `[清除筛选]` CTA。
**B3 详情页**：容器最大宽 `1200px` 三栏（正文 720px + 右侧粘性 TOC 240px，<1280px 时 TOC 折叠为浮动按钮）；顶部阅读进度条；Shiki 双主题代码块（随站点主题切换）+ 复制按钮；文末标签、上下篇卡片。
**B4 延伸区**：相关文章 ×3（按标签重合度，后端返回）；评论区**不做**（v1.1 决策，Out of Scope）。
终态：404 → 专属页面 + 返回列表 CTA；滚动位置在返回列表时恢复。

### Flow C 模型页（Blender 3D / 渲染图 / 动画）

**C1 Gallery**：Tabs `全部 | 3D 模型 | 渲染图 | 动画`（URL 同步）；瀑布流封面卡（3:4 与 1:1 混排），悬停放大 1.03 + 类型角标；封面全部懒加载 + blur-up 占位。
**C2 详情**：主媒体区按类型分发——3D：`<model-viewer auto-rotate camera-controls>`（加载失败降级为渲染图）；渲染图：多图组 + Lightbox；动画：`<video>` 封面帧起播 + 0.5x/1x/1.5x。右侧信息栏：创作说明（MD）、参数表（面数/材质数/时长/软件版本/输出格式）、`下载 .glb`（经后端计数）与外链（ArtStation/B 站）。
**C3 灯箱**：全屏、缩放、左右切换、Esc 关闭并恢复原位。
大文件策略：glb 建议 < 20MB，列表接口只回封面，详情媒体懒加载 + 进度提示。

### Flow D 杂谈 + 个人主页

**D1 杂谈时间线**：单列 ≤640px 内容宽；按日期分组（月/日标题线）；卡片=短文本（超 300 字折叠「展开全文」）+ 可选九宫格图 + 分类小图标。游标分页「 Load more」。
**D2 杂谈详情**：短内容默认不单独成页，仅当含长文或需要可分享 URL 时生成 `/chats/:id`。
**D3 个人主页**：大头像 + 简介（MD 渲染）、技能栈分组 Tag 墙、教育/工作经历垂直 Timeline、作品集快链（联动模型栏目）。
**D4 联系出口**：仅社交链接矩阵卡片（GitHub/邮箱以链接形式呈现，**不明文暴露邮箱、不做留言表单**——v1.1 决策，降低垃圾采集；邮箱可用图片式或拆分拼接渲染防爬）。

### Flow E 后台登录

Minimal 布局（无导航，居中卡片 ≤400px）。用户名 + 密码（显隐切换）、记住登录 Switch、提交按钮 loading。**全部错误 inline 显示**，不用 toast；连续失败显示剩余等待秒数（423 锁定）。登录过期被拦截器捕获 → 跳回本页 + 顶部提示条。

**忘记密码（v1.4 追加）**：记住登录行右侧一个「忘记密码？」文字按钮 → `n-modal`（只填账号名，默认带出上方已输入的账号）→「发送重置邮件」。界面**不自己编措辞**：成功提示直接用响应 `data` 里服务端那句 `UNIFORM_MESSAGE`，所以"账号不存在 / 没填邮箱 / 被冷却挡下 / 发信失败"在界面上长得一模一样（防枚举口径由后端唯一持有，改一处即可）。只有 `50300`「邮件通道未配置」会走红色错误条 —— 它是站点级故障，与任何账号无关。这条调用单独把 axios 超时放宽到 30s：服务端发信自身上限 15s，再叠 bcrypt 与对端 SMTP 耗时，默认的 20s 余量太薄，超时会被误报成"网络错误"而邮件其实已经发出去。

### Flow F 内容上传与编辑（后台）

**F1 列表**：`n-tabs`（文章/模型/杂谈）+ `n-data-table`（标题、状态 Badge(draft 灰/published 绿/archived 黄)、标签、更新时间、行操作···：编辑/预览/发布/下架/删除）、搜索 + 状态筛选、`+ 新建`。删除走 AlertDialog 确认。空态含「发布第一篇文章」CTA。
**F2 编辑器**（全页，字段 >5 不用 Dialog）：左编辑右预览分屏（可切「编辑/预览/仅预览」），工具栏（图片→唤起素材库、代码块、标题）；顶部标题输入 + 元数据抽屉（slug 自动生成可改、分类、标签多选可创建、摘要、封面裁剪）。模型类资源额外字段：类型(3d/render/animation)、参数 JSON 表单、媒体文件绑定（glb/多图/视频）。**自动保存草稿（30s 防抖 + beforeunload 提示）**。**右侧「语法」抽屉**（`MarkdownHelp.vue`，模式条最右一个按钮开合，从右边缘滑入、收起后 `display:none` 所以不撑横向滚动条）：内容 = Markdown 基础 + 扩展语法（`~~删除~~` `H~2~O` `X^2^` `==高亮==` `$公式$`，含 `$` 撞金额的逃生口）+ 本站特有语法（`@[TOC]`、Typora 的 `zoom:` 图）+ 支持的 HTML 标签表（行内/块级分栏，**直接读 `MD_HTML_TAGS` 生成**）+ 可用 style 属性 + 明确不放行清单。块级标签那节写明「必须独占一行、与上下文留空行」。
**F3 素材库**：网格 + 上传区（拖拽/多选/进度条/类型大小校验：图 ≤5MB、glb ≤50MB、视频 ≤200MB）、搜索、选中回填。
**F4 发布**：`发布` 前拉取预览（新 tab 前台草稿链接，token 校验）；状态机 草稿→已发布→下架。
**F5 成功**：回列表新行置顶 + Message「已发布 ✓ 查看前台」；流水线状态附注（重建中 → 推送成功 ✓ / 推送失败 ⚠ 可前往 SEO 面板重推，见 §10.3）。
反模式规避：表单错误 inline 而非 toast；操作后局部更新不刷全页。

### Flow G 站点设置（后台）

子 Tabs：`站点信息 / 导航与页脚 / 邮件通道`。**每个分区独立保存按钮**（禁"统一 Save All"）。
- ~~个人资料~~：**v1.4 起从本站点设置移出**——资料跟人走，改由后台侧栏独立页「我的资料」（`/admin/profile`）承担：**七项资料每位管理员都能改自己那一份**（头像走素材库选/上传；昵称/签名/社交链接/简介 MD/技能栈/经历）。经历每条含类型下拉（工作/教育/项目）+ 标题 + 单位 + 起止 + 一句话说明；技能栈按「组名: 项1, 项2」逐行输入。About 主体与首页 hero 读 super 那份（字段名未变），其他人的资料渲染进 About 的自己那张卡片与内容页署名。
- 我的资料分块只读/编辑（v1.4 同日追加）：页面拆成 **6 块**（基本信息=昵称+签名+头像 / 社交链接 / 简介 / 技能栈 / 经历 / 密码设置），**默认只读预览**（不是把输入框灰掉：短字段显示文本、链接与经历显示条目、简介按 `whitespace-pre-line` 纯文本、头像显示图片），每块标题行右侧「修改」才换成控件。**取消=回滚该块快照且不请求后端**；**保存=只 `PUT /admin/profile` 本块字段**（后端本来就支持部分字段）。两条约束别改回去：① **一次只允许一块处于编辑态**（另一块点「修改」会 warning），因为保存成功后整页按服务端返回重填，同时开两块会把另一块的未保存改动冲掉；② **头像由「选完立即落库」改为随「基本信息」块一起保存**（原行为是误触来源，取消即不写库）。密码板块只读态不显示任何密码信息，编辑态给 当前密码/新密码/确认，三条前端校验（空当前密码、新密码 <8、两次不一致）**都在发请求之前**；成功后沿用旧行为：本地登出 + 跳 `/admin/login`（改密会 bump `token_version`，所有设备下线）。**两条重置路径互不替换**：本页与后台「管理员账号」页的「重置口令」= 界面一次性口令（服务端不留明文、不回显给别人）；登录页「忘记密码」= 随机口令走邮件，**HTTP 响应里永不含口令**（见 §5.9）。
- About「管理团队」（v1.4）：**一行一张全宽卡片**，主体（顶级管理员）在最上，其余在职管理员按 id 依次排开，全部复用同一个 `components/site/ProfileCard.vue`（头像 + 昵称 + 签名 + 简介 MD + 技能栈 + 经历 + 社交链；原先挂在主体卡上的「查看我的 3D 作品集 →」已按圈注删除，模型栏目入口仍由首页与顶栏导航提供）。卡片底色用 **`bg-glass` + `backdrop-blur-md` 毛玻璃**（深色主题 `rgba(17,26,46,.3)`，与内容卡片同款），内部 chip 用 `bg-elevated/50` 让背景透得过来。**技能栈与经历各带折叠按钮**（标题行即按钮，带「收起/展开」文字 + `aria-expanded`，箭头是单个 `▸` 靠 CSS `rotate-90` 转），默认展开，动画用 **anime.js 高度补间**（260/220ms，`outQuad`/`inQuad`，animejs 只在点击时动态 import，不进 SSR 与首包；`prefers-reduced-motion` 直接瞬时切换）。两条实现约束别改回去：① 收起前必须**把当前高度钉成像素值**（inline 还是 `auto` 时 anime 拿不到起点，会退化成原地不动再瞬间跳 0）；② 终态用 `setTimeout` 兜底而非只靠 `onComplete`（anime 靠 rAF 推进，后台标签页里 rAF 冻结，否则点了按钮毫无结果）。折叠用 `v-show` 不用 `v-if`，正文必须留在预渲染 HTML 里（不伤百度收录）。口径=凡在职管理员都上名单（按 id 升序，super 不重复出现，停用即下架），无逐账号开关；账号页顶部一行文案提示「在职管理员的昵称/头像/签名/社交链会出现在前台关于页」。
- About 卡头自动缩略（v1.4，同日追加）：大卡头（大头像 + 居中昵称）被滚出卡片可见区时，一条 `小头像 + 昵称 + 签名` 的 sticky 栏**用 anime.js 滑入**（`translateY -100%→0` + 淡入 280ms `outQuad`，回顶时 220ms `inQuad` 滑出，只动 transform/opacity）。判定用卡头之后的一条 1px 哨兵交给 IntersectionObserver，**root 必须取真正滚动的 `main`**（本项目是「顶栏 + main 内部滚动 + footer 固定」三段式，按视口算会被顶栏那 56px 干扰）；栏体是 `sticky top-0 h-0 overflow-visible` + 内部 `absolute`，所以它出现/消失不推动正文（实测滚 900px 时正文位移恰为 900px，一像素不多不少）。**动画与终态分离**：`-translate-y-full opacity-0` / `translate-y-0 opacity-100` 由 class 表达，anime 只补间、收尾清掉内联样式交还 class（另有 `setTimeout` 兜底），所以 rAF 冻结或 animejs 加载失败时最坏只是「没有动画」，不会把栏卡在半隐半现；也因此**不要再给这条栏加 CSS `transition-*`**（会与 anime 抢同一批属性）。初始态「未缩略」，SSR 输出完整卡头；栏本身 `aria-hidden`，避免与卡内 h1/h2 重复播报。每张卡各自 sticky，滚到下一张时上一张的条随卡片一起离开，不会叠两条。
- 站点信息：标签直接写明每项去哪儿 —— **站点名**（顶栏 + 首页大标题 + 各页 `<title>` 后缀）、**副标题**（首页眉题，留空则该行不渲染）、**站点描述**（首页介绍正文 + 各页 SEO）、**网站图标**、**favicon**、备案/版权行（香港服务器部署，无 ICP 时留空仅显示版权）。前三项是首页首屏「网站介绍」的文字数据源。
  - **网站图标（`site.icon`，圈注「首屏那张图改成可在站点设置编辑的网站 icon」）**：首页首屏右侧那张圆形大图，**以前借用 super 的个人头像**（读 `/home` 的 `profile.avatar`），现在读 `site-config` 的 `site.icon`，与「资料跟人走」彻底分开。控件走 `MediaPicker`（与「我的资料」换头像同款：从素材库选或上传即选用，分类 `site`），不是手填 URL。**留空则整格不渲染**（沿用原 `v-if` 语义，不回落头像）。素材分类新增第 5 类 `site`（`media.CATEGORIES` + `MEDIA_CATEGORIES`，标签「站点素材」）——站点资产混进 `avatar` 以后在素材库里没法筛。
  - **favicon（`site.favicon`）曾经是个死控件**：值入得了库、`/site-config` 也下发，但前台没有任何地方读它（`index.html` 写死 `/favicon.svg`），与 2026-10-06 绑定审计抓到的是同一类缺陷，本轮接上。做法是**删掉 `index.html` 里那条硬编码 link**，改由 `App.vue` 的 `useHead` 按配置产出（留空回落内置 `/favicon.svg`）。挂在 App 而不是 `useSeo`：后者只有站点页调用，后台页会漏掉图标；删硬编码而不是留着覆盖：unhead 是否与静态标签去重没有可靠保证，两条 `rel=icon` 谁生效属未定义。
- ~~首页配置~~：**v1.4 整组废弃**（同日，首页改版之后）。原本是 A2 的四类型开关（Hero/文章/模型/杂谈，`/site-config.sections`）+ 精选内容勾选器（`/home.featured_models`）。首页改成「最新 / 热门 / 管理团队」三段后，四个类型开关与精选位都**再无任何消费者** —— 与 2026-10-06 绑定审计抓到的「值入库但前台无人读」是同一类缺陷，所以整块撤掉而不是留着改语义：`SETTINGS_GROUPS` 去掉 `home`（改它返回 `40000`）、`get_public_config` 不再下发 `sections`、`/home` 不再算 `featured_ids` 与 `featured_models`（省掉每次请求一次无用的库查询）、旧的两行由迁移 `b7f3d2c8a5e4` 前滚清除。三段固定显示，不给后台开关。
- 导航与页脚：导航项显隐/排序、页脚文字（版权行 + 备案号，**当前页脚未渲染这两项，只入库**，控件下方已写明）、**友站链接**（一行 `站点名 + URL`，就是首页首屏「阅读博客 / 查看作品」下面那行「友站」的唯一数据源；没有新增首页专用字段）
- 邮件通道（v1.4 追加）：`发信接口地址 / API Key / 测试收件人` 三项，`PUT /admin/settings/mail`。Key 是**只写不回显**字段：接口只给 `api_key_set` 与明文尾 4 位，输入框 placeholder 因此显示「已配置（尾号 xxxx），留空则不修改」，保存后必须拿响应里的掩码刷新这两个状态（响应形状是 `{mail: {...}}`，按扁平对象读就永远显示"未配置"——本地实测踩过）。库里存 Fernet 密文（主密钥由 `JWT_SECRET` 派生），改 `JWT_SECRET` 后旧密文解不开就退回「未配置」，重填即可。「测试收件人」非空时所有重置邮件改投该地址，只应在排障时临时打开，线上留空。
- 账号安全：**v1.4 起从站点设置移出**，改密码并入「我的资料」页的「密码设置」板块（端点仍是 `POST /admin/auth/password`，未变）。理由：改密码是"我的"而不是"站点"的事，两处入口迟早漂移。
- 详情署名（v1.4）：文章/模型/杂谈详情页在标题或元信息行展示 `作者 = {头像, 昵称}`，只取公开白名单两项，邮箱等一律不显示。**署名是可点的**，跳到 `/about?a=<昵称>`，关于页加载完成后滚到那张卡并描边约 1.6s 再淡出（重名命中第一张；找不到人就不滚不动）。定位靠卡片的 `data-author` 属性；**用昵称做锚点而不是账号 ID** —— 昵称本来就显示在页面上，为深链新开一项公开标识会把账号数量与创建顺序泄露出去。

- 管理员账号页的授权行（v1.4 追加）：支持栏目作用域的三点（`content:write` / `content:delete` / `column:manage`）采**互斥二选一、以后一次操作为准** —— 勾权限名=全站，只在右侧选栏目=仅这些栏目；勾全局会**清空**该行已选栏目（留着也只在保存时被静默丢掉），选栏目会自动取消全局。每行末尾实时显示本次将存成什么：`全局` / `指定 N 个栏目` / `未授`。这条是修「顶级管理员无法为其他管理员分配可编辑的指定栏目」时定下的：后端 `PUT /admin/admins/{id}/grants` 一直存得进 `column_id`（已补契约测试钉住更新路径），卡点在界面 —— 旧版一勾全局就把栏目下拉 `disabled`，而「全局」这层含义只写在占位符「或仅指定栏目」里，看不出来。
- 新建与改权限两个弹窗共用同一对处理函数（`setGlobal` / `setColumns`）与同一份行模板结构，别只改一边。

### Flow H 监控看板（后台）

**H1 总览**：KPI 卡 ×4（今日 PV/UV/文章数/近 7 日环比迷你图）、访问趋势折线（Range：7d/30d/90d/自定义，联动全部图表）、热门内容 Top10 Table（点击行下钻）、来源分布条形图。
**H2 下钻**：单篇趋势弹窗（该篇 PV/UV 折线 + 来源）；Skeleton 加载。
**H3 出口**：CSV 导出（下载 blob）；新站空态 →「还没有访问数据」+ 引导发布 CTA；采集异常顶部 Banner。
**H4 更新公告卡**（2026-10-14 v1 新增，**v2 同日撤除**）：仪表盘内嵌卡与 `AnnouncementCard.vue` 已不存在——该组件 `git mv` 为独立管理页 `AnnouncementsView.vue`（见下 Flow H-ann），仪表盘回到 H1–H3 原布局。撤除的动因是 v1 把读写都钉在 `announcement:manage` 上，实测发现其他管理员根本看不到公告；v2 改为「全员登录弹窗 + 独立管理页」，卡片当年的列表渲染与新建/编辑弹窗口径由管理页原样承接。

### Flow H-ann 更新公告：管理页 + 登录弹窗（2026-10-14 v2 新增）

**HA1 管理页**（`/admin/announcements`，`views/admin/AnnouncementsView.vue`）：路由 `meta.perm='announcement:manage'`（全局守卫拦截），侧栏 `AdminLayout.vue` 的 `ALL_ITEMS` 加「📢 更新公告」同 `perm`（无权限者菜单不显示）。页面为页级标题行（`更新公告` + 条数 + `＋ 新建`）+ surface 容器列表，每项含状态徽章（已发布绿/草稿灰）、标题、日期（`published_at ?? created_at` 取日）、作者昵称、正文（Markdown 经 `renderMd()` + `.prose` 容器渲染，与内容详情页同款，`max-h-96` 限高滚动）、行内编辑/删除（`n-popconfirm` 二次确认）。新建/编辑走自控 `show` 的 `n-modal preset="card"`（照 TagsView 样板），字段：标题（1–200，前端 `save()` trim 已拦下所有空白标题；纯空白标题由后端兜底 `422`（`42200`，仅在绕过界面直连 API 时可达））、正文（编辑/预览两态切换）、发布日期（`n-date-picker` formatted `yyyy-MM-dd`、可清空）——**日期留空 = 存草稿（status=draft），填了日期 = 发布**；首发时间由后端保证「重发布不覆盖」（改回草稿再发布不会把日期刷成新值）。**不接重建链路**（不触发 trigger_rebuild / sitemap 失效）：公告本期前台没有消费者。

**HA2 登录弹窗**（`views/admin/AnnouncementGate.vue`，挂在 `AdminLayout.vue` 的 `n-message-provider` 之内，**所有在职管理员**都走这套，无需任何权限点）：`auth.ready`（me 探测完成）后拉 `GET /admin/announcements/unread`，非空则弹 `n-modal`（preset card，标题「更新公告」、header-extra「N 条未读」），逐条 = 标题 + 日期 + 作者昵称 + `.prose` 正文，整体 `max-h-[60vh]` 限高滚动。三条口径：① **一次登录只弹一次**——一次性 `fetched` 守卫，路由来回切不重复拉、不重复打扰；② **关闭即整批标已读**——遮罩/×/「我知道了」三条路径汇进同一 `onClose`，先 `blur()` 把焦点移出弹窗，再取本次列出的 ids 快照 `POST /admin/announcements/read` 一次（`reported` 守卫防重复上报），上报失败只 `message.warning`「下次登录可能再次看到」，不重开弹窗；③ **拉取失败静默**——弹窗是增益不是必经步骤，网络/5xx 直接跳过，不打断登录流程。`/unread` 只推 `status=published`（草稿不弹给别人）；没有未读的人不渲染弹窗、不占位。两条无障碍/动画约束别改回去：本弹窗**无用户手势自动弹出**（其他后台弹窗由点击带焦点进弹窗），Naive trap-focus 给背景加 `aria-hidden` 时焦点若还留在背景 `<div>` 里，Chrome 在打开这一刻就报 Blocked aria-hidden——故 `watch(show)` 打开后 `nextTick` 依次取「我知道了」按钮 ref → `.n-modal .n-base-close` → `document.body` 主动 `.focus()`；正文清空推迟到 `@after-leave`，否则淡出过程中弹窗会变成「0 条未读」的空壳。

## 6. 响应式断点规范

| 断点 | 范围 | 前台变化 | 后台变化 |
|---|---|---|---|
| xs | <640px | Hero 上下堆叠；博客单列；TOC 隐藏入浮动按钮；轮播 snap 滑动；导航收为 Hamburger Drawer | 表格转卡片式行；Sidebar 收为顶部抽屉 |
| sm | ≥640px | 杂谈图格 2 列 | — |
| lg | ≥1024px | 博客两列栅格；Hero 双栏 | 编辑器双栏分屏启用 |
| xl | ≥1280px | 详情页 TOC 栏展开（正文 720 定宽居中偏左） | Sidebar 常驻 240px |

图片策略：封面提供 2x 源或 `srcset`；`loading="lazy"` + 宽高占位防 CLS。

## 7. 组件清单（前台自研 / 后台 Naive）

**前台自研**：`SiteHeader / SiteFooter / ThemeToggle / HeroSection / ContentCard(Post|Model|Chat) / TagChip / SearchInput / TimelineList / ExperienceTimeline / ProseArticle(MD 样式容器) / TocNav / CodeBlock / MediaViewer(Model3D|ImageSet|Video) / Lightbox / PaginationLoader / SkeletonBlock / EmptyState / ErrorRetry / SocialLinkCard`
**后台 Naive 映射**：DataTable、Tabs、Form+Input+Select+Switch+DynamicInput、Upload、Modal/Drawer、AlertDialog(n-popconfirm+n-modal)、Message、Badge、Progress、DatePicker、n-config-provider 主题注入。

## 8. 前端工程约定

```
frontend/src/
├── api/            # axios 实例 + 各资源 API 封装（与接口文档一一对应）
├── assets/
├── components/
│   ├── common/     # 跨页通用（Card、TagChip、Skeleton…）
│   ├── site/       # 前台布局与栏目组件
│   └── admin/      # 后台专用（编辑器、上传器…）
├── composables/    # useAuth / useTheme / usePagination / useMd(渲染)
├── layouts/        # SiteLayout / AdminLayout / MinimalLayout
├── router/         # 路由 + 守卫
├── stores/         # auth / site / theme
├── views/
│   ├── site/       # Home, Blog, BlogPost, Models, ModelDetail, Chats, About
│   └── admin/      # Login, Dashboard, ContentList, ContentEdit, MediaLibrary, Settings
└── styles/         # tokens.css, prose.css
```

- 命名：组件 PascalCase 文件、composable `use*`、视图 `*View.vue`；样式前台仅 Tailwind + token 类，不写散落 CSS
- **路由过渡里 `done()` 是契约不是回调**（`usePageTransition` + `SiteLayout` 的 `<Transition mode="out-in" :css="false">`）：out-in 模式下旧页的 leave 不结束，新页就永不挂载，而 URL 已经变了 —— 表现是「点导航没反应，只有刷新才好」（本地把那次 `import('animejs')` 换成必定失败的地址注入复现：URL 连跳两次、视图一直停在旧页）。三条漏 `done` 的路都要堵：① `import` 失败（每 4 小时 cron 重建 + `rebuild-frontend.sh` 只保留 3 个 release，旧 chunk 会被删；且模块表会**记住**失败，之后每次点都立刻 reject）；② anime 靠 rAF 推进，后台标签页里 rAF 冻结，`onComplete` 不来；③ 动画丢帧。写法=幂等 `finish()` + `setTimeout` 兜底 + `try/catch` 放行，并且**兜底放行时把终态一并钉上**（`opacity:1`、`transform:''`）——否则冻结页签里新页会带着 anime 的起始值 `opacity:0` 挂载，等于白屏（实测：修前停在 0，修后同一场景为 1）。
- 懒加载路由 chunk 拉不到时 Vue Router 只会**静默放弃**这次导航（`routes.ts` 里 26 个组件全是 `() => import()`），所以 `main.ts` 挂了 `router.onError`：识别到模块加载失败就 `location.assign(to.fullPath)`，把用户本来要点的那一页整页加载过去（不是原地刷新，不丢目的地）；同一地址连续失败只试一次，避免重建窗口里来回刷。
- Markdown 渲染：正文存 MD，由 markdown-it + Shiki 渲染——**该渲染在 vite-ssg 构建期执行并产出静态 HTML**，客户端水合后行为一致；后端接口不做 HTML 注入（RSS 例外，后端渲染）
- **扩展语法**（圈注「使内容编辑器支持内联公式/下标/上标/高亮，并支持 `~~弃用~~`」）：`~~弃用~~` 删除线是 **markdown-it default 预设自带的，没装任何插件**；`H~2~O` 下标 / `X^2^` 上标 / `==重点==` 高亮 走 `markdown-it-sub|sup|mark`；`$E=mc^2$` 行内公式走 `@vscode/markdown-it-katex` + KaTeX。**Mermaid / 流程图 / 序列图本轮明确不做**（用户拍板）——mermaid 需要 DOM、构建期跑不了，只能水合后异步换 SVG，且它默认的 `htmlLabels` 会把刚堵掉的「低权限写正文 → 高权限读」提权口从另一扇门放回来。四条实现事实：
  - 三个 sub/sup/mark 包**只发 JS 不带 `.d.ts`**，环境声明必须放在**独立的、顶层没有 import/export 的 `.d.ts`**（`src/types/markdown-it-plugins.d.ts`）里；写进带 `export {}` 的 `shims.d.ts` 会被解析成「模块增强」而对本来无类型的包整体失效，TS7016 照旧报（实测踩过一次）。
  - `@vscode/markdown-it-katex` **只有 CJS 产物**：Node（vite-ssg 构建期）经 cjs-module-lexer 会把 `default` 再包一层，浏览器侧 vite 预打包后 `default` 就是函数本身。本文件两个环境都要跑，所以取一次 `?? ` 兜底 —— 这类互操作差异只有「构建期 + 浏览器各跑一遍」才暴露。
  - KaTeX 不碰 DOM，公式**在构建期就渲染进 HTML**（SEO 看得见、客户端不闪）。CSS 走 `src/style.css` 里一行 `@import "katex/dist/katex.min.css"`，19 个 woff2 由 vite 落进 assets 并改写哈希名，浏览器按 `unicode-range` 只取用到的（实测一个公式只拉 `KaTeX_Math-Italic` + `KaTeX_Main-Regular`）。
  - **`$` 的误判面是实测过的**：`价格$5和$10之间`、`他有 $5 块钱`、`见 $PATH 与 $HOME 两个变量`、跨行的 `成本 $5\n售价 $10` 全部按原样显示（插件自带守卫），所以没有额外收紧；但 `$ x $`（内侧带空格）会被当公式，且该插件**不认 `\(...\)`**。逃生口写在抽屉里：金额写 `\$5` 或放进行内代码。
- **正文里的 HTML 走「白名单哨兵预转换」，不是 markdown-it 的 `html:true`**（`composables/useMd.ts` 的 `MD_HTML_TAGS`）：代码区外把命中白名单的标签换成 `[[pw-hN]]` 哨兵，渲染后再按**属性白名单**重建。这么做的理由是权限而非排版：`renderMd` 的产物全部进 `v-html`，而 `content:write` 可以授给 staff —— 真开 `html:true` 等于允许只有内容权的账号在正文里埋 `onerror`，等 super 打开这篇文章时执行，refresh token 存在 storage 里，内容权就提成了 super 权。哨兵方案是纯字符串处理，所以构建期在 Node 里照跑、不需要 jsdom。
  - 表驱动：`MD_HTML_TAGS` 一份数据同时喂渲染器和编辑页右侧「语法」抽屉（`components/admin/MarkdownHelp.vue` 直接 `Object.entries` 生成），改标签只改一处，不会两处漂移。
  - **一律不放行**（按字面显示成文本）：`<script> <style> <link> <meta> <form> <input> <iframe>`（用户拍板：iframe 嵌入、`<style>` 块、`class` 属性三项全禁）、任何 `on*`、`href/src` 里的 `javascript:`/`data:`/`vbscript:`、`style` 里的 `position`/`url()`/`expression`/`behavior`（`position` 整条不在白名单里，防覆盖全站 UI 与钓点击）。`class` 也禁：站点没有配套类名，放行只会让人写出没效果的 class。
  - `style` 只放行排布与字号字色那一批属性；`<a target="_blank">` 自动补 `rel="noopener noreferrer"`；块级标签两侧补空行让它独占一段（否则回填出来是 `<p><div>` 这种被浏览器强行拆开的结构）。
  - **两步预转换都必须避开代码区**（`mapOutsideCode`）：教程里写的 `<br>`、`<img>` 示例要照原样显示。这条顺带修掉 `extractImgZoom` 的老问题——它此前会把 ``` 围栏里的 `<img>` 也换成 markdown 图片语法。坑：围栏正则**不能用 `(`{3,})...\1` 这种反向引用**，`\1` 指向的是整个交替式、会把围栏截断成「只有开头那一行」；写死 ```` ``` ````/`~~~` 两种收尾即可。
  - 回填哨兵时跳过 `<code>`/`<pre>` 内部：四空格缩进式代码块不在 `mapOutsideCode` 的识别范围内，漏网的哨兵宁可显示成 `[[pw-hN]]` 也不能变成注入进代码示例的真标签。
- SEO：v1 即采用 **vite-ssg 构建期预渲染**（详见 §10），meta 由 `useHead` 式 composable 按路由注入；sitemap/RSS 后端提供

## 9. 无障碍与质量底线

- 键盘可达：导航/Tab/抽屉全部可 Tab 遍历，焦点环显式（`focus-visible` + token 色）
- 图片必有 alt（封面标题兜底）；正文对比度 ≥ 4.5:1；`prefers-reduced-motion` 关闭位移动效
- 语义标签：header/nav/main/article/aside/footer 结构；文章标题层级不跳级

## 10. 百度合规与渲染架构（v1.1 新增，硬性要求）

### 10.1 渲染方案：vite-ssg 构建期预渲染

- 引入 `vite-ssg` 替换纯 SPA 入口；路由级数据在 **构建期** 通过公开 API 拉取（仅 published 内容），产出每个内容页的真实 HTML（含正文、封面 img、参数表文字）
- 预渲染路由清单（动态枚举）：`/`、`/blog`、`/blog/:slug`*、`/models`、`/models/:slug`*、`/chats/:id`（长文）、`/about`；列表页预渲染首屏第 1 页，翻页后为客户端路由
- 水合后行为不变：主题切换、3D viewer、灯箱等交互组件仅客户端渲染（`<ClientOnly>` 包装），不阻塞 SEO
- **发布流水线（关键约束，v1.2 定稿）**：新内容发布 → **服务器本机脚本重建**（后端 subprocess 触发：拉内容 API → vite-ssg build → `dist_new` 原子符号链接切换；同机需 Node ≥20、内存 ≥1GB；并发加锁 + 短窗口合并）→ 构建成功后向百度推送 URL（token 未配置阶段仅重建，推送留待 SEO 面板补推）；未重建期间新文章已可经 SPA 路由直达，重建后进 HTML 索引
- 性能预算：预渲染页 LCP < 2.5s（4G）、首页 JS 首包 < 180KB gzip；图片 AVIF/WebP + 尺寸声明防 CLS

### 10.2 SEO 页面规范（每页必做）

| 项 | 规则 |
|---|---|
| title | `{文章标题} · {站点名}`；列表页 `{栏目} · {站点名}` |
| meta description | 取 summary，缺省取正文前 80 字 |
| canonical | 全站唯一 `https://域名/path`，禁止 query 版式 URL 进入 canonical |
| slug | 语义化英文/拼音，**发布后不可变**（改 slug = 新建 + 301 旧链） |
| 结构化数据 | 文章页 JSON-LD（Article）、模型页（3DModel/Image/GenericMedia）、面包屑（BreadcrumbList） |
| robots.txt | 静态：放行 `/`，屏蔽 `/admin`；含资源平台验证文件路径 |
| sitemap | 由后端生成 `sitemap.xml` + 百度专用 `sitemap.txt`（Caddy 转发），含 lastmod |
| 移动适配 | 响应式即满足（百度已不再要求单独 m 站）；禁止闪屏/插页引导 |
| HTTPS | 全站强制 + http→https 301；HSTS |

### 10.3 百度主动推送（后端执行，前端配合）

- 推送 API 为后端职责（见后端架构 §10）；前端仅在后台「发布成功」Toast 中展示推送状态（成功/失败可重试）
- 备选兜底：sitemap 推送（资源平台支持提交 sitemap.txt 自动周期抓取）
- 部署基线：香港服务器无 ICP——百度可正常抓取与推送，但收录权重与信任分通常低于备案国内节点；若后续以百度流量为主要目标，评估迁移大陆节点（需备案）

