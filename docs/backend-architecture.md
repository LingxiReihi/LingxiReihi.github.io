# 后端架构设计文档

> 项目：personal-web 个人博客站 ｜ 版本：v1.1 ｜ 日期：2026-09-22
> v1.1 变更：新增 **百度推送与发布流水线子系统**（§10）；留言 feedback 暂缓；部署基线改为香港服务器（无 ICP）。
> 配套文档：[前端页面设计文档](./frontend-design.md) · [接口文档](./api-reference.md)

---

## 1. 概述与目标

FastAPI 后端为个人博客提供：**公开内容读取 API**、**管理员内容管理 API**（上传文章/模型/杂谈、站点设置）、**媒体文件服务**、**轻量访问统计**。单管理员场景，不做多租户。

非目标：不做评论、不做留言（feedback v1.1 暂缓，About 仅社交链接）、不做全文检索引擎（SQLite FTS / LIKE 足够）。**邮件自 v1.4 起不再是非目标**，但也不是自建：发信一律复用同一台服务器上 personal-mail 容器的外部发信接口（见 §5.2），后端不装 MTA、不开 25/465/587。

## 2. 技术栈

| 组件 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 异步、自动 OpenAPI（即接口文档的机器可读版） |
| ORM | SQLAlchemy 2.0（async）+ Alembic | 类型友好、迁移可版本化 |
| 数据库 | **SQLite（WAL 模式）** 起步 | 单写者博客足够；模型统一，随时可切 PostgreSQL（URL 配置化） |
| 校验/序列化 | Pydantic v2（pydantic-settings 读 `.env`） | |
| 鉴权 | **PyJWT（HS256）+ bcrypt 直用**（v1.1 实现决策：passlib 停维且与 Py3.14/bcrypt≥4.1 冲突，python-jose 维护弱，见 docs/adr） | access + refresh 双 token |
| 图片处理 | Pillow（缩略图、webp 转换、尺寸探测） | |
| 定时任务 | asyncio 后台任务（日聚合）；如需 cron 再引 APScheduler | 减少依赖 |
| 出站 HTTP | httpx（百度推送、触发重建回调） | async |
| 部署 | Docker + Caddy/nginx（静态前端 + 反代 `/api`、`/media`）；**香港服务器，无 ICP** | |

Python ≥ 3.12；现有 `.venv` 已含 fastapi/uvicorn，需补：`sqlalchemy[asyncio] aiosqlite alembic pydantic-settings PyJWT bcrypt pillow python-multipart httpx structlog pytest pytest-asyncio`（requirements.txt 已固化）。

## 3. 分层架构

```
backend/app/
├── main.py               # 应用工厂：挂载路由/中间件/静态目录/启动事件
├── core/
│   ├── config.py         # Settings（env: DATABASE_URL, JWT_SECRET, MEDIA_ROOT, CORS, MAIL_API_*…）
│   ├── crypto.py         # 配置密钥静态加密：HKDF(jwt_secret) → Fernet（邮件 API Key 密文入库）
│   ├── security.py       # bcrypt 哈希、JWT 签发/校验
│   └── deps.py           # Depends：get_db, get_current_admin, get_optional_pagination
├── models/               # SQLAlchemy ORM（表定义）
├── schemas/              # Pydantic（请求/响应 DTO，public / admin 两组）
├── services/             # 业务逻辑：content, media, stats, settings, auth, admin_accounts,
│                         #   profiles, seo_push, rebuild, sitemap, mail_sender, password_reset,
│                         #   comment_notify
├── repositories/         # 数据访问薄层（查询封装，可被 service 直接替代，5.x 项目允许省略）
├── api/
│   ├── public.py         # /api/v1/*       免鉴权 + 统计埋点
│   └── admin.py          # /api/v1/admin/* JWT 鉴权
├── middleware/
│   ├── access_track.py   # PV/UV 采集（见 §6）
│   └── error.py          # 统一异常 → 响应包
└── tasks/
    └── aggregate.py      # 每日 00:30 将 view_events 聚合进 stats_daily / stats_content
```

