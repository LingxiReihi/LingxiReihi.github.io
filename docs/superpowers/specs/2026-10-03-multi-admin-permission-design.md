# 多管理员与权限体系设计（personal-web 后端）

日期：2026-10-03　范围：后端 + 后台管理页　状态：待批准

## 1. 背景与目标

今天后台只有一个管理员账号（`users` 表，`backend/app/models/user.py:9-21`），没有 role/is_active/permissions 任何一列；唯一的鉴权依赖是 `get_current_admin`（`backend/app/core/deps.py:14-29`），它只回答"这是不是合法后台用户"，**全站没有任何一处校验内容归属**。`contents`、`media_assets`、`columns` 三张表都没有创建者列，所以"谁上传的"这件事在数据层根本不存在。

目标（用户原话拆成的可验收条件）：

1. 可以添加其他管理员用户（后台建号、停用、重置口令）。
2. 每个管理员只能管理**自己上传**的内容（内容、素材的写/改/删/状态变更按归属隔离）。
3. `admin` 为顶级管理员，可以管理其他管理员账号。
4. 顶级管理员可以给不同账号**不同权限**，粒度到"某一栏目的管理权"。

非目标（本轮明确不做）：多租户、前台按作者署名/作者页、SSO、审计日志页面、角色自定义（RBAC 三层表）、把权限缓存进 JWT。

## 2. 已定口径（2026-10-03 七题拍板）

| # | 岔路 | 定案 |
|---|---|---|
| 1 | 权限粒度 | **权限点 + 作用域**（`admin_grants` 一张表），不建角色表 |
| 2 | 对他人内容的可见性 | **可见不可改**（列表返回全站，逐条带 `can_edit`；写操作 403） |
| 3 | 栏目归属 | **全局共享 + 授权**（`columns` 不加 owner 列） |
| 4 | 交付范围 | **后端 + 后台管理页**（新 `AdminsView.vue`） |
| 5 | 评论审核 | **全站共享待审队列** —— 只校验 `comment:moderate` 权限点，**不校验归属**（归属隔离的唯一显式例外，见 §5） |
| 6 | `column_id=NULL` 的内容 | 持**全局** `content:write` 者可建/可改（仍受归属限制）；只有**栏目级**授权者必须把内容挂在自己被授权的栏目下，无栏目 403 |
| 7 | 素材隔离 | **归属隔离 + 引用保护**：只能删自己上传且未被引用的素材；素材对所有人可见可复用（跨人复用不阻断） |

## 3. 数据模型

### 3.1 `users` 加 4 列

```
role        String(16)  default 'staff'   -- 'super' | 'staff'
is_active   Bool        default True
created_by_id  Int     FK users.id, nullable   -- 谁建的号（审计）
note        String(128) default ''
```

- seed 出的 `admin`（`services/auth.py:68 ensure_admin`）为 `super`；后台新建的账号一律 `staff`。
- `is_active=False` → `get_current_admin` 抛 401「账号已停用」。不物理删除，历史内容归属保留。
- 复用已有 `failed_attempts/locked_until`（登录防爆破对所有账号一视同仁）与 `token_version`（改密/重置即全端下线，`core/security.py:22-29`）。

### 3.2 新表 `admin_grants`

```
id           Integer PK
user_id      Int  FK users.id  ON DELETE CASCADE, index
permission   String(32)   -- 必须在白名单内，否则 400
scope_type   String(16)   -- 'global' | 'column'
scope_id     Int nullable -- scope_type='column' 时为 columns.id
granted_by   Int FK users.id nullable
created_at   TZDateTime
UNIQUE(user_id, permission, scope_type, scope_id)
```

模型文件 `backend/app/models/grant.py`，在 `models/__init__.py` 导出 `AdminGrant`。`scope_id` 不做 FK（栏目可被删；删栏目时一并清理该栏目的 grant，见 §6.3）。

### 3.3 权限点白名单

