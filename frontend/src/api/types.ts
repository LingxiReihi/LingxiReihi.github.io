/** 与后端 DTO 对齐的共享类型（docs/api-reference.md）。 */

export type ContentType = 'article' | 'model' | 'chat'
export type MediaKind = '3d' | 'render' | 'animation'

export interface TagOut {
  id: number
  name: string
  slug: string
  /** 标签体系按内容类型隔离：同名标签可在不同 type 下各自存在 */
  type: ContentType
  count?: number
}

/** 栏目：文章的单归属分组（一篇内容最多属于一个栏目），按类型隔离 */
export interface ColumnOut {
  id: number
  name: string
  slug: string
  type: ContentType
  summary: string
  /** 本级直属内容数（后台栏目管理与删除确认用它） */
  count?: number
  /** 自身 + 全部子孙的内容数（前台目录栏徽章用它，与点进去的筛选结果同口径） */
  total?: number
  sort_order?: number
  parent_id?: number | null
  /** 当前登录管理员能否改/删该栏目 */
  can_manage?: boolean
}

export interface ColumnBrief {
  id: number
  name: string
  slug: string
  type: ContentType
}

export interface ContentOut {
  id: number
  type: ContentType
  title: string
  slug: string | null
  summary: string
  cover: string | null
  tags: TagOut[]
  published_at: string | null
  view_count: number
  likes: number
  media_kind?: MediaKind | null
  extra: Record<string, unknown>
  column?: ColumnBrief | null
  /** 仅杂谈列表/详情携带（短内容直出） */
  body_md?: string
}

export interface ContentDetail extends ContentOut {
  body_md: string
  assets: MediaAsset[]
  prev: { slug: string; title: string; cover: string | null } | null
  next: { slug: string; title: string; cover: string | null } | null
  related: ContentOut[]
  /** 详情页规格表：最近更新与文件下载次数 */
  updated_at?: string | null
  downloads?: number
  /** 内容页作者署名：白名单只有昵称与头像（不含邮箱/登录名/角色） */
  author?: { nickname: string; avatar: string }
}

/** 管理员自己的资料（/admin/profile）；bio/skills/experience 仅 super 可改 */
export interface MyProfile {
  id: number
  username: string
  email: string | null
  nickname: string
  avatar: string
  signature: string
  bio_md: string
  social_links: SocialLink[]
  skills: { group: string; items: string[] }[]
  experience: AboutData['experience']
  editable: string[]
  is_super: boolean
}

export type MediaCategory = 'blog' | 'avatar' | 'render' | 'model' | 'site'
export const MEDIA_CATEGORIES: { value: MediaCategory; label: string }[] = [
  { value: 'blog', label: '博客图片' },
  { value: 'avatar', label: '头像' },
  { value: 'render', label: '渲染图' },
  { value: 'model', label: '模型' },
  { value: 'site', label: '站点素材' },
]
export const mediaCategoryLabel = (c: MediaCategory | null | undefined) =>
  c ? MEDIA_CATEGORIES.find((x) => x.value === c)?.label ?? c : '未分类'

export interface MediaAsset {
  id: number
  url: string
  filename?: string
  kind: 'image' | 'model3d' | 'video' | 'file'
  mime: string
  size: number
  width: number | null
  height: number | null
  thumb: string | null
  storage_key: string
  category?: MediaCategory | null
  /** zip 素材的内容清单（后端读中央目录得到，含层级路径） */
  entries?: { path: string; size: number }[] | null
  uploaded_at?: string
  /** 后台列表附带：上传者与可删性（素材库全站可见，归属只约束删除） */
  uploader_id?: number | null
  uploader_nickname?: string | null
  can_delete?: boolean
  /** 引用它的内容（正文链接 / 封面 / 模型附件），自动归组用，实时计算 */
  used_by?: { id: number; title: string; type: string; slug: string | null }[]
}

export interface Page<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

/** 热门位：多带已过审评论数与后端算好的热度分（权重不要在前端再抄一份） */
export interface HotOut extends ContentOut {
  comment_count: number
  score: number
}

/** 首页/关于页的团队名片（公开白名单，只有这三项） */
export interface TeamMember {
  nickname: string
  avatar: string
  signature: string
}

export interface HomeData {
  profile: { nickname: string; avatar: string; signature: string; social_links: SocialLink[] }
  recent_posts: ContentOut[]
  recent_chats: ContentOut[]
  /** 跨类型最新（文章/模型/杂谈混排，按发布时间倒序） */
  latest: ContentOut[]
  hot: HotOut[]
  /** 所有在职管理员（含 super），首页名片条用 */
  team: TeamMember[]
}

export interface SocialLink {
  platform: string
  url: string
}

/** About 上的一份管理员资料（公开白名单：资料类字段，不含邮箱/登录名/角色/备注） */
export interface AboutMember {
  nickname: string
  avatar: string
  signature: string
  bio_md: string
  social_links: SocialLink[]
  skills: { group: string; items: string[] }[]
  experience: {
    kind: string
    title: string
    org: string
    start: string
    end: string | null
    desc: string
  }[]
}

export interface AboutData extends AboutMember {
  /** 「管理团队」名单：所有在职管理员（super 除外，它是主体） */
  team?: AboutMember[]
}

export interface SiteConfig {
  site: { title: string; subtitle: string; description: string; favicon: string; icon: string }
  nav_items: { label: string; path: string; visible: boolean; order: number }[]
  footer: { links: SocialLink[]; copyright: string; beian: string }
  profile: { nickname: string; avatar: string; signature: string; social_links: SocialLink[] }
}

export interface AdminUser {
  id: number
  username: string
  nickname: string
  role?: 'super' | 'staff'
  is_super?: boolean
  is_active?: boolean
  /** 权限点集合；super 为全量白名单 */
  permissions?: string[]
  /** 栏目级授权涉及的栏目 id */
  scoped_column_ids?: number[]
}

export interface GrantOut {
  permission: string
  /** null = 全局作用域 */
  column_id: number | null
}

export interface AdminAccount {
  id: number
  username: string
  nickname: string
  /** 建号必填且全站唯一；迁移前的存量账号为 null */
  email: string | null
  /** 资料跟人走：列表直接带上，供头像与署名展示 */
  avatar?: string
  signature?: string
  role: 'super' | 'staff'
  is_super: boolean
  is_active: boolean
  note: string
  last_login_at: string | null
  created_at?: string
  content_count: number
  media_count: number
  grants: GrantOut[]
  permissions: string[]
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  expires_in: number
  user?: AdminUser
}

export interface StatsOverview {
  today: { pv: number; uv: number }
  yesterday: { pv: number; uv: number }
  total_published: Record<string, number>
  storage_used: number
  media_count: number
}

export interface CommentOut {
  id: number
  nickname: string
  avatar: string
  body: string
  created_at: string
}

export interface AdminComment extends CommentOut {
  content_id: number
  content_title: string | null
  email: string
  status: 'pending' | 'approved' | 'rejected'
  submit_ip: string
  reviewed_at: string | null
}

/** 更新公告（本期由后台「登录弹窗 + 独立管理页」消费；status/published_at 为前台预留） */
export interface Announcement {
  id: number
  title: string
  body_md: string
  status: 'draft' | 'published'
  published_at: string | null
  created_at: string | null
  created_by: string | null
}
