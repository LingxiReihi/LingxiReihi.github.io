# 接口文档（REST API）

> 项目：personal-web ｜ Base URL：`/api/v1` ｜ 版本：v1.1 ｜ 日期：2026-09-22
> v1.1 变更：新增 SEO/百度推送端点组（§5.6）与 sitemap/robots 公开端点；留言 feedback 端点暂缓。
> 机器可读版由 FastAPI 自动生成：`/api/docs`（Swagger UI）。本文档为评审与设计基准。

---

## 1. 总览

| 分组 | 前缀 | 鉴权 | 对应前端 Flow |
|---|---|---|---|
| 公开内容 | `/api/v1/*` | 无 | A/B/C/D |
| 后台认证 | `/api/v1/admin/auth/*` | 登录接口无，其余 Bearer | E |
| 内容管理 | `/api/v1/admin/contents/*`、`/media/*`、`/tags/*` | Bearer | F |
| 站点设置 | `/api/v1/admin/settings/*` | Bearer | G |
| 统计监控 | `/api/v1/admin/stats/*` | Bearer | H |

## 2. 通用约定

**响应包**（所有接口）：

```json
{ "code": 0, "message": "ok", "data": { } }
```

**错误码表**（`code`，HTTP 状态码见括号）：

| code | HTTP | 含义 |
|---|---|---|
| 0 | 200 | 成功 |
| 40000 | 400 | 请求参数错误 |
| 40100 | 401 | 未登录 / token 无效或过期 |
| 40101 | 401 | 账号或密码错误（不区分二者） |
| 40300 | 403 | 无权限 |
| 40400 | 404 | 资源不存在（含访问非 published 内容） |
| 40900 | 409 | 冲突（slug 重复、标签已存在） |
| 41300 | 413 | 文件超出大小限制 |
| 41500 | 415 | 不支持的文件类型 |
| 42200 | 422 | 校验失败（返回 `data.fields[]` 字段级错误，前端 inline 展示） |
| 42300 | 423 | 账号锁定（`data.retry_after` 秒） |
| 42900 | 429 | 触发限速 |
| 50000 | 500 | 服务器内部错误 |

**分页**：请求 `?page=1&page_size=10`（默认 10，上限 50）→ `data: { total, page, page_size, items: [] }`。游标分页：`?cursor=<opaque>&limit=20` → `data: { items, next_cursor }`（`next_cursor=null` 结束）。

**鉴权头**：`Authorization: Bearer <access_token>`。

**内容对象 `Content`（公开精简 DTO）**：

```json
{
  "id": 1, "type": "article", "title": "…", "slug": "hello-world",
  "summary": "…", "cover": "https://…/media/x.webp",
  "tags": [{"id":1,"name":"随笔","slug":"essay"}],
  "published_at": "2026-09-20T12:00:00Z", "view_count": 128,
  "media_kind": null, "extra": {}
}
```
详情 DTO 额外含 `body_md`；模型详情额外含 `assets[]`（glb/图/视频 URL 与规格）与完整 `extra`。
三类内容的详情都额外含 `author: {nickname, avatar}`（v1.4 资料跟人走）——白名单只有这两项，`email / username / role / note` 一律不下发；作者账号缺失或已停用时回落顶级管理员，前台不出现空署名。列表 DTO 不含 `author`（省体积）。

---

## 3. 公开接口

### 3.1 首页聚合 — Flow A

`GET /home` → 一次拉齐落地页所需数据：

```json
{ "data": {
  "profile":   { "nickname": "…", "avatar": "…", "signature": "…", "social_links": [] },
  "recent_posts": [Content], "recent_chats": [Content],
  "latest": [Content], "hot": [Hot], "team": [{ "nickname": "…", "avatar": "…", "signature": "…" }]
} }
```
`profile` 字段名不变，数据源已换成顶级管理员账号那一行（`site_settings.profile` 组在 v1.4 废弃，一次性迁进 super 行）。

首页改版（2026-10-06）后新增三段：`latest` = 跨类型最新 12 条；`hot` = 热门 8 条，`Hot = Content + {comment_count, score}`，`score = 浏览×1 + 点赞×8 + 已过审评论×12`（**分数由后端算并下发**，前台只拿它画热度条，别在前端再抄一份权重）；`team` = 所有在职管理员的名片三项（**含 super 且排最前**，与刻意不含 super 的 `/about.team` 分开）。原 `featured_models` 已删 —— 新首页没有精选位，留着等于每次请求白查一遍库。

### 3.2 博客 — Flow B

| 方法 路径 | 说明 |
|---|---|
| `GET /posts?q=&tag=&column=&page=&page_size=` | 列表（仅 published；`q` 匹配标题+摘要+正文；`column=<slug>` 按栏目筛，**默认含全部子孙**，加 `column_direct=1` 只取本级直属） |
| `GET /posts/{slug}` | 详情（含 body_md、prev/next、related[3]） |
| `GET /posts/{slug}/preview?token=` | 草稿预览（管理员签发的短期 token） |
| `GET /tags` | 标签清单（含 published 计数，供筛选栏） |
| `GET /columns?type=` | 栏目树（扁平 + `parent_id`，层级最多三级、父必同类型）。计数两档：`count` = 本级直属，`total` = 自身 + 全部子孙。前台目录栏徽章用 `total`（所以父栏目不会显示成 0 却点得出内容），后台栏目页与「删除后 N 篇解除归属」的确认文案仍用 `count`。内容单 FK 只挂一层，逐层相加不会重复计数 |

### 3.3 模型 — Flow C

| 方法 路径 | 说明 |
|---|---|
| `GET /models?kind=all|3d|render|animation` | Gallery 列表（封面 + media_kind） |
| `GET /models/{slug}` | 详情：`assets[]`（`{kind:"model3d",url,size,storage_key}` 等）、`extra`（faces/materials/software/duration/links） |
| `POST /models/{slug}/download` | 下载计数（返回签名直链或 302 到 `/media/…`） |