依赖方向：`api → services → models`，禁止反向；router 不写业务逻辑，只做参数解析与 DTO 转换。

## 4. 数据模型

```
users 1─n (无，单管理员)          site_settings (key-value)
contents n─n tags                 media_assets
   │ 1─n content_media ──────────┘
   │ 1─n content_views(事件)  →  stats_daily / stats_content(聚合)
   └─ feedback (留言，独立表)
```

### 4.1 表定义

**users**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| username | str unique | 登录名 |
| password_hash | str | bcrypt |
| nickname / avatar_url | str | 展示用的昵称与头像，v1.4 起就是账号自己的资料（不再是 settings.profile） |
| signature / bio_md / social_links / skills / experience | str / text / JSON | **v1.4 资料跟人走**：每位管理员自己那份，`GET/PUT /admin/profile` 读写（七项资料本人全能改，越界靠「只能改自己」这条边界守）；昵称空则回落 `username`。About 主体与首页读 super 那份，其余人渲染进 About 的自己那张卡片；首页/关于页/详情署名都从账号行读（`site_settings.profile` 组废弃，值由迁移 `a8c1e4f7b205` 一次性搬进 super 行） |
| show_in_about（已作废） | — | 同日先加后废：About 名单最终口径是「凡在职管理员都露出」（`is_active` 且非 super，停用即下架），不需要逐账号开关。加列迁移 `c7d3b9e0a412`、前滚删列迁移 `d1f4a6c8b307`（该列从未上线，但按链只增不减处理）。名单每人下发完整资料卡（`nickname/avatar/signature/bio_md/social_links/skills/experience`），身份类字段仍不出网 |
| failed_attempts / locked_until | int / datetime | 登录防爆破 |
| last_login_at | datetime | |

**contents**（三类内容统一模型，前端 Flow F 一套编辑器复用）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| type | enum(`article`,`model`,`chat`) | |
| status | enum(`draft`,`published`,`archived`) | 仅 published 对外可见 |
| title | str | |
| slug | str unique(article/model; chat 用 id) | URL 友好 |
| summary | str | 卡片摘要 |
| body_md | text | 正文 Markdown（原文存储，前端渲染） |
| cover_asset_id | FK media_assets NULL | 封面 |
| media_kind | str NULL | 模型子类：`3d`/`render`/`animation` |
| extra | JSON | 弹性字段：model→{faces, materials, software, duration, formats, links[], asset_refs}；article→{reading_time, related[] 可选} |
| published_at / created_at / updated_at | datetime | 排序与 RSS 依据 |
| view_count | int | 冗余计数（来自聚合任务，详情页展示用） |

索引：`(type, status, published_at desc)`、`slug unique`。

**tags**：`id, name unique, slug unique`；**content_tags**：联合主键多对多。

**media_assets**：`id, filename, storage_key(相对路径), kind(image|model3d|video|file), mime, size, width, height, sha256(秒传/去重), uploaded_at`。

**site_settings**：`key PK(group.field), value JSON, updated_at`。分组：`site / home / nav / footer`（`profile` 组在 v1.4 废弃，资料改存 users，见 §4.1）。公开组随 `/site-config` 下发。

**view_events**（原始事件，30 天后清理）：`id, day(YYYYMMDD int), path, content_id NULL, referrer, ip_hash, ua_hash, status_code, created_at`。

**stats_daily**：`day PK, pv, uv`；**stats_content**：`(day, content_id) PK, pv, uv`。

**feedback**：`id, name, email, message, created_at, handled bool`。**v1.1 暂缓**（About 页仅社交链接，不开放留言；表结构保留不实现端点）。

**announcements**（更新公告，2026-10-14 新增，迁移 `c9e2f4a7b108`）：`id, title String(200) 必填, body_md Text(Markdown 正文，默认空), status(draft|published，默认 published), published_at nullable(首次置 published 且从无发布时间时补写，改回 draft 不清空、重发布不覆盖首发), created_at/updated_at, created_by_id FK users SET NULL(索引，同 contents 归属口径)`。**v2 形态**（同日改口径，见 §5.1）：消费方是管理页 `/admin/announcements`（增删改，需 `announcement:manage`）与全员登录弹窗（`/unread` 只推 `status=published`——草稿是作者自己没写完的备忘，不弹给别人）。**status/published_at 为前台预留，本期无公开端点**（前台无消费者，故发布也不接 trigger_rebuild/sitemap）。