新文件 `backend/app/core/permissions.py`：

```python
PERMISSIONS = {
  "content:write", "content:delete",          # 内容写/删
  "comment:moderate",                          # 评论审核（全站队列）
  "media:write", "media:delete",               # 素材上传/删除
  "column:manage", "tag:manage",               # 栏目、标签维护
  "setting:manage",                            # 站点设置
  "stats:view", "log:view",                    # 数据看板、日志
  "admin:manage",                              # 管理员账号管理（= 顶级能力，可单独下放）
}
SCOPED_PERMISSIONS = {"content:write", "content:delete", "column:manage"}  # 允许 scope_type='column'
```

super 隐式拥有全部权限点，**不落库**（`admin_grants` 里查不到 super 的记录，判定走 `is_super` 短路），因此不存在"给 admin 勾权限"这件事。

其余权限点只接受 `scope_type='global'`（传 column 报 400），避免"评论审核按栏目"这类没人要的维度。

### 3.4 归属列

```
contents.created_by_id      Int FK users.id nullable, index
media_assets.uploaded_by_id Int FK users.id nullable, index
comments.reviewed_by_id     Int FK users.id nullable   -- 审核留痕
```

`columns` / `tags` / `site_settings` 不加 owner（§2 第 3 题）。

## 4. 鉴权层

### 4.1 `AdminContext`

`backend/app/core/deps.py` 新增：

```python
@dataclass
class AdminContext:
    user: User
    is_super: bool
    grants: frozenset[tuple[str, str, int | None]]   # (permission, scope_type, scope_id)

    def can(self, perm: str, *, column_id: int | None = None) -> bool: ...
    def can_edit_content(self, c: Content) -> bool: ...
    def deny(self, perm: str, *, column_id: int | None = None) -> None:      # 不通过就抛 403
    def deny_content(self, c: Content, *, need_delete: bool = False) -> None

async def get_admin_ctx(request, db=Depends(get_db)) -> AdminContext
```

`get_admin_ctx` = `get_current_admin`（含 `is_active` 检查）+ 一次 `admin_grants` 查询。**权限每请求实时读库，不进 JWT** —— 撤权、停用、改 role 立即生效，无需等 token 过期。

⚠ **停用要封两条通道**（实现期补）：access（`get_current_admin`）与 refresh（`services/auth.refresh_tokens`）都得查 `is_active`。只封 access 时，被停用者仍能用 refresh token 不断换发新 access token —— 每次请求确实会被拒（不构成越权），但「停用即时生效」这句话就名不副实。另外 `is_active` 判定必须排在 `token_version` 之前：停用本身会 bump `token_version`，否则用户只看到含糊的「登录已失效，请重新登录」，不知道自己是被人停用了。

`can(perm, column_id=...)` 的两条语义（消歧）：
- 传 `column_id=None` → 只认 `scope_type='global'` 的 grant（§2 第 6 题：无栏目内容需全局权）。
- 传 `column_id=X` → global grant 命中即放行；否则要求存在 `('column', X)` 的 grant。**global 覆盖一切栏目**，不必重复勾。

**零权限账号的默认行为**：新建 staff 若一条 grant 都没授，则**只读后台** —— 可登录、可看列表与详情，任何写操作 403。不做"默认给自己上传的内容放行"这种隐式口子，否则"权限点"形同虚设。

判定内核（归属 AND 作用域，两条都要过）：

- `is_super` → 一切放行。
- 内容写/改/删/状态：`c.created_by_id == user.id` **且** `can('content:write', column_id=c.column_id)`（删除另需 `content:delete`）。
- 归属不满足 → 403「该内容由 {创建者昵称} 创建，你只能管理自己上传的内容」；作用域不满足 → 403「你没有栏目「{名称}」的管理权」。两种文案分开，便于用户自查配置。
- 读接口（`GET /contents/{id}`、详情、看板）对 staff **一律放行**（§2 第 2 题：可见不可改）。