### 3.4 杂谈 — Flow D

| 方法 路径 | 说明 |
|---|---|
| `GET /chats?cursor=&limit=20&tag=` | 时间线（游标分页；**列表项额外直出 `body_md`** 供前端 300 字折叠——短内容场景特例） |
| `GET /chats/{id}` | 单条（长文/可分享场景） |

### 3.5 关于 / 站点 / 其他

| 方法 路径 | 说明 |
|---|---|
| `GET /about` | 个人主页整页数据（profile + skills + experience[]，源=顶级管理员账号行）；另带 `team: [{nickname, avatar, signature, bio_md, social_links, skills, experience}]` = **所有在职管理员**的完整资料卡（不含 super，按 id 升序，停用即下架；邮箱/登录名/角色/备注仍一律不下发） |
| `GET /site-config` | 前台运行配置：站点名（顶栏 + 首页大标题 + 各页 `<title>` 后缀）、副标题（首页眉题）、描述（首页介绍正文 + SEO）、**`icon`（首页首屏右侧圆图）**、**`favicon`（标签页图标，空则 `/favicon.svg`）**、导航项[]（显隐+排序）、页脚、主题默认色。原 `sections{hero,posts,models,chats}` 已删（首页改版成 最新/热门/团队 三段，四个类型开关再无消费者） |
| `POST /feedback` | **v1.1 暂缓不实现**（About 仅社交链接；表结构与本端点定义保留） |
| `GET /search?q=&type=` | 全站搜索（返回三类内容混合 top20） |
| `GET /rss`（`/feed.xml`） | RSS 2.0，后端渲染正文 HTML |
| `GET /sitemap.xml` | XML 站点地图（published 详情 + 栏目页，含 lastmod）；Caddy 以 `/sitemap.xml` 转发至此 |
| `GET /sitemap.txt` | 逐行 URL 纯文本（百度 sitemap 提交格式） |
| `GET /robots.txt` | 放行全站、屏蔽 `/admin`；含资源平台验证文件 |
| `GET /baidu_verify_*.html` | 资源平台站点验证文件（env 配置内容直出） |
| `POST /track` | （预留 v1.1）前端 beacon 上报 `{path, referrer}`，204 |
| `GET /health` | 存活检查，无包直出 `{"status":"ok"}` |

---

## 4. 后台 — 认证（Flow E）

### `POST /admin/auth/login`

```json
// req
{ "username": "admin", "password": "…", "remember": true }
// 200 res.data
{ "access_token": "jwt…", "refresh_token": "jwt…", "expires_in": 7200,
  "user": { "id": 1, "username": "admin", "nickname": "…" } }
```
错误：`40101` 密码错误；`42300` 锁定（`retry_after`）；`42200` 空字段。

| 方法 路径 | 说明 |
|---|---|
| `POST /admin/auth/refresh` | `{refresh_token}` → 新双 token |
| `POST /admin/auth/logout` | 服务端记录 + 前端清 token（v1 无黑名单，refresh 旋转） |
| `GET /admin/auth/me` | 当前管理员信息（守卫初始化用） |
| `POST /admin/auth/password` | `{old_password, new_password}` → 改密（需重新登录） |

---

## 5. 后台 — 内容管理（Flow F）

### 列表与筛选

`GET /admin/contents?type=article&status=published&q=&tag=&page=` — 与公开 DTO 相同字段 + `status`、`updated_at`，含 draft/archived。

### 创建 / 更新

`POST /admin/contents` ｜ `PUT /admin/contents/{id}`（全量更新）

```json
// req（article 示例；model 换 type 并给 media_kind/assets/extra；chat 可省 slug/cover）
{
  "type": "article", "status": "draft",
  "title": "…", "slug": "hello-world", "summary": "…",
  "body_md": "…", "cover_asset_id": 12,
  "tags": [{"name":"技术"}, {"id":3}],
  "media_kind": null,
  "extra": { "links": [] },
  "asset_ids": []        // 模型/杂谈关联媒体
}
// 200 res.data = Content（含 status）
// 40900 slug 冲突（data.field="slug"，编辑器 inline 提示）
```

### 状态机与删除

| 方法 路径 | 说明 |
|---|---|
| `PATCH /admin/contents/{id}/status` | `{"status":"published"}`；draft→published 写 `published_at`（已存在则保留首次时间）；published→archived 下架。**发布成功后自动触发前端重建 + 百度推送流水线**（异步，结果见 §5.6 日志；失败不回滚发布） |
| `DELETE /admin/contents/{id}` | 软删→归档？否：**直接删除**（个人站，AlertDialog 二次确认在前端）；关联 content_media 解绑，媒体文件不自动删 |
| `POST /admin/contents/{id}/preview-token` | 签发 15min 预览 token，供新 tab 打开草稿 |
| `POST /admin/contents/{id}/import-images` | 正文外链图片入库。`{"body_md":"…"}`（省略则用服务端已存正文）→ `{body_md, imported[], failed[], skipped[], total}`。服务端逐张下载，以 `{slug}-{图片名}` 命名存入素材库并回写 **`{SITE_URL}/media/…` 绝对地址**（导出到站外仍可访问）；**不自动保存正文**，由编辑器拿到新 Markdown 后自行 PUT。**本地链接一律跳过**（不下载、不入库，只在 `skipped` 里回报原因）：相对/根路径、本站地址（含 www/apex 变体、任意路径）、本机地址（localhost/127.0.0.1/::1）、`data:` 等内联数据。SSRF 防护：域名解析到内网/环回/链路本地即拒，重定向每跳重新校验；单张 ≤5MB、单次 ≤30 张 |