**announcement_reads**（逐条已读水位，v2 同日新增，迁移 `d3a9c5e7b412`，依赖 `c9e2f4a7b108`）：`(announcement_id, user_id)` **复合主键** = 天然去重（`POST /read` 重复上报幂等、不多写行）；两侧 FK 均 **ON DELETE CASCADE**（删公告连带清它的已读行、删用户同理，所以「未读」永不需要脏数据兜底）；`read_at` 记标已读时刻。「未读」= `announcements` 中不存在 `(该公告 id, 当前 user)` 已读行的集合；本期不做已读可视化端点（无人消费）。

### 4.2 种子数据

启动迁移后由 CLI（`python -m app.cli seed`）创建唯一管理员（用户名/密码来自 env 首启生成）与默认 settings。v1.4 起 `ADMIN_NICKNAME` 落进该账号的 `nickname` 列（About/首页读它），不再写 `site_settings.profile.*`。

## 5. 鉴权与安全

- **JWT 双 token**：access 2h（内存/localStorage 由前端定），refresh 7d（仅 `/admin/auth/refresh` 换新）；payload 含 `sub=user_id, role=admin, exp`。
- 密码 bcrypt(cost≥12)；登录失败统一「账号或密码错误」，不暴露账号是否存在。
- **防爆破**：同账号连续 5 次失败 → 锁定 10 min（`locked_until`），返回 423。**按 IP 的全局限速至今没有实现**（此前文档写的"中间件层 10 req/min/IP"是设想，不是代码）：线上 Caddy 反代后 `request.client.host` 恒为代理 IP，要按真实来源计数得先补 `ProxyHeadersMiddleware` 并限定可信代理段 —— 这是已知缺口，涉及公开端点时（如 §5.2 的忘记密码）改用"按账号 + 全站"计数顶住。
- 公开 API 只读且只回 `status=published` 字段白名单 DTO；`draft` 预览通过带签名的 preview token（`?token=`，服务端校验管理员签发的短期 JWT）。
- CORS：生产仅允许前端域名；dev 放行 localhost。
- 上传安全：白名单 MIME + 扩展名 + 大小上限（图 5MB / glb 50MB / 视频 200MB）；文件名 uuid 重命名，存 `MEDIA_ROOT`（`data/media/YYYY/MM/`），**绝不用用户原名**；静态目录禁目录列举、`Content-Disposition` 下载 glb 等非常规类型。
- SQL 注入/XSS：全 ORM 参数化；MD 正文前端渲染，后端不做可信 HTML 拼接；RSS 输出转义。
- 密钥仅 env（`.env` gitignore）；日志不记录 token 与 IP 明文（只存哈希）。

### 5.1 多管理员与权限层（v1.4 新增）