### 4.2 路由改造清单

把 `_: User = Depends(get_current_admin)` 换 `ctx: AdminContext = Depends(get_admin_ctx)`，写操作前插一行 `ctx.deny(...)` / `ctx.deny_content(obj)`：

| 文件 | 端点 | 需要的权限 |
|---|---|---|
| `api/admin/contents.py` | POST `` / PUT `/{id}` / PATCH `/{id}/status` / POST `/column-bulk` | `content:write` + 归属 + 作用域 |
| 同上 | DELETE `/{id}` | `content:delete` + 归属 |
| 同上 | POST `/{id}/reset-likes` | `content:write` + 归属（改 likes 是内容写操作） |
| 同上 | GET ``、GET `/{id}`、GET `/{id}/dashboard`、POST `/{id}/preview-token` | 读，放行（`/dashboard` 顺带回报 `can_edit`） |
| `api/admin/media.py` | POST `` 上传（写 `uploaded_by_id`）；POST `/categorize` | 两者均需 `media:write`；**归类另需归属**（首轮实现漏了：归类会移动磁盘文件并重写引用它的正文 URL，属写操作；现只处理自己上传的 id，其余进新增的 `denied` 回报） |
| 同上 | DELETE `/{asset_id}` | `media:delete` + 归属 + 沿用 `assert_deletable` 引用检查 |
| 同上 | GET `` | 全放行，逐条带 `can_delete`、`uploader_nickname` |
| `api/admin/comments.py` | POST `/moderate`、DELETE `/{id}` | `comment:moderate`（**不校验归属**，§2 第 5 题）；`moderate` 写 `reviewed_by_id=user.id` |
| `api/admin/site.py` | tags 写 3 个 | `tag:manage` |
| 同上 | columns 写 3 个 | `column:manage`（global 或该栏目）；`list_columns` 逐条带 `can_manage` |
| 同上 | `PUT /settings/{group}` | `setting:manage` |
| `api/admin/logs.py` | 全部 4 个 | `log:view` |
| `api/admin/seo_stats.py` | `stats/*` 读 | `stats:view` |
| 同上 | `seo/*` 写（manual-push、trigger） | **仅 `is_super`**（实现期收紧：原写「admin:manage」会让被下放账号也能触发全站百度推送与重建，站点级动作不下放） |
| 新增 `api/admin/admins.py` | 全部 | `admin:manage` |

列表接口新增能力：`GET /contents?mine=1`、`GET /media?mine=1`，每条响应加 `owner_id / owner_nickname / can_edit / can_delete / denied_reason`（`_asset_admin_dict` 增参实现，`contents.py:53-65`）。

### 4.3 新路由 `api/admin/admins.py`

挂载在 `main.py:41-52` 的 `{api}/admin` 下，prefix `/admins`：

| 端点 | 语义与校验 |
|---|---|
| `GET /admins` | 列表：id、username、nickname、role、is_active、last_login_at、note、内容数、grants |
| `POST /admins` | 建号：username（唯一，重复 409）+ password（≥10 位且含字母与数字，否则 422）+ nickname + grants（可空，一次给全） |
| `PUT /admins/{id}` | 改 nickname / note / is_active / role（super ↔ staff） |
| `PUT /admins/{id}/grants` | **覆盖式**设权限：传完整集合，服务端算增删；前端勾完整表提交，语义无歧义 |
| `POST /admins/{id}/reset-password` | 服务端生成一次性强口令返回，并 `token_version += 1` 强制下线 |

**不自建 `/admins/me/permissions`。** 已核实 `GET /admin/auth/me`（`api/admin_auth.py:52-54`）与登录响应里的 `user` 字段（同文件 `:33`）都输出 `schemas/auth.py UserOut`，前端 `stores/auth.ts:36-59 restore()` 每次进页都会打它 —— 权限集合**扩到这一个端点**上，登录、刷新页面、token 续期后都自动带回来，不需要第二个请求：