### 素材（Flow F-3）

| 方法 路径 | 说明 |
|---|---|
| `POST /admin/media` | multipart `file`（字段 `purpose`=cover\|inline\|model3d\|video 可选）→ `MediaAsset`；自动压缩图片→生成 webp 缩略图、探测宽高、sha256 命中已有则直接返回旧记录 |
| `GET /admin/media?kind=&q=&category=&content_id=&unused=&page=` | 素材库网格。每条附 `used_by: [{id,title,type,slug}]`（正文 `/media` 链接 / 封面 / 模型附件三处来源，实时计算）；`content_id=` 只看某篇用到的，`unused=1` 只看未被引用的 |
| `GET /admin/media/contents` | 素材库右下拉数据：`{items:[{id,title,type,slug,count}], unused, total}`，按引用条数倒序 |
| `PATCH /admin/media/{id}` | `{"filename":"新名字.png"}` 重命名。**只改展示名**，`storage_key`/`url` 不变，历史链接继续有效；文件名里的路径成分会被剥掉 |
| `POST /admin/media/categorize` | `{ids:[], category}` 批量改分类标签。**不移动文件、不改写正文 URL**（物理搬家会换地址，历史文章与外链会集体失效）；返回 `{updated, denied}`，`denied` 是他人上传的素材 |
| `DELETE /admin/media/{id}` | 被引用时返回 `40900`，data 带 `content_ids` 与 `contents:[{id,title,type,slug}]`，message 直接点名是哪几篇 |

`MediaAsset`：`{id, filename, url, kind, mime, size, width, height, thumb, storage_key, category, uploaded_at}`（`thumb` 为服务端预生成 webp 缩略图 URL，可空）。

> 组织原则：`storage_key` 是素材的永久地址，落盘后不再变动。分类与文件名都只是标签，
> 所以整理素材永远不会让已有链接失效。

### 标签

`GET /admin/tags`、`POST /admin/tags {name}`、`PUT /admin/tags/{id}`、`DELETE /admin/tags/{id}`（自动解除关联）。创建内容时 `tags[]` 支持 `{id}` 或 `{name}`（不存在则自动建）。

### 5.6 SEO / 百度推送（v1.1 新增，Flow F 扩展）

| 方法 路径 | 说明 |
|---|---|
| `GET /admin/seo/config` | 推送开关与配置状态：`{push_enabled, api_configured: true|false, site_url, daily_quota, quota_left}`（不回显 token） |
| `POST /admin/seo/push` | 手动推送：`{content_ids:[..]}` / `{urls:[...]}` / `{pending:true}`，可选 `force:true` → `{success, fail, skipped, already, notice[], remaining}`。**默认去重**：`pushed_urls` 里已成功的地址不再推送，`already` 即被跳过的条数；`skipped` 仍是「入待推队列」的条数。`force:true` 忽略去重强制重推（面板上的「忽略去重」勾选） |
| `GET /admin/seo/push-logs?page=` | 推送日志（triggered_by=manual/publish、URL 集、百度返回、时间），供后台「SEO」面板 |
| `POST /admin/seo/rebuild` | 手动触发前端预渲染重建 → `{queued, merged_with_previous}`；正常情况由发布自动触发（v1.2：**服务器本机 subprocess 脚本构建**，文件锁 + `REBUILD_MERGE_SECONDS` 合并窗口，无外部回调） |
| `GET /admin/seo/jobs?page=` | 重建任务列表 `items[{id,status(running|requested|success|failed|skipped),log尾部,triggered_by,created_at,finished_at}]`，面板轮询展示。**Docker 模式下 job 只能停在 `requested`**（真正构建的是宿主机 watcher，后端不参与），所以本接口在列出前先做一次**对账**：`REBUILD_REQUEST_FILE` 已不存在 ⇒ watcher 只在构建成功时才删它 ⇒ 把所有 `requested` 改成 `success` 并补 `finished_at`。文件还在就一行不动，所以失败重试不会被误报成完成 |

---

### 5.7 管理员账号与权限（v1.4 新增，Flow E 扩展）

顶级管理员（`role='super'`，隐式拥有全部权限、不落授权表）可建其他管理员账号并按权限点+作用域下放管理权；持 `admin:manage` 授权的非 super 账号也能管账号，但**不能**创建或提升 super 身份。

| 端点 | 说明 |
|---|---|
| `GET /admin/admins` | `{total, items:[{id,username,nickname,email,avatar,signature,role,is_super,is_active,note,last_login_at,content_count,media_count,grants,permissions}]}`（`avatar`/`signature` 为 v1.4 资料跟人走带上） |
| `POST /admin/admins` | 建号 `{username,password,email,nickname,note,role='staff',grants:[]}`，**email 必填**。口令 <10 位或缺字母/数字 → `42200`；邮箱格式非法 → `42200`；用户名或邮箱重复 → `40900`（重复邮箱会回告被谁占用）；未知权限点或给不支持栏目作用域的权限点带 `column_id` → `40000` |
| `PUT /admin/admins/{id}` | 变更 `{nickname,note,email,is_active,role,password}` 任意子集（覆盖式，空 body → `40000`；`email` 改动同样受唯一性约束，改回自己原值不算冲突）。停用会 `token_version+=1` 强制下线。资料字段 `{avatar,signature,social_links,bio_md,skills,experience}` 只有 super 可代改，非 super 一带即 `403`（见 §5.8） |
| `PUT /admin/admins/{id}/grants` | **覆盖式**重设权限集合（不是增量）。super 账号无需授权 → `40900` |
| `POST /admin/admins/{id}/reset-password` | 返回一次性 `data.password`（服务端不留明文），旧会话立即失效 |
| `DELETE /admin/admins/{id}` | 仅允许删除名下无内容且无素材的账号，否则 `40900` 并引导改用停用 |