- **两级身份**：`users.role` = `super`（顶级，隐式拥有全部权限点、授权表里查不到它的行）| `staff`（靠 `admin_grants` 表逐条授权）。`users.is_active=false` 时 `get_current_admin` 直接 401，且 `login` 拒绝签发 token。
- **权限点 + 作用域**：`admin_grants(user_id, permission, scope_type∈{global,column}, scope_id)`，唯一约束 `(user_id, permission, scope_type, scope_id)`；权限点白名单集中在 `app/core/permissions.py`，白名单外的字符串一律 400，避免拼写漂移出"没人能解释的权限"。仅 `content:write/content:delete/column:manage` 支持栏目作用域，global 覆盖任意栏目。2026-10-14 新增权限点 `announcement:manage`（更新公告）：**仅全局**（不进 `SCOPED_PERMISSIONS`）。v2 同日改口径，语义 = **可写公告**：`GET/POST/PUT/DELETE /admin/announcements*` 四个管理端点（含管理页列表 GET）首行判它；而登录弹窗的读侧 `GET /unread`、`POST /read` 只依赖 `get_current_admin`、**不判权限点 —— 读全员开放**。（v1 曾读写同权限钉在一起，用户换 staff 账号实测发现其他管理员看不到公告，同日反转，见设计文档 §9。）
- **判定内核**（`core/deps.py` 的 `AdminContext.can(perm, column_id=)`）：内容写改删要**同时**过两道门 —— 归属（`contents.created_by_id == 当前用户`，他人内容永远 403，无例外口子）AND 作用域（有 `content:write` 命中 global 或该内容所在栏目）。读接口对 staff 全放行（"可见不可改"），列表逐条回报 `can_edit/can_delete/denied_reason`。
- **例外**：评论审核（`comment:moderate`）是全站共享待审队列，**不按归属过滤**，仅写 `comments.reviewed_by_id` 留痕；`site_settings` 与 SEO/重建等站点级动作默认只归 super。
- **实时生效**：权限每次请求实时读库、不进 JWT —— 撤权/停用/降级下一次请求即生效，无需等 token 过期；改密与重置口令走 `token_version += 1` 全端下线。
- **跨归属的「管理动作」是三类，不是一类**（实现期自查补齐，别再只看同名动词的端点）：`/admin/media/categorize`（移动磁盘文件 + 重写正文引用的 URL）、`column-bulk`（批量挂栏目，起点与终点都要过栏目作用域）、`delete_column`（把栏目下**所有人**内容的 `column_id` 置空，故栏目级 `column:manage` 不够，需全局）。凡「看起来像管理动作而非编辑动作」的接口，都要问一句它改了谁的行。
- **授权链只向上收口**：不能改自己的权限；`admin:manage` 仅 super 可授；非 super 只能授出自己已具备的权限点（`services/admin_accounts.py::_validate_grants_by_actor`，前端 `canOffer` 同步置灰）。否则「admin 给别人不同权限」这句话会被下放者自我复制架空。
- **护栏优先级**（`services/admin_accounts.py`）：最后一个可用 super 被停用/降级/删除 → 409；停用或降级自己、非 super 触碰 super 身份 → 403；名下有内容或素材的账号不可删除 → 409（引导停用）。
- **回填不变式**：迁移 `e7a1c9b3d5f2` 把最早创建的账号（seed 出的站点主账号）设为 super，并把全部现存 `contents/media_assets` 归属回填给它 → 顶级管理员绕过校验，线上行为与改造前逐端点一致。`created_by_id IS NULL` 视为"无主"，仅 super 可改。
- **悬空授权清理**：`scope_id` 不做外键，删栏目时必须同事务 `DELETE FROM admin_grants WHERE scope_type='column' AND scope_id=?`；SQLite 无 AUTOINCREMENT 会复用最大 rowid，残留死授权会让他人意外取得新栏目的管理权。

### 5.2 忘记密码与邮件通道（v1.4 追加）

三个新件，各管一件事，别互相伸头：