```
UserOut 增加：is_super: bool, permissions: list[str], scoped_column_ids: list[int], is_active: bool
```

⚠ 实现坑（已核实）：`UserOut.model_validate(user)` 是 ORM 直读，新增的 4 个字段**不是 User 的列**，必须改成显式构造函数（如 `user_out(user, grants)` 服务函数）在两处调用点替换，否则 pydantic 报缺字段或静默丢权限。撤权后靠"下一次请求实时读库"生效，但前端菜单要即时变化需重进 `/admin`（可接受，不做 WebSocket 推送）。

护栏（`services/admin_accounts.py` 承载，路由保持薄）：
- 不可停用 / 降级 / 删除**最后一个 super**。
- 不可对自己 `PUT is_active=false` 或改自己的 `role`。
- **授权链只向上收口**（实现期自查补上，否则「admin 给别人不同权限」这条会被架空）：① 任何人不能改**自己**的权限（403）—— 被下放 `admin:manage` 的人不能自助提权；② `admin:manage` 只能由 **super** 授出（403）—— 防账号管理权横向自我复制；③ 非 super 的授权者只能授出**自己已具备**的权限点（403 并列出越界项）。super 三条全不受限；前端授权面板同步把不可授出的行置灰并给原因。
- `DELETE /admins/{id}` 仅允许"从未上传过内容且未挂任何素材"的账号（存在归属数据 → 409，提示改用停用）。删除前把其 grant 一并级联。
- 所有账号变更写 `log_event("admin", ...)`（沿用 `core/logs.py`），actor 为操作者 username。

## 5. 例外与风险（显式记录）

- **评论审核不按归属**（§2 第 5 题）：拿到 `comment:moderate` 即可审全站待审评论，包括别人内容的评论。理由：待审队列是站点级卫生工作，按归属切会让 spam 落在无人可审的缝里。代价：某管理员可驳回/删除他人内容下他认为不当的评论 → 靠 `reviewed_by_id` 留痕，事后可查。
- **`column-bulk` 是跨归属变更向量**（`contents.py`）：改造后逐条判定，无权的 id 放进新的 `denied` 列表回报（与既有的类型不符 `skipped` 分开），不整批失败。**起点与终点都要过作用域** —— 首轮实现只查了内容当前所在栏目，导致「只有 A 栏目授权的人可以把自家内容批量搬进他没权限的 B 栏目」（单条 PUT 路径已拦，批量路径开了后门）；现已补上目标栏目的校验，两个方向都拦（搬出未授权栏目、搬进未授权栏目同样 denied）。
- **删栏目是跨归属写入（实现期自查补上的第三道门）**：`delete_column` 会把栏目下**所有**内容的 `column_id` 置空，只拿到「该栏目的 column:manage」的人因此能改写别人内容的归属。现规则：栏目内存在非本人（或无主）内容时，删除需**全局** `column:manage`，否则 403 并回报受影响条数；栏目清空后栏目级授权即可删。super 不受限。
- **标签的隐性旁路（实现期发现，接受）**：`_resolve_tags` 会在内容写作时按名字自动建标签（`contents.py:30-50`），所以只授 `content:write` 的 staff 能间接新增标签行 —— 但不碰重命名/删除，也不碰标签的栏目归属；`tag:manage` 只管显式的标签 CRUD。若日后要收紧，就改成"staff 只能引用已有标签"。
- **`admin:manage` 被下放后仍不是 super**：可建/管 staff、可设权限，但不能创建或提升 super 身份（`test_admin_manage_grantee_cannot_create_or_promote_super` 锁死），避免"下放一次账号管理权＝可自我提权到顶级"。
- **素材跨人复用**：`content_media` 是多对多，A 的封面可被 B 的内容引用。定案是"素材库共享、删除有引用保护"，所以 `uploaded_by_id` 只约束删除权，不约束引用权。
- **`site_settings` 与 SEO/重建是站点级**：`setting:manage` 与 `seo/*` 写操作默认只给 super，不给 staff 误改导航/域名的机会。
- **线上迁移不可逆**：`app.db` 是 SQLite，加列可回滚但回填值不可逆 → B4 上线前先 `cp app.db app.db.bak-multi-admin`。