护栏返回码：**40900** = 最后一个可用 super 被停用/降级/删除、super 账号被调 `grants`（隐式全有，无需授权）、名下有内容或素材的账号被删除；**40300** = 停用或降级自己、非 super 触碰 super 身份、无 `admin:manage` 调用本组端点。

**授权链只向上收口**（三条，super 全不受限）：① 任何人不能改**自己**的权限（403）；② `admin:manage` 只能由 super 授出（403）；③ 非 super 的授权者只能授出**自己已具备**的权限点，越界项名写进 403 文案。前端授权面板据此把不可授出的行置灰。

**停用封两条通道**：access（每次请求）与 `POST /admin/auth/refresh` 都查 `is_active`，返回 `40100 账号已停用`；且该判定排在 `token_version` 之前（停用本身会 bump 版本），否则用户只会看到含糊的「登录已失效」。

**邮箱口径（v1.4 追加）**：入库前统一 `strip().lower()` 再判唯一，避免 `Alice@X` 与 `alice@x` 绕过约束；格式校验为正则 `^[^@\s]+@[^@\s]+\.[^@\s]+$`（首尾空格被 trim，中间空格算格式错）。`users.email` 列可空 —— 迁移前已存在的账号（含 seed 出的顶级管理员）为 `NULL`，不强制补填；唯一索引下多个 `NULL` 互不冲突。**它现在也是「忘记密码」的唯一投递地址**（§5.9）：没填邮箱的账号自助重置会被静默挡下（响应仍是同一句话），只能由顶级管理员在界面里代重置。

授权载荷形态：`grants: [{"permission": "content:write", "column_id": 3}]`，`column_id` 为 null 即全局作用域（全局覆盖任意栏目）。

权限点白名单（`app/core/permissions.py`）：`content:write` `content:delete` `comment:moderate` `media:write` `media:delete` `column:manage` `tag:manage` `setting:manage` `stats:view` `log:view` `announcement:manage` `admin:manage`。其中仅 `content:write` / `content:delete` / `column:manage` 支持按栏目作用域（`announcement:manage` 为 2026-10-14 新增，仅全局，v2 语义=可写公告——含管理页列表在内的四个管理端点判它，登录弹窗读侧 `/unread`、`/read` 仅登录，见 §6.5）。

登录与 `GET /admin/auth/me`（§4）响应随之扩展：`user` 增加 `role / is_super / is_active / permissions[] / scoped_column_ids[]`，前端据此渲染菜单与按钮态（服务端仍是唯一安全边界）。

**既有列表接口的归属字段（v1.4）**：

- `GET /admin/contents` 支持 `mine=1`（只看自己上传的）；每条新增 `owner_id`、`owner_nickname`、`can_edit`、`can_delete`、`denied_reason`（无权限时给原因文案，有权时为 null）。详情/看板/preview-token 一律可读（"可见不可改"），写端点（POST/PUT/PATCH/DELETE/reset-likes/column-bulk）按归属+作用域双门校验，拒绝返回 403 且 message 区分「不是你的内容」与「没有该栏目的管理权」。
- `POST /admin/contents/column-bulk` 响应新增 `denied: [id]`（无权变更的条目被跳过而非整批失败），原有 `updated/skipped` 语义不变。**起点与终点都要过栏目作用域**：把自家内容批量搬进自己没权限的栏目、或从被授权栏目移成无栏目，同样进 `denied`（与单条 PUT 的规则一致，批量不是后门）。
- `GET /admin/media` 支持 `mine=1`；每条新增 `uploader_id`、`uploader_nickname`、`can_delete`。上传/归类需 `media:write`，删除需 `media:delete` 且只能删自己上传的（仍受"被内容引用则 409"保护）。
- `GET /admin/columns` 每条新增 `can_manage`；栏目改名需 `column:manage`（全局或该栏目）；**新建栏目只能凭全局 `column:manage`**（新栏目没有 id，无法按栏目授权）；**删除栏目时若该栏目下还有非本人或无主内容，也需全局 `column:manage`**（删除会把它们的 `column_id` 置空，属跨归属写入，403 会回报受影响条数）。删栏目同事务清掉指向它的栏目级授权（`scope_id` 无外键，且 SQLite 会复用最大 rowid）。
- `POST /admin/media/categorize`（批量归类）需 `media:write` **且按归属逐条判定** —— 归类会移动磁盘文件并重写引用它的正文 URL，属写操作；响应为 `{moved, denied:[id]}`，非本人上传（或不存在）的 id 进 `denied`，不会被移动。
- `POST /admin/comments/moderate` 与 `DELETE /admin/comments/{id}` 需 `comment:moderate`，**不校验内容归属**（全站待审队列共享），审核写入 `reviewed_by_id` 留痕。新评论提交后会**给内容作者发一封通知信**（见 §5.10），蜜罐与冷却挡下的不触发。
- 标签写需 `tag:manage`；`PUT /admin/settings/{group}` 需 `setting:manage`；`GET /admin/logs/*` 需 `log:view`；`GET /admin/stats/*` 与 SEO 面板读需 `stats:view`；百度推送 `POST /admin/seo/push` 与重建 `POST /admin/seo/rebuild` 仅顶级管理员；更新公告四个管理端点（含管理页 GET 列表）需 `announcement:manage`，登录弹窗读侧 `GET /admin/announcements/unread` 与 `POST /admin/announcements/read` 仅登录即可（§6.5）。

### 5.8 我的资料（v1.4 新增，Flow E 扩展）

资料跟人走：`site_settings.profile` 组已废弃，旧值由迁移 `a8c1e4f7b205` 一次性迁进顶级管理员那一行（只写目标列仍为空的字段，不覆盖账号自己的编辑；迁完 `DELETE FROM site_settings WHERE key LIKE 'profile.%'`）。

