# 更新公告（全员登录弹窗 + 独立管理页）设计

日期：2026-10-14 · 状态：v2 已获用户批准（v1 实现完成后经用户实测反馈改口径，见 §9 变更记录）

## 1. 背景与目标

用户要求在后台新增「更新公告」功能。v2 口径（AskUserQuestion 四项全选）：

1. **可见面**：本期仅后台，但数据模型预留前台（含 `status` 字段，以后接前台不加迁移）。
2. **形态**：**所有在职管理员登录后台都会弹出公告弹窗**（未读时）；管理入口在**独立页**
   `/admin/announcements`。v1 的「仪表盘内嵌管理卡」已撤销（见 §9）。
3. **正文**：Markdown，复用 `renderMd()` + `.prose`（vue 主题，2026-10-14 已上线）。
4. **权限（v2 收窄）**：`announcement:manage` 只管**写**（增删改，管理页用）；
   **读全员开放**（任何在职管理员登录即可，无需权限点）——与 About 名单「凡在职管理员都可见」同口径。

## 2. 数据层

新表 `announcements`（alembic 迁移，down_revision = `b7f3d2c8a5e4`）：

| 列 | 类型 | 说明 |
|---|---|---|
| id | PK int | |
| title | String(200) | 必填，非空 |
| body_md | Text | Markdown 正文，默认 `''` |
| status | String(16) | `draft` / `published`，默认 `published`（本期界面只产 published；字段为前台预留） |
| published_at | TZDateTime nullable | 首次置 published 时写入；改回 draft 不清空（重发布不覆盖首发时间） |
| created_at / updated_at | TZDateTime | 同 contents 口径（`core.db.utcnow`） |
| created_by_id | FK users.id ON DELETE SET NULL, index | 同 contents |

排序口径（唯一实现处 `services/announcements.py:list_announcements`）：
`status='published'` 的按 `published_at DESC NULLS LAST`（SQLite 无 NULLS，用
`(published_at IS NULL), published_at DESC` 双键），`draft` 恒排在其后、组内
`created_at DESC`。API 出参不分页（个人站量小），`limit` 默认 20、上限 100。

模型文件 `backend/app/models/announcement.py`，在 `models/__init__.py` 注册（迁移
autogenerate 依赖）。

### 2.1 已读表（v2 新增）

新表 `announcement_reads`（alembic 迁移，down_revision = `c9e2f4a7b108`）：

| 列 | 类型 | 说明 |
|---|---|---|
| announcement_id | FK announcements.id ON DELETE CASCADE | 复合 PK 之一 |
| user_id | FK users.id ON DELETE CASCADE | 复合 PK 之一 |
| read_at | TZDateTime | 标已读时刻 |

`(announcement_id, user_id)` 复合主键 = 天然去重（重复上报走 INSERT OR IGNORE 语义，幂等）。
删除公告级联清掉其已读行（CASCADE），不会留下悬空计数；删用户同理。
「未读」= `announcements` 中不存在 `(id, 当前 user)` 已读行的集合。

## 3. 后端 API

Router `backend/app/api/admin/announcements.py`，`APIRouter(prefix="/announcements")`，
`main.py` 挂 `/api/v1/admin` 下。**v2 按读写分两档鉴权**：

写侧（管理页用）—— `ctx: AdminContext = Depends(get_admin_ctx)` + 首行
`ctx.need("announcement:manage", subject="更新公告")`：

- `GET /admin/announcements?limit=20` → `{items: [...]}`，含 `created_by` 昵称（复用
  `author` 白名单口径：只出 nickname，不出 email/username）
- `POST /admin/announcements`（`AnnouncementReq`：title 1-200、body_md、status Literal）
- `PUT /admin/announcements/{id}`（部分更新 `model_dump(exclude_unset=True)`，同 profile 口径）
- `DELETE /admin/announcements/{id}`

读侧（登录弹窗用）—— `_: User = Depends(get_current_admin)`，**不判权限点**：

- `GET /admin/announcements/unread` → `{items: [...]}`：当前登录者**未读**的公告，
  **只推 `status='published'`**（草稿是作者自己没写完的备忘，含「发布后又改回草稿、仍带旧
  `published_at`」的行，不该弹给其他人），
  沿用 §2 同一排序与 `to_dict` 出参，`limit` 默认 20、上限 100。