## 6. 迁移与回填

单一新 revision，`backend/alembic/versions/<12hex>_multi_admin.py`，当前 head 为 `d9b3c5e7f0a2`（content_downloads）：

1. `op.batch_alter_table("users")` 加 4 列（`render_as_batch=True` 已在 `alembic/env.py:27,35` 配好，沿用 `f1c3d5e7a9b1` 给已填充 contents 加列的先例）。
2. `create_table("admin_grants")` + 唯一索引 + user_id 索引。
3. `batch_alter_table` 给 `contents` 加 `created_by_id`（+index）、`media_assets` 加 `uploaded_by_id`（+index）、`comments` 加 `reviewed_by_id`。
4. **回填**（upgrade 体内直接跑 SQL）：
   ```sql
   UPDATE contents     SET created_by_id = (SELECT id FROM users WHERE role='super' ORDER BY id LIMIT 1);
   UPDATE media_assets SET uploaded_by_id = (SELECT id FROM users WHERE role='super' ORDER BY id LIMIT 1);
   ```
   无 super 时子查询返回 NULL → 该行按"无主"处理。回填后线上现存数据全归 `admin`，super 绕过所有校验，**行为与今天逐端点一致 → 零回归**。
5. 无主（NULL）内容/素材：仅 super 可改可删，staff 一律 403（读得到）。
6. 删栏目时同事务清理悬空 grant：`site.py:172 delete_column` 现状是把内容 detach 成无栏目，改造后额外执行 `DELETE FROM admin_grants WHERE scope_type='column' AND scope_id=?`（`scope_id` 无 FK，不清理会留下指向已删栏目的死权限，被删栏目 id 若被 SQLite 复用（本机已知坑：无 AUTOINCREMENT 会复用最大 rowid）就会意外获得新栏目的管理权）。

本地跑法：`cd backend && .venv/Scripts/python.exe -m alembic upgrade head`（pytest 走 metadata 建表不跑迁移，必须手动执行一次才算数）。

## 7. 前端后台

已核实的现状约束（设计据此写，不是凭印象）：项目**没有** `router/index.ts`，router 由 `main.ts:15-22` 的 `ViteSSG` 创建；唯一的守卫在 `main.ts:39-45`（只判 `meta.requiresAuth` + `auth.isAuthed()`）；`meta.perm` 是全新概念；`AdminLayout.vue:27-37` 的 `menuItems` 是硬编码数组、零条件逻辑，且 activeKey 用 `route.name`（`:39-43`）→ **新路由 name 必须与菜单 key 一致**；`AdminUser` 类型只有 `{id, username, nickname}`（`api/types.ts:138-142`）；响应解包集中在 `http.ts:107-120` 的 `api()`，调用方从不碰 `{code,message,data}`；删除确认一律用 `NPopconfirm`（绝不 `window.confirm`，本机已知会冻住自动化）。