- **`services/mail_sender.py` —— 只懂"发一封信"**。对端是同容器网络的 personal-mail：`POST http://mail:8000/api/external/send`（线上）或公网 `https://mail.lingxi-reihi.cn/api/external/send`（本地开发容器网络外，用它），`Authorization: Bearer <key>`，body 只有 `to/subject/body_text`（带 `draft_id` 会被对端 400；From 恒为发信账号，不可指定）。出站写法照 `seo_push.py` 的 `httpx.AsyncClient(timeout=15)`，另加 `trust_env=False` 免得本机代理劫持内网调用。**任何失败（非 2xx、`ok:false`、超时、连不上）一律抛 `MailError`，绝不静默** —— 上层就靠这一条保证"发不出去就不改口令"。对端错误码表在 `mail_sender._REASON` 里翻译成人话。
- **`services/password_reset.py` —— 只懂"一次自助重置该不该发生"**。写库→发信→**成功才 `commit`，`MailError` 则整笔 `rollback`**；口令写入本身复用 `admin_accounts.apply_reset()`（与顶级管理员代重置同一个函数，含 `token_version+=1` 强制下线与清锁定计数，所以被锁住的账号能靠它自己回来）。限流是进程内两份状态（同账号 60s 冷却 / 同账号每小时 3 封 / 全站每小时 20 封，最后一档是为保住发信邮箱不被 QQ 风控），窗口清理放在**所有提前返回之前**，冷却表只保留窗口内条目。**响应侧只有一个口径**：`UNIFORM_MESSAGE` 那一句话（放 `data`，措辞服务端唯一持有），账号不存在 / 已停用 / 未填邮箱 / 被冷却 / 发信失败全部同一句，因为"有没有报错"本身就是可枚举信号；真实原因只进 `app.log`。唯一例外是通道整体不可用 → `50300`，且这一步在查库之前完成，与任何账号无关。
- **`core/crypto.py` —— 只懂"配置里的密钥不能裸存"**。`mail.api_key` 在 `site_settings` 里存 Fernet 密文，主密钥由 `HKDF-SHA256(jwt_secret)` 派生，**不新增 env 项**：能读库（含每次上线前的 `app.db` 备份）但读不到 `.env` 的人拿不到凭据；`jwt_secret` 一变旧密文就解不开，此时读接口报 `api_key_set=false`、发信按"未配置"处理，**绝不会把乱码当凭据发出去**。派生密钥这件事是用户拍板"要在设置页填 token"+"不接受明文入库"两个要求叠出来的唯一解。

`mail` 设置组的读写语义（`services/settings.py`）：`api_key` **只写不回显**，`GET /admin/settings` 换成 `api_key_set` + 明文尾 4 位；`PUT` 时**留空 = 保留原值**（否则界面带着掩码保存一次就把凭据洗没了），派生键在写入路径剔除。发信凭据从站点设置取，`.env` 的 `MAIL_API_*` 只作兜底。

**邮件通道的出口只有一个：`services/mail_queue.py`**（v1.4 追加，设计见 `docs/superpowers/specs/2026-10-06-mail-queue-design.md`）。额度、退避、重试全部**从 `mail_queue` 表推导**，没有独立计数器 —— 因为「超额攒到下一小时发」是跨重启的承诺，内存计数一清零就变成静默丢信。状态只有 `pending/sent/dropped`，等待重试仍是 `pending`（不设 `failed`，免得出现"failed 但其实还会再发"的两处真相）。

三个调用方，语义按「邮件是不是交付手段」分档：

- `services/password_reset.py`（忘记密码）：**发不出去就不改口令** —— 写库不 commit，发信成功才落盘，失败整笔回滚；而且它**不入队**（明文口令不能在库里躺到下一小时），只在成功发出后写一条 `body_text` 为空的台账行来占同一份额度，额度满就明确 `50300` 不排队。因为邮件本身就是交付手段，没送到等于没发生。
- `services/comment_notify.py`（作者通知 + 评论者通知）：**评论/审核已经落库，通知失败不回滚也不报错**，只记 warning。作者信收件人 = 内容归属账号，无邮箱/停用则回落 super，两边都没有就跳过；评论者信的去重靠 `comments.notified_at` 持久列（入队与写列同一笔事务），所以「通过→拒绝→再通过」只发一封。访客输入只进正文，绝不进 To/From。
- `services/announcement_notify.py`（公告首次发布通知，2026-10-14 追加）：与上一档同语义（公告已 commit，通知是旁路），但**收件人是全体**：`is_active` 且填了邮箱的**每一个**管理员各一封（含操作者本人，与 About 名单同口径），`kind="announcement"`。触发点只有**首次发布**——新建即 published，或草稿转发布；编辑已发布公告不重发。去重**靠状态转换**，不给 `mail_queue` 加公告外键列（代价：改回草稿再发布算一次新发布，会再发一封）。入口 `notify_published(announcement_id)` 由端点挂 `BackgroundTasks` 调用：自开 session、整段吞异常，所以保存请求既不等 SMTP 也不会被通知失败带回 500。
- 冲刷：入队后顺带 `drain`（在 `BackgroundTasks` 里，所以管理员与访客都不等 SMTP 往返），另有 CLI `mail-drain` + 每小时 cron 兜底。
- 额度 30 封/小时全站共用（用户先要 60，接受"60/h=1440/天、个人 QQ 邮箱风控阈值未知"的反对意见后下调），外加连续失败退避 30 分钟。