| 端点 | 说明 |
|---|---|
| `GET /admin/profile` | 自己那份，附 `editable[]`（本账号能改的字段，前端据此显隐）与 `is_super` |
| `PUT /admin/profile` | **改自己不需要任何权限点**（`setting:manage` 只管站点设置）；空 body → `40000`；提交越界字段 → `403`，文案「不能修改「xx」」 |

字段口径：**七项资料（`nickname / avatar / signature / social_links / bio_md / skills / experience`）每位管理员都能改自己那一份**（`avatar` 是 API 名，落 `users.avatar_url` 列；昵称提交空值会回落成登录名）。`GET/PUT /admin/profile` 的作用对象永远是当前登录者，所以「谁能改什么」不靠字段白名单区分身份，而由「只能改自己」这条边界保证。在职管理员的资料会上 About 卡片，因此改任一影响 About 的字段都自动入队预渲染重建（停用的人不触发）。

**代改他人**只有 super，且走账号端点：`PUT /admin/admins/{id}` 的请求体可带 `avatar / signature / social_links / bio_md / skills / experience`；非 super 带任一资料字段 → `403`（「只有顶级管理员能代改他人资料」）。

**改密码入口已迁移（v1.4 同日）**：端点没动，仍是 `POST /admin/auth/password`（需旧密码，新密码 ≥8，成功即 `token_version += 1` 全端下线），但界面入口从「站点设置 → 账号安全」移到了「我的资料 → 密码设置」板块，站点设置里那个分区已删。`PUT /admin/profile` 支持**部分字段提交**，前端正是按板块逐块提交（基本信息一次三字段、社交链接/简介/技能栈/经历各一次单字段），所以「一块一保存」不需要新端点。

**隐私边界**：公开侧只下发详情里的 `author.{nickname, avatar}` 与首页/关于页那份资料，`email / username / role / note / is_active` 绝不出现在公开响应。

**About「管理团队」名单（v1.4 追加）**：`/about` 的 `team[]` = **所有在职管理员**（`is_active` 且非 super），按 id 升序，每人一份完整资料（`nickname/avatar/signature/bio_md/social_links/skills/experience`）——前台把每个人都渲染成与主体同款的全宽卡片，所以不能只给两项。身份类字段（`email/username/role/note`）仍然绝不下发；内容页署名 `author` 依旧只有 `nickname/avatar` 两项。口径演进值得记一笔：同日先定成「加 `show_in_about` 逐个勾选」（迁移 `c7d3b9e0a412`），当天即被推翻为「全员露出、停用即下架」，因该列从未上线，故用前滚迁移 `d1f4a6c8b307` 删列（alembic 链只增不减）。super 不进名单（它是 About 主体，同页不出现两遍）。**因为在职者必然上名单，任何成员的资料变更与启停都要入队预渲染重建**（`services/profiles.py` 的 `ABOUT_TRIGGER_FIELDS` 与 `about_visible()` 是 `/admin/profile` 与 `/admin/admins` 两条路径共用的唯一口径）；代价是新建一个 staff 就会出现在公开页，不想露出只能停用。`bio_md/skills/experience` 已放开给**每位管理员自己填**（同日先定「仅 super 可改」，当天因每人卡片都要渲染这三项而推翻）——越界面由「`/admin/profile` 只能改自己」这一条守住，不是靠字段白名单。

### 5.9 忘记密码：自助口令重置（v1.4 追加，免鉴权）

| 端点 | 说明 |
|---|---|
| `POST /admin/auth/forgot-password` | body `{username}`，**无需登录**。生成 16 位随机口令（复用 `admin_accounts.gen_password`），经邮件通道送达 |

响应只有一个口径：**永远返回同一句话**（放在 `data` 里，措辞由服务端 `password_reset.UNIFORM_MESSAGE` 唯一持有，前端不得改写）。账号不存在、已停用、未填邮箱、被冷却挡下、发信失败 —— 全部同一句话、同一形状，因为「有没有报错」本身就是可枚举的信息；真实原因只进 `app.log`。唯一会明确报错的情形是**邮件通道整体不可用**（未配置或密文解不开）→ `50300`「邮件通道未配置」，这一步在查库之前完成，所以不区分任何账号。

**发不出去就不改口令**：`apply_reset()`（写 hash、`token_version+1` 强制下线、清 `failed_attempts/locked_until`）先落在会话里，**发信成功才 `commit`**，`MailError` 则整笔 `rollback` —— 旧口令继续可用，连"被强制下线"都不会发生。顺带效果：被 5 次失败锁定的账号可以靠它自己回来。

限流（进程内，落库无新列）：同账号 60s 冷却、同账号每小时 3 封、全站每小时 20 封（保住发信邮箱不被 QQ 风控）。窗口滚动清理放在**所有提前返回之前**，冷却表只留窗口内条目。**按 IP 限流暂不做**：线上没有 `ProxyHeadersMiddleware`，`request.client.host` 恒为 Caddy 的容器 IP，按 IP 计数等于把所有访客当同一台机器（既有缺陷，另开一轮）。

`docs/api-reference.md` §5.7 那句「邮箱仅作账号数据与留痕用，不触发任何发信」到本节失效：**顶级管理员在界面里代重置**仍是"一次性口令只显示一次、服务端不留明文"，而**自助重置**会把新口令发到账号绑定邮箱（明文只出现在那一封邮件里，不进 HTTP 响应、不进日志）。

### 5.10 评论通知邮件（v1.4 追加）

两封信，都**先进 `mail_queue` 再由队列冲出**，没有一处直发：

