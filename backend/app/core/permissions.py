"""后台权限点白名单：新增权限点只改这里，路由不认白名单外的字符串。"""

PERMISSIONS: frozenset[str] = frozenset({
    "content:write",      # 新建/编辑内容（作用域可为栏目）
    "content:delete",     # 删除内容（作用域可为栏目）
    "comment:moderate",   # 审核评论（全站待审队列，不按归属隔离）
    "media:write",        # 上传素材/重新归类
    "media:delete",       # 删除自己上传的素材
    "column:manage",      # 栏目增删改（作用域可为该栏目）
    "tag:manage",         # 标签增删改
    "setting:manage",     # 站点设置
    "stats:view",         # 数据看板
    "log:view",           # 运行日志
    "announcement:manage",  # 更新公告（管理页可写；读全员开放，unread/read 仅登录；仅全局）
    "admin:manage",       # 管理员账号管理（顶级能力，可单独下放）
})

# 允许授到具体栏目上的权限点；其余只接受全局作用域
SCOPED_PERMISSIONS: frozenset[str] = frozenset({"content:write", "content:delete", "column:manage"})

SCOPE_GLOBAL = "global"
SCOPE_COLUMN = "column"