## 6. 访问统计子系统

- **中间件采集**：仅对公开页面 API（`/api/v1/posts/{slug}`、`/models/{slug}`、`/chats`、`/home`… 的 GET 2xx/404）记 `view_events`；UV 指纹 `sha256(ip+UA+day+SECRET)`，天然按天去重。静态资源与 `/admin` 不采集；爬虫按 UA 正则剔除。
- **来源归属**：`view_events.referrer` 优先取前端上报的 `X-Page-Referrer`（即落地页的 `document.referrer`；SPA 内 pushState 不改它，所以一次访问的后续请求都保留最初来源），头缺失或不是绝对 http(s) URL 时回落到 HTTP `referer`。必须靠前端上报的原因：搜索/社交来源只存在于首次 HTML 文档请求上，而那份请求由 Caddy 直出 dist、根本不经后端，后端能看到的同源 XHR 其 `referer` 恒等于本站页面自己的 URL，全都会被 `classify_referrer` 判成 `direct`。
- **日聚合任务**：启动时 `asyncio.create_task` 循环，每日 00:30 汇总昨日 `view_events` → `stats_daily` / `stats_content`，并回填 `contents.view_count`，清理 30 天前原始事件。
- 备选增强（不在 v1）：前端 `navigator.sendBeacon` 补采 SPA 路由级 PV（`POST /track` 已预留）。
- 局限声明：无 JS 采集的 PV ≠ 真实页面浏览（按详情 API 调用近似），对个人站足够。

## 7. 横切约定

- **统一响应包**：`{"code": 0, "message": "ok", "data": ...}`；错误 `code ≠ 0`（详见接口文档 §2）。HTTP 状态码与业务 code 并用。
- 分页约定：page-based（公开列表/后台表格）+ cursor-based（杂谈流）；响应含 `total, page, page_size, items`。
- 时间一律 UTC ISO8601 存储，前端本地化展示。
- 路由版本前缀 `/api/v1`；OpenAPI JSON 在 `/api/docs`（生产可关闭 docs UI 仅留 JSON）。
- 错误处理中间件捕获 `AppException(code, http, message)` / RequestValidationError / 未捕获 500，全转响应包。
- 日志：structlog 或 stdlib JSON formatter，级别 env 控制；慢查询（>200ms）warning。

## 8. 目录与部署

```
backend/
├── app/                # §3 结构
├── alembic/versions/   # 迁移
├── data/               # sqlite 文件 + media/（挂载卷）
├── tests/              # pytest + httpx.AsyncClient（public/admin/stats/media 四组）
├── .env.example
└── pyproject.toml
```

**Docker 部署**（compose）：
1. `backend`：uvicorn（1 worker + WAL 足够），卷 `./data:/app/data`，健康检查 `/api/v1/health`
2. `caddy`：托管前端 `dist/`（SPA fallback 到 index.html），反代 `/api` 与 `/media` → backend；`/sitemap.xml`、`/sitemap.txt`、`/robots.txt`、资源平台验证文件 → backend 直出；自动 HTTPS；gzip/缓存头（media 长缓存 `immutable`，html no-store）
3. 备份 = 定时拷贝 `data/`（sqlite3 .backup + 文件同步）；单机资源：**≥1GB 内存（前端本机重建需要，推荐 2GB）**，见 §10.3
4. 部署基线为**香港服务器**：百度可抓取但无备案权重加成；对百度链路需监控抓取成功率（见 §10.4）；同机需安装 **Node.js ≥ 20**（vite-ssg 重建用）