- `POST /admin/announcements/read`（body `{ids: [int]}`）→ `{marked: n}`：把这批 id 记为该
  用户已读。**幂等**（重复上报不报错、不重复写行）；**只接受真实存在的 id**（不存在的静默跳过，
  不因此 400——弹窗只是尽力上报，不该因脏 id 打断用户）；空数组直接回 `{marked: 0}`。

错误：id 不存在 → `AppException(NOT_FOUND)`；title 空白 → 422（v1 实测裁决，见 §9）；
未知 status → 422。统一 `errors.ok()` 包。**不调 `trigger_rebuild`、不调 `sitemap.invalidate()`**
——前台无消费者。

权限：`core/permissions.py` 的 `PERMISSIONS` 含 `"announcement:manage"`（v2 语义=可写公告）；
**不进** `SCOPED_PERMISSIONS`（只授全局）。

## 4. 前端（登录弹窗 + 独立管理页）

### 4.1 登录弹窗（所有管理员）

新组件 `frontend/src/views/admin/AnnouncementGate.vue`，挂在 `AdminLayout.vue` 内（与
`n-config-provider` 同层，登录态就绪后才存在）：

- 触发：`onMounted` → 等 `auth.ready`（me 探测完成）后 `GET /admin/announcements/unread`。
  非空则弹 `NModal`（preset card，标题「更新公告（N 条未读）」）。**一次登录只弹一次**：
  拉取与弹出各带一次性 guard（`fetched` 标记），关掉不再请求，路由切换不重复弹。
- 内容：逐条 = 标题 + 日期（`published_at ?? created_at` 取 `YYYY-MM-DD`）+ 作者昵称 +
  Markdown 正文（`renderMd(body_md).html` 进 `.prose`），整体 `max-h` 限高滚动。
- 关闭（含点遮罩/×/「我知道了」按钮）：`POST /admin/announcements/read` 上报本次列出的
  全部 id，**先关后报也不允许漏报**——在 `@update:show` 的关闭分支里统一发一次。
  上报失败只 `message.warning`，不重开弹窗（下次登录仍会看到，因为服务端没记上）。
- 无任何可见入口给「没有未读」的人：unread 为空 → 不渲染弹窗、不占位。
- 拉取失败（网络/5xx）静默：不打扰登录流程，仅 console 之外不留痕（弹窗是增益，不是必经步骤）。

### 4.2 管理页（有 announcement:manage 者）

新页 `frontend/src/views/admin/AnnouncementsView.vue`，路由 `/admin/announcements`
（`meta: { perm: 'announcement:manage' }`，全局守卫已覆盖），侧栏 `AdminLayout.vue` 的
`ALL_ITEMS` 加一项 `📢 更新公告`（带同一 `perm`，无权者菜单不显示）。

页面 UI = v1 卡片那套原样搬迁（列表 + 状态徽章 + 日期 + 作者 + `.prose` 正文 + 行内
编辑/删除 + 新建弹窗），差别只在：
- 顶层照 ColumnsView/TagsView 加页标题行；
- 新建/编辑弹窗的日期语义不变（留空 = 存草稿、有日期 = published，`today()` 用本地日期）；
- 列表正文限高从卡内 `max-h-72` 放宽为 `max-h-96`（整页空间更足）。

**v1 的 `AnnouncementCard.vue` 与 DashboardView 的挂载一并删除**（不留死代码），
`DashboardView.vue` 除撤除外不动其他区块。

### 4.3 API 层

- `types.ts`：`Announcement` 不变。
- `api/index.ts` 的 `adminAnnouncementsApi` 加两方法：`unread()`、`markRead(ids)`。
- `AdminsView.vue` 的 `PERMS` 文案表该行改为
  `{ key: 'announcement:manage', label: '更新公告', hint: '公告的新建/编辑/删除（读全员开放）', scoped: false }`。

## 5. 测试与验收

后端契约测试 `backend/tests/test_announcements.py`：v1 已有 11 例（CRUD 全链、无权限 staff
403、super 默认可用、title 空白 422、未知 status 422、排序含「带旧发布时间的草稿仍垫底」、
SET NULL、404、schema）。v2 追加 ≥5 例：