| 信 | 触发 | 收件人 | 主题/正文 |
|---|---|---|---|
| 作者通知 | `POST /comments` 评论成功入库后（后台任务） | `contents.created_by_id` 的 `users.email`；作者不存在/停用/未填邮箱 → **回落顶级管理员**；两者都无 → 跳过并记 warning | 《标题》收到新评论；正文含评论者昵称与邮箱、提交时间、前台链接、评论原文（截 300 字）、审核页链接 |
| 评论者通知 | `POST /admin/comments/moderate` **首次** 置为 approved | 评论者自报邮箱 `comments.email` | 你的评论已通过审核：《标题》；正文含内容标题、前台链接、他自己的评论原文 |

- **去重靠 `comments.notified_at`（持久列），不靠"队列里有没有行"**：所以「通过→拒绝→再通过」也只发一封；重复点「通过」同样不重发。蜜罐命中与 60s 冷却挡下的评论两封都不触发。
- 审核响应新增 `notified` 计数（`{"updated": n, "notified": m}`），出信在 `BackgroundTasks` 里跑，管理员不等 SMTP。
- **额度是全站一份**：`mail_queue.HOURLY_LIMIT = 30 封/小时`，作者通知、评论者通知与忘记密码共同消耗（同一个发信邮箱，分开计数等于没有总闸）。超额的信留在队列里，下一窗口自动补发；连续失败会触发整队退避（详见 §5.11）。
- 失败语义：评论此刻已 commit，通知失败**不回滚、不向提交者报错**，只记 warning；通道未配置算"延后"而不是"失败"（不烧重试次数、不触发退避）。
- 注入面：访客输入只进正文，绝不进 To/From；主题就地压平换行与连续空白。
- 隐私：给评论者的信**不含作者邮箱**，也不含其他人的评论。

### 5.11 出站发信队列（v1.4 追加，无对外端点）

`mail_queue` 表是本站唯一的发信出口。状态只有 `pending / sent / dropped` —— 等待重试的行仍是 `pending`（配 `attempts>0` 与 `next_try_at`），不设 `failed`，避免出现"failed 但其实还会再发"的两处真相。

- **额度**：最近 1 小时内 `status=sent` 的行数 < 30（`HOURLY_LIMIT`）。忘记密码与评论通知共用。
- **退避**：最近 15 分钟内 ≥3 次失败且最新一次仍是失败 → 暂停整条队列到「最后一次失败 + 30 分钟」；期间若有任何一封成功发出，说明对端活着，不连坐。动机是防"积压在下一窗口集中冲出 → 再被拒 → 雪球"。
- **重试**：失败则 `attempts+1`、`next_try_at` 推后 1 小时；5 次用尽转 `dropped` 并记 warning（防永久堆积）。
- **通道未配置 = 延后，不是失败**：不烧 `attempts`、不触发退避 —— 站点没开通知和发信失败是两件事。
- **额度与退避全部从表推导**，没有独立计数器，所以后端重启/重建不会把承诺冲掉。
- **忘记密码的信不入队**（明文口令不能在库里等下一小时），但成功发出后写一条 `body_text` 为空的 `sent` 台账行来占额度；**台账不含正文**。
- **并发占位**：`drain` 发每一封前先用一条 `UPDATE ... WHERE status='pending' AND next_try_at<=now` 把 `next_try_at` 推到一小时后，`rowcount!=1` 就跳过 —— 两个 drain 并发（同一秒的两个评论请求后台任务、或 cron 兜底撞上线上请求）否则会把**同一封信发两次**，这是本地实测抓到的真缺陷。崩在占位之后只会晚一小时重试，不会丢。
- 冲刷触发点：每次入队后顺带 `drain`，加上 CLI `mail-drain` 的 cron 兜底（没有兜底，最后一封积压可能几小时没人碰）。`mail-status` 打印各状态计数、`paused_until` 与最近一条错误。
- 队列期间评论者邮箱与评论正文以明文存在本表（与 `comments` 同级敏感，但确实是多一份副本，会随 `app.db` 进备份）。

### 5.12 评论头像（v1.4 追加）

`GET /comments` 与 `GET /admin/comments` 的 `avatar` 是**本站自服的静态图包路径**（`/avatars/NN.svg`），不再是 Gravatar 外链：`md5(邮箱去空格转小写) % AVATAR_COUNT` 选一张，同一邮箱恒定同一张，公开响应仍不含明文邮箱。

- **管理员邮箱命中 → 改用他的个人资料头像**：`services/comment_avatars.py.load()` 一次查出 `{归一化邮箱: avatar_url}`（只收邮箱与头像都非空的账号），`resolve()` 命中就返回 `users.avatar_url`、否则回落图包；比较前两边统一 `strip().lower()`（评论入库只 strip，而 `users.email` 入库已 lower，不归一就永远匹配不上大写邮箱）。**不查 `is_active`**：头像不是权限，且停用账号的历史评论不该突然变脸。前后台同源，同一条评论两边同一张。
- **已知代价（2026-10-06 拍定）**：评论邮箱是自报未验证的，知道某管理员邮箱的人填上就能拿到那张头像、看着像官方回复；冒充面靠先审后显人工把关（审核页看得到 email 与提交 IP）。

- 图包由 `frontend/scripts/gen-avatars.mjs` 离线生成（`npm run gen:avatars`），素材是 **DiceBear 的 Open Peeps 风格，设计许可 CC0 1.0**（作者 Pablo Stanley），许可信息随每张 SVG 的 `<metadata>` 落进文件；构建产物 `dist/avatars/` 由 Vite 从 `public/` 原样拷贝，线上零第三方请求。
- **张数是一处跨仓库常量**：`backend/app/core/text.py` 的 `AVATAR_COUNT` 必须等于 `frontend/public/avatars/*.svg` 的文件数，`tests/test_comment_avatars.py` 会直接数目录来钉住。改张数要同时改常量并重跑生成器，否则部分邮箱会取到 404 的图。
- 换风格只需换生成器里的 style 包与色板（`@dicebear/styles` 有 42 个 CC0 风格可免署名使用；CC BY 4.0 的那批需要署名，别混进来）。