**测试策略**：service 层单测 + API 集成测试（登录→建草稿→发布→公开读取→统计落库全链路冒烟必须覆盖）。

## 9. 演进路线（明确不做于 v1）

评论系统、多作者角色、ElasticSearch 全文、对象存储(OSS/S3)媒体、Webhook 通知、i18n——均在数据模型上留有出口（extra JSON、settings 分组、storage_key 抽象），不做提前实现。留言（feedback）v1.1 起同样归入此类。

## 10. 百度推送与发布流水线子系统（v1.1 新增）

### 10.1 配置（env）

`BAIDU_PUSH_API`（资源平台「链接提交-主动推送」接口地址，含 token；**用户决策 v1.2：暂不配置**——缺省时流水线只重建不推送，`SEO_PUSH_ENABLED` 自动置 false，配置 token 后可在后台 SEO 面板批量补推历史 URL）、`BAIDU_SITE_URL`（https 规范域名）、`REBUILD_SCRIPT`（**服务器本机重建脚本路径**，v1.2 决策：不走 GitHub Actions，采用同机 subprocess 构建）、`SEO_PUSH_ENABLED`（联调期可关）。token 仅存 env，接口不回显明文（列表只回"已配置/未配置"）。

### 10.2 Sitemap 生成（`services/sitemap.py`）

- `GET /sitemap.xml`：published 的 post/model/chat 详情 + 五栏目页；`lastmod = updated_at`；`changefreq` 按类型（chat=daily，其余=weekly）
- `GET /sitemap.txt`：仅 URL 逐行（百度 sitemap 提交格式）
- 内存缓存 + 发布/下架事件失效重建（个人站量级无需落盘）

### 10.3 主动推送（`services/seo_push.py`）

- 单客户端封装：httpx POST 换行分隔 URL 体，解析百度返回 JSON（`success/rest/notice/error`），结果写 `push_logs` 表：`id, urls(json), result(json), triggered_by(manual|publish), created_at`
- 限额自律：≤ 日配额（默认 2000 条，读取响应 `remaining`），批量合并（同一次发布多 URL 一次请求）
- 触发时机（发布流水线顺序，防推送时页面 404；v1.2 定为**服务器本机重建**，实现于 `services/rebuild.py`）：
  1. `PATCH …/status → published` 成功
  2. 后端以 asyncio subprocess 启动 `REBUILD_SCRIPT`（`scripts/rebuild-frontend.sh`：vite-ssg build 输出到 `releases/<ts>` → `dist` 符号链接**原子切换**），任务落 `rebuild_jobs` 表（running/success/failed/skipped，含日志尾部）
  3. **文件锁保证同时只有一个构建**（新触发排队；`REBUILD_MERGE_SECONDS` 窗口内的多次发布合并为一次构建，默认 10s）；脚本退出码 0 → 若已配置百度 token 则对新 URL 调主动推送，未配置则记 `pending_push`；脚本未配置则 job=skipped、URL 入 pending_push
  4. 结果回写 `rebuild_jobs`/`push_logs`，后台经 `GET /admin/seo/jobs` 轮询展示（无外部回调端点）
- 重建失败或推送失败均**不回滚发布**；后台「SEO」面板提供手动重推与手动重建入口
- 兜底：资源平台同时提交 `sitemap.txt`，周期抓取与主动推送双通道
- **服务器要求（v1.2 连带变更）**：与站点同机需装 **Node.js ≥ 20**；vite-ssg 构建峰值内存约 1GB——机器规格从 512MB 上调为 **≥1GB（推荐 2GB）**；构建期间站点不受影响（旧 dist 仍在服务）

### 10.4 可观测

- 后台看板（Flow H）增加采集健康卡：近 7 日推送成功率、重建失败次数；百度侧核对以资源平台「抓取诊断/流量对接」数据为准（v1 不自动抓取诊断）
- 香港节点风险：跨境延迟致抓取超时 → 响应头 `Server-Timing` 与访问日志保留百度 IP 段 UA（`Baiduspider`）命中率统计，连续 3 日 0 命中告警（邮件/控制台，v1.1 仅日志）