- `views/admin/AdminsView.vue`（新）：`NDataTable` + `h()` 渲染列（沿用 `ColumnsView.vue:132-162` 的写法）+ `NModal preset="card"` 新建弹窗 + 权限抽屉（按 §3.3 白名单勾选；栏目级权限按 `article/model/chat` 三组列出各自栏目多选）+ 停用/重置口令（一次性口令显示后要求复制，`dialog.warning()` 做二次确认）。外壳手写 `h1.text-2xl.font-bold` + `div.rounded-xl.border.border-line.bg-surface`，不引入新组件库或包装器（项目里没有 `PageHeader`/`useAdminTable`，自造会不一致）。
- `router/routes.ts`：children 增 `{ path: 'admins', name: 'admin-admins', meta: { perm: 'admin:manage' } }`（与 `:33-43` 现有兄弟项同级同风格）。
- **路由级权限补全（第一轮上线后追加）**：只守 `/admin/admins` 不够 —— 其余后台页靠菜单隐藏，staff 直接敲 URL 会落进满屏 403 的页面。现给每条后台路由挂上对应权限点：`tags→tag:manage`、`columns→column:manage`、`comments→comment:moderate`、`settings→setting:manage`、`logs→log:view`、`seo→stats:view`、`content/new` 与 `content/:id/edit`→`content:write`。`dashboard`/`content`(列表)/`media` **刻意不设门槛**：dashboard 是守卫的兜底跳转目标，若它也设权限，零权限账号登录后会撞进自我重定向；列表与素材按"可见不可改"保持可读。写入口同时按权限显隐（内容页「＋ 新建内容」与批量挂栏目栏、素材页「上传」与「归类」）。
- `main.ts` 守卫：现有 `beforeEach` 内追加一段 —— `to.matched.some(r => r.meta.perm)` 时要求 `auth.ready && (auth.isSuper || auth.perms.includes(perm))`，否则跳 `admin-dashboard` 并 `message` 提示。⚠ SSG 陷阱：本文件用 `ViteSSG`，构建期预渲染时 `localStorage` 不存在、`auth.restore()` 必然失败 → 权限判定必须只在客户端生效（守卫开头加 `if (import.meta.env.SSR) return true`），并先确认 `/admin/admins` 是否进 `vite-ssg` 的 includedRoutes 枚举（若进，SSR 阶段一律放行、hydrate 后再判）。
- `layouts/AdminLayout.vue`：`menuItems` 改为 `computed`，按 `auth.isSuper || auth.perms` 过滤（日志、SEO、设置、管理员入口对无对应权限者消失）。
- `stores/auth.ts` + `api/types.ts`：`AdminUser` 扩 `is_super / permissions / scoped_column_ids / is_active`；store 暴露 `isSuper`、`perms`、`can(perm, columnId?)`（与后端 `AdminContext.can` 同语义，前端只用于按钮态，不作安全边界）。
- `views/admin/ContentListView.vue`：新增「归属」列、「只看我的」开关（`mine=1`）；无权行的编辑/删除/状态按钮 `disabled` + tooltip 显示 `denied_reason`。
- `views/admin/ContentEditView.vue`：`can_edit=false` 时进只读态（隐藏保存与发布，顶部横幅「该内容由 X 创建，你只有查看权限」）。
- `api/index.ts`：新增 `export const adminAdminsApi = { list, create, update, setGrants, resetPassword }`，命名与 `adminColumnsApi`（`:114-121`）同构，URL 走 `/admin/admins...`（baseURL `/api/v1`）。

## 8. 测试

现有 46 例（`test_admin.py` 16、`test_auth.py` 8、`test_public.py` 10、`test_tags.py` 6、`test_comments.py` 4、`test_e2e_smoke.py` 2），`conftest.py:31-57` 的 `auth` fixture 以 `admin` 登录 —— admin 回填为 super 后绕过所有校验，**预期不需改动即全绿**；若有用例挂了，说明改造侵犯了 super 的既有行为，按 bug 处理而不是改测试。

新增：
- `conftest.py`：`staff1_auth` / `staff2_auth` / `grant_client` fixture（真走 `POST /admins` 建两个 staff 并授不同权限，不直连库）。
- `tests/test_admins.py`（27 例）：建号成功/用户名 409/弱口令 422/grants 覆盖式更新/停用后旧 token 立即 401/撤权即时生效/最后一个 super 不可停用/不可自停用/有内容的账号不可删除/`/admin/auth/me` 权限字段正确（super 全量、staff 按 grant、撤权后再读少一项）/staff 调 `/admins` 403/重置口令后旧会话失效。
- `tests/test_ownership.py`（24 例）：A 改 B 内容 403 且文案区分归属与作用域、B 读 A 内容 200 且 `can_edit=false`、mine=1 只见自己、未授权栏目写入 403、授权该栏目后放行、无栏目内容需全局权、`column-bulk` 跳过无权项、删除需 `content:delete`、素材归属与引用保护、`reviewed_by_id` 留痕、回填的无主内容仅 super 可改、`setting:manage` 与 `log:view` 缺失时 403。