---

## 6. 后台 — 站点设置（Flow G）

按分区分组读写（对应「每分区独立保存」）：

| 方法 路径 | group 与 schema |
|---|---|
| `GET /admin/settings` | 全部分组一次拉取。**`mail` 组的 `api_key` 只写不回显**：响应里换成 `api_key_set`（能否解出明文）与 `api_key_hint`（明文尾 4 位），任何登录态都能读这份掩码 |
| `PUT /admin/settings/{group}` | `group ∈ site / nav / footer / mail`（`profile` 组已在 v1.4 废弃，改它返回 `40000`，见 §5.8；**`home` 组已整组废弃** —— 首页改版成 最新/热门/团队 三段后，四个类型开关与「精选内容 id」都再无消费者，改它同样返回 `40000`，旧的两行由迁移 `b7f3d2c8a5e4` 清除）。`mail` 三个键：`api_url / api_key / override_to`；**`api_key` 留空 = 保留原值**（界面回显的是掩码，若按空串覆盖就等于一次保存把凭据洗掉），派生键 `api_key_set / api_key_hint` 会被写入路径剔除，不会变成假设置行 |

```json
// PUT /admin/settings/site
{ "title": "泠曦 Blog", "subtitle": "", "description": "…", "favicon": "", "icon": "" }
// 站点名→首页大标题与各页标题后缀、副标题→眉题（空则该行不渲染）、描述→首屏介绍正文 + SEO meta、
// icon→首屏右侧圆图（空则整格不渲染）、favicon→<link rel=icon>（空则回落内置 /favicon.svg）

// PUT /admin/settings/nav
{ "items": [{"label":"博客","path":"/blog","visible":true,"order":1}] }

// PUT /admin/settings/footer
{ "links": [{"platform":"Personal Mail","url":"https://mail.lingxi-reihi.cn"}], "copyright":"…", "beian":"…" }
// links 就是首页首屏按钮下方那行「友站」的唯一数据源：只认 http(s) 完整地址（javascript:/data:/协议相对 // 一律由前端丢掉，不进 <a href>）；platform 留空则拿对方域名当文字。
// copyright / beian 目前只入库、页脚未渲染（页脚固定输出 © 年份 站点名 · RSS · Sitemap），后台那两项已标注「暂不渲染」
```
响应 `200 data = 该分组最新值`；错误 `42200` 字段校验。

---

## 6.5 后台 — 更新公告（Flow H 扩展，2026-10-14 新增；v2 同日改「管理页 + 登录弹窗」形态）

管理页（`/admin/announcements`）与全员登录弹窗的数据源。**鉴权分两档（v2）**：四个管理端点（含管理页列表 GET）需 `announcement:manage`，无权限 `40300`「你没有更新公告权限」；登录弹窗读侧 `GET /unread`、`POST /read` **仅登录即可**（`get_current_admin`，不判权限点）——v1 曾把读写同钉 `announcement:manage`，用户换 staff 账号实测发现其他管理员看不到公告，同日反转口径。本期无公开端点（`status/published_at` 为前台预留）；写成功**不触发**重建与 sitemap（前台无消费者）。

| 方法 路径 | 说明 |
|---|---|
| `GET /admin/announcements?limit=20` | 需 `announcement:manage`。`limit` 夹在 1..100。排序口径唯一实现处在服务层：先按 status 分组（published 在前、draft 恒垫后——改回草稿的旧发布条目带 `published_at` 也不混入发布组），组内有 `published_at` 者在前按发布时间倒序、无者垫后，同级按 `created_at` 倒序（SQLite 无 NULLS LAST，用 `published_at IS NULL` 双键等价）。`data = {items: [Announcement]}` |
| `POST /admin/announcements` | 需 `announcement:manage`。req `{title(1–200), body_md="", status="published"|"draft", published_at: datetime|null}` → `data = Announcement`；`created_by_id` 记当前登录者；status=published 而日期为空时服务端补 `now` |
| `PUT /admin/announcements/{id}` | 需 `announcement:manage`。部分更新（照 `/admin/profile` 口径，body 缺省/null 字段一律不动）→ `data = Announcement`。发布语义：由无到有置 published 且无首发时间 → 补 now；**重发布不覆盖首发时间**；改回 draft 保留 `published_at` |
| `DELETE /admin/announcements/{id}` | 需 `announcement:manage`。→ `data = {deleted: id}`；该公告的已读水位行由 FK CASCADE 连带清除，不留悬空计数 |
| `GET /admin/announcements/unread?limit=20` | **仅登录**（登录弹窗用）。当前登录者**未读**的公告（`announcement_reads` 里无 `(id, 当前 user)` 行），**只推 `status=published`**——草稿是作者自己没写完的备忘（含「发布后又改回草稿、仍带旧 `published_at`」的行），不该弹给其他人。沿用上面同一排序口径与出参，`limit` 夹 1..100。`data = {items: [Announcement]}` |
| `POST /admin/announcements/read` | **仅登录**。body `{ids: [int]}` → `data = {marked: n}`：把这批 id 记为该用户已读。`(announcement_id, user_id)` 复合主键天然去重，**幂等**（重复上报不报错、不重复写行）；**只接受真实存在的 id**，不存在的静默跳过、不因此 400（弹窗只是尽力上报，不该因脏 id 打断用户）；空数组直接回 `{marked: 0}` |

已读水位表 `announcement_reads`（迁移 `d3a9c5e7b412`）：`(announcement_id, user_id)` 复合 PK + `read_at`，两侧 FK **CASCADE**（删公告/删用户都连带清行，「未读」永不需要脏数据兜底）。本期不做已读可视化端点（谁读过什么，无人消费）。