1. `unread` 全员可读：无 `announcement:manage` 的 staff 调 `GET /unread` → 200 且拿到全部公告
   （对照：同一 staff 调 `GET /admin/announcements` 仍 403）。
2. 标已读后 `unread` 转空；未标的另一用户仍看得到（**多用户互不影响**）。
3. `POST /read` 幂等：同批 ids 报两次 → 第二次仍 200、`announcement_reads` 行数不增。
4. `read` 容忍脏输入：不存在的 id 与空数组均 200，不写悬空行（FK CASCADE 前提是不存在即跳过）。
5. 删公告级联清已读行（`DELETE` 后该 id 在 reads 中计数为 0）。

迁移端到端：`upgrade head` → 两表在 → `downgrade -1` → reads 表消失 → 再 `upgrade`。

前端：`npx vue-tsc -b` 干净；本地实测退出门（浏览器，controller 执行）：
① admin 建一条含表格/代码块的公告 → 管理页可见；
② 换 staff 账号（无 manage 权限）登录 → **弹窗自动出现**、正文渲染正确、侧栏无「更新公告」菜单；
③ 关闭弹窗 → 重登不再弹（DB 有 reads 行、`unread` 回空）；
④ 再建一条新公告 → 该 staff 重登又弹（只弹新的那条）；
⑤ 明暗两态各一次读数；⑥ console 零新增报错；⑦ 仪表盘上 v1 的卡已消失。

## 6. 文档同步

- `docs/backend-architecture.md` §4.1 补 `announcement_reads` 表行；§5.1 权限点语义改「可写公告，读全员」。
- `docs/frontend-design.md`：Flow H 的 H4 撤除说明 + 新增公告管理页 Flow（含登录弹窗）。
- `docs/api-reference.md` §6.5 补 `unread` / `read` 两端点（标注仅登录）、§9 速查表补行。

## 7. 上线

走 personal-web-deploy-verify-loop 七步：本地验证 → commit/push → 服务器 pull →
**两次新迁移（c9e2f4a7b108 + reads 表）→ 上线前备份库**（`wal_checkpoint` + integrity，tar 到 ~）
→ `compose build backend` + `up -d`（日志确认两段迁移都跑）→ 前端重建（避开 4 小时整点）→
线上验证（`/admin/announcements/unread` 未登录 401、新 chunk 命中、公告表在）。

## 8. 边界与不做

- 不做前台展示、不做 RSS/首页公告位（status 已预留，另立批次）。
- 不做附件/图片上传（正文可写 Markdown 引用已有素材 URL）。
- 不做分页/搜索/软删；不做公告排序拖拽。
- 不做「稍后再读」/逐条已读勾选：弹窗关闭即整批标已读（v2 拍板）。
- 不做已读记录的后台可视化（谁读过什么，本期无人消费）。
- 仪表盘其余统计区块布局不动（v1 的公告卡撤除后回到原状）。

## 9. 变更记录

**v1 → v2（2026-10-14，用户实测后反转形态口径）**

v1 按「合并到仪表盘、读写同权限」实现完毕（分支 `feat/admin-announcements` 8 提交，
230 例全绿、终审 ready-to-merge，**未合并未上线**）。用户实测时换一个 staff 账号登录，
发现**其他管理员根本看不到公告**——因为 v1 把读也钉在 `announcement:manage` 上，而该权限
默认只有 super 有。据此改口径：

| 项 | v1 | v2 |
|---|---|---|
| 展示形态 | 仪表盘内嵌管理卡（有权限才渲染） | 登录弹窗（全员）+ 独立管理页 |
| 读权限 | 需 `announcement:manage` | 仅登录即可 |
| 写权限 | 需 `announcement:manage` | 不变 |
| 已读状态 | 无 | `announcement_reads` 表逐条记录 |
| 新路由/菜单 | 明确不做 | 做（`/admin/announcements`） |

v1 的实现不作废：`announcements` 表、四个管理端点、`renderMd` + `.prose` 正文渲染、
排序与发布语义、弹窗表单全部复用；改动集中在「撤卡 + 搬页 + 加已读 + 加弹窗」。
v1 期间的一处实测裁决（title 空白返回 422 而非 spec 原写的 400）继续有效。