## 9. 批次与退出门

| 批次 | 做什么 | 退出门（可判定） | 提交点 |
|---|---|---|---|
| **B1 权限层** | `users` 4 列 + `admin_grants` + 3 张归属列 + `permissions.py` + `deps.AdminContext` + `admins.py` 路由与服务 + `test_admins.py` | `alembic upgrade head` 本地跑通；`pytest -q` 全绿（46 旧 + 新）；`GET /admins/me/permissions` curl 200 | 1 commit |
| **B2 归属改造** | 六个既有路由全部接 `ctx`；列表加 `can_edit`/`mine`；`column-bulk` 逐条判定；`reviewed_by_id`；`test_ownership.py` | staff1/staff2 交叉用例全绿；以 admin 跑一遍 16 个 `test_admin.py` 行为不变；`test_ownership.py` 全绿 | 1 commit |
| **B3 前端后台** | `AdminsView.vue` + 路由守卫 + 菜单显隐 + 列表归属列/灰按钮 + 编辑只读态 | 本地 `http://localhost:5174` 实测链路：super 建 staff → 退出 → 用 staff 登录 → 只见自己可改、他人灰掉带 tooltip、无权菜单消失 → 截图或 DOM 读数为证；`vue-tsc -b` 无错 | 1 commit |
| **B4 上线闭环** | push → 服务器 `git pull` → **备份 app.db** → `alembic upgrade head` → `rebuild-frontend.sh` → `readlink dist` 确认切换 → 线上 curl 验证 | 线上 `/api/v1/admin/admins/me/permissions` 200、旧 admin 登录与内容列表行为不变、`contents.created_by_id` 全部回填非 NULL | 1 commit（+ 部署记录） |

B4 规避：避开服务器 4 点整点 cron 窗口（详见 `personal-web-deploy-verify-loop`）。

## 10. 文档同步（交付项，漏了就是不完整）

- `docs/api-reference.md`：新增「管理员账号」端点段（6 个）、权限点白名单表、以及 `GET /contents` / `GET /media` / `GET /columns` 响应新增字段（`owner_nickname` / `can_edit` / `can_delete` / `denied_reason` / `mine` 参数）；`/admin/auth/me` 响应示例更新。
- `docs/backend-architecture.md`：加一节「权限层」—— `AdminContext` 判定内核（归属 AND 作用域）、`admin_grants` 表结构、super 短路、评论审核例外。
- 两处文档与代码同一批提交（B1 提交流水线内），不另开任务。

- **只读态的边界（B3 实测发现）**：`ContentEditView` 的只读态按批准口径只做到「隐藏保存/发布/设置 + 顶部横幅 + save() 前置拒绝」，正文输入框与 3D 素材工作台的操作按钮**仍可点击**（点了不会丢数据：本地不保存，任何写请求都被服务端 403 拦下，且 save 守卫会提示）。若要连输入控件一并禁用，需要给编辑页十余处控件加 `:disabled="readOnly"`，属额外工作，等用户点头再做。
- **登录侧的停用拦截**：`services/auth.login` 在密码正确后仍检查 `is_active`，返回 `40100 账号已停用`（不是 BAD_CREDENTIALS）。取舍：持有正确口令的人本就知道账号存在，泄露面可忽略；换来的是"被停用的账号看得见原因"。

## 11. 待答（不阻塞 B1）

- 是否需要给 staff 一个「内容转移所有权」入口（离职管理员的内容改归他人）？本轮**不做**（会引入批量写他人内容的口子），先靠回填 + 停用。