**发布副作用（2026-10-14 追加）**：`POST` 与 `PUT` 在**首次发布**（新建即 `published`，或草稿转 `published`）时，会给**每个 `is_active` 且填了邮箱的管理员**各入队一封通知信（`mail_queue.kind="announcement"`，主题 `【站名】新公告：《标题》`，正文 = 标题/日期/作者/Markdown 原文前 300 字/后台链接），实际出信由 `BackgroundTasks` 与 `*/15` cron 的 drain 按 30 封/小时的全站额度发。编辑已发布的公告**不重发**；「改回草稿再发布」按新发布算，会再发一封（去重靠状态转换，未给 `mail_queue` 加公告外键）。通知失败只记 warning，绝不影响公告保存。

```json
// Announcement
{ "id": 1, "title": "…", "body_md": "Markdown 原文", "status": "published",
  "published_at": "2026-10-14T12:00:00Z", "created_at": "2026-10-14T11:58:03Z",
  "created_by": "昵称" }
```
`created_by` 为作者昵称（复用 `author` 白名单口径，只出 nickname；作者账号被删则 SET NULL 成 null）。

错误：`40300` 无 `announcement:manage`（仅管理端点；`/unread`、`/read` 未登录是 `40100`）；`40400`「公告不存在」（PUT/DELETE 未知 id）；`42200` 校验（标题空串/纯空白、status 非法值，`data.fields[]` 前端 inline 展示）。

---

## 7. 后台 — 统计监控（Flow H）

| 方法 路径 | 参数 | 返回 |
|---|---|---|
| `GET /admin/stats/overview` | — | `{today:{pv,uv}, yesterday:{pv,uv}, total_published:{article,model,chat}, storage_used, media_count}`（环比由前端算） |
| `GET /admin/stats/trend` | `start=2026-09-01&end=2026-09-22`（≤366d，默认 7d） | `{days:[{day,pv,uv}]}` |
| `GET /admin/stats/top-content` | `range=7d&limit=10&type=` | `[{content_id,title,type,pv,uv}]` |
| `GET /admin/stats/content/{id}` | `start&end` | 单篇下钻 `{days:[{day,pv,uv}], sources:[{referrer,pv}]}` |
| `GET /admin/stats/sources` | `range=7d` | `{items:[{referrer,pv}], direct, search, social, other}`（饼/条图）。`referrer` 取值优先前端上报的 `X-Page-Referrer`（落地页 `document.referrer`，见架构文档 §6），头缺失/非法才回落 HTTP `referer`。分类口径：空 referrer 与**站内自跳**（host 等于 `SITE_URL` 的 host 或其 www/去-www 变体，精确比对不做后缀匹配）都算 `direct` —— 否则「从列表点进详情」会被算成外部来源，把「其他」那一栏灌满自家流量。搜索域名表含 baidu/bing/google/360/sogou/quark(sm.cn)/yandex/duckduckgo |
| `GET /admin/stats/export` | `start&end` | `text/csv` 附件（日聚合明细） |
| `GET /admin/feedbacks?handled=&page=` | — | **v1.1 暂缓**（留言功能未开放） |
| `PATCH /admin/feedbacks/{id}` | — | **v1.1 暂缓** |

---

## 8. 媒体文件服务（非 /api）

| 路径 | 说明 |
|---|---|
| `GET /media/{storage_key}` | 静态直出（Caddy 或 FastAPI StaticFiles）。长缓存 `Cache-Control: public, max-age=31536000, immutable`（文件名含 hash 段）。`kind=model3d/video` 响应带 `Content-Disposition: attachment`（下载即计数走 3.3 download） |
| `GET /media/thumbs/…` | ~~独立缩略图路由~~ **实现差异**：缩略图与原件同走 `/media/{storage_key}`，thumb 的 storage_key 由 `MediaAsset.thumb` 字段给出（上传时预生成 webp） |

---

## 9. Flow ↔ 接口映射速查

| Flow | 调用序列 |
|---|---|
| A 首页 | `GET /home`（+ `GET /site-config` 应用启动时一次） |
| B 博客 | `GET /posts` → `GET /posts/{slug}`；筛选回 `GET /posts?tag&q` |
| C 模型 | `GET /models?kind` → `GET /models/{slug}` →（`POST …/download`） |
| D 杂谈/关于 | `GET /chats?cursor` →（`GET /chats/{id}`）；`GET /about` |
| E 登录 | `POST /admin/auth/login` →（过期时 `refresh`）→ `GET /admin/auth/me` |
| F 内容管理 | `GET /admin/contents` → `POST /admin/media`* → `POST/PUT /admin/contents` → `PATCH …/status`（自动触发 rebuild+push）→（`GET /admin/seo/jobs` 轮询、失败时 `POST /admin/seo/push` 重推）→ `POST …/preview-token` |
| G 设置 | `GET /admin/settings` → `PUT /admin/settings/{group}`（逐区） |
| H 监控 | `GET /admin/stats/overview` + `trend` + `top-content` + `sources`（并行）→ 下钻 `content/{id}` → `export`；SEO 面板：`GET /admin/seo/push-logs` |
| H 公告管理页 | `GET /admin/announcements`（需 `announcement:manage`，路由与侧栏同权限，无权限者整页/菜单不可见）→ 增改删走 `POST/PUT/DELETE /admin/announcements*`（§6.5，不接 rebuild/sitemap） |
| H 全员登录弹窗 | `auth.ready` 后 `GET /admin/announcements/unread`（仅登录、只推 published、一次登录只拉一次、失败静默）→ 非空弹出 → 关闭整批 `POST /admin/announcements/read` 标已读（§6.5） |
