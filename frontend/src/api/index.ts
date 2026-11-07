import type { AxiosRequestConfig } from 'axios'

import { api, http } from './http'
import type {
  AboutData, Announcement, AdminAccount, AdminComment, AdminUser, ColumnOut, CommentOut, ContentDetail, ContentOut, ContentType, CursorPage, GrantOut, HomeData,
  MediaAsset, MediaCategory, MyProfile, Page, SiteConfig, StatsOverview, TagOut, TokenPair,
} from './types'

const q = (params: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== ''))

export const homeApi = {
  get: () => api<HomeData>({ url: '/home' }),
}

export const postsApi = {
  list: (params: { q?: string; tag?: string; column?: string; column_direct?: boolean; page?: number; page_size?: number } = {}) =>
    api<Page<ContentOut>>({ url: '/posts', params: q(params) }),
  detail: (slug: string) => api<ContentDetail>({ url: `/posts/${slug}` }),
  preview: (slug: string, token: string) =>
    api<ContentDetail>({ url: `/posts/${slug}/preview`, params: { token } } as AxiosRequestConfig),
  like: (slug: string) => api<{ id: number; likes: number }>({ url: `/posts/${slug}/like`, method: 'post' }),
  unlike: (slug: string) => api<{ id: number; likes: number }>({ url: `/posts/${slug}/unlike`, method: 'post' }),
  tags: (type?: ContentType) => api<{ items: TagOut[] }>({ url: '/tags', params: q({ type }) }),
}

export const columnsApi = {
  list: (type?: ContentType) => api<{ items: ColumnOut[] }>({ url: '/columns', params: q({ type }) }),
}

export const modelsApi = {
  list: (params: { kind?: string; tag?: string; column?: string; column_direct?: boolean; page?: number; page_size?: number } = {}) =>
    api<Page<ContentOut>>({ url: '/models', params: q(params) }),
  detail: (slug: string) => api<ContentDetail>({ url: `/models/${slug}` }),
  download: (slug: string, assetId?: number) => api<{ url: string; filename?: string }>({ url: `/models/${slug}/download`, method: 'post', params: assetId ? { asset_id: assetId } : undefined }),
  like: (slug: string) => api<{ id: number; likes: number }>({ url: `/models/${slug}/like`, method: 'post' }),
  unlike: (slug: string) => api<{ id: number; likes: number }>({ url: `/models/${slug}/unlike`, method: 'post' }),
}

export const chatsApi = {
  list: (params: { cursor?: string; limit?: number; tag?: string; column?: string; column_direct?: boolean } = {}) =>
    api<CursorPage<ContentOut>>({ url: '/chats', params: q(params) }),
  detail: (id: number) => api<ContentDetail>({ url: `/chats/${id}` }),
}

export const aboutApi = {
  get: () => api<AboutData>({ url: '/about' }),
}

export const siteApi = {
  config: () => api<SiteConfig>({ url: '/site-config' }),
}

export const searchApi = {
  run: (query: string, type?: string) =>
    api<{ items: ContentOut[] }>({ url: '/search', params: q({ q: query, type }) }),
}

// ── 后台 ──
type AdminContent = ContentOut & {
  status: string
  body_md?: string
  cover_asset_id: number | null
  column_id?: number | null
  created_at: string
  updated_at: string
  assets?: MediaAsset[]
  comment_count?: number
  /** 归属与可编辑性（服务端算好，前端只用于按钮态，不作安全边界） */
  owner_id?: number | null
  owner_nickname?: string | null
  can_edit?: boolean
  can_delete?: boolean
  denied_reason?: string | null
}

interface PipelineInfo { queued: boolean; merged_with_previous?: boolean }

export interface ImportedImage { src: string; url: string; filename: string; asset_id: number; size: number }
export interface FailedImage { src: string; reason: string }
export interface ImportImagesResult {
  body_md: string
  imported: ImportedImage[]
  failed: FailedImage[]
  /** 本地链接（站内/本机/相对路径/内联数据），按原因跳过，不下载 */
  skipped: FailedImage[]
  total: number
}

export const adminContentsApi = {
  list: (params: Record<string, unknown> = {}) =>
    api<Page<AdminContent>>({ url: '/admin/contents', params: q(params) }),
  get: (id: number) => api<AdminContent>({ url: `/admin/contents/${id}` }),
  create: (body: Record<string, unknown>) =>
    api<AdminContent & { pipeline: PipelineInfo | null }>({ url: '/admin/contents', method: 'post', data: body }),
  update: (id: number, body: Record<string, unknown>) =>
    api<AdminContent & { pipeline: PipelineInfo | null }>({ url: `/admin/contents/${id}`, method: 'put', data: body }),
  setStatus: (id: number, status: string) =>
    api<{ pipeline: PipelineInfo | null }>({ url: `/admin/contents/${id}/status`, method: 'patch', data: { status } }),
  remove: (id: number) => api<void>({ url: `/admin/contents/${id}`, method: 'delete' }),
  columnBulk: (ids: number[], column_id: number | null) =>
    api<{ updated: number; skipped: number; denied?: number[] }>({ url: '/admin/contents/column-bulk', method: 'post', data: { ids, column_id } }),
  dashboard: (id: number) =>
    api<AdminContent & { comments: { pending: number; approved: number; rejected: number; total: number } }>(
      { url: `/admin/contents/${id}/dashboard` }),
  resetLikes: (id: number) => api<{ id: number; likes: number }>({ url: `/admin/contents/${id}/reset-likes`, method: 'post' }),
  previewToken: (id: number) => api<{ token: string }>({ url: `/admin/contents/${id}/preview-token`, method: 'post' }),
  /** 外链图片入库：服务端逐张下载并改写正文，返回新 Markdown（不自动保存） */
  importImages: (id: number, body_md: string) =>
    api<ImportImagesResult>({
      url: `/admin/contents/${id}/import-images`, method: 'post', data: { body_md }, timeout: 180000,
    }),
}

export interface MediaGroup {
  id: number
  title: string
  type: string
  slug: string | null
  count: number
}

export const adminMediaApi = {
  list: (params: Record<string, unknown> = {}) => api<Page<MediaAsset>>({ url: '/admin/media', params: q(params) }),
  /** 右下拉数据：引用过素材的内容 + 未被引用计数 */
  contents: () => api<{ items: MediaGroup[]; unused: number; total: number }>({ url: '/admin/media/contents' }),
  upload: (file: File, category?: MediaCategory) => {
    const fd = new FormData()
    fd.append('file', file)
    if (category) fd.append('category', category)
    // 大模型文件（glb/zip ≤200MB）上传远超默认 20s，单独放宽，否则 axios 超时被报成「网络错误」
    return api<MediaAsset>({ url: '/admin/media', method: 'post', data: fd, timeout: 600000 })
  },
  /** 改分类：只改标签，不移动文件、不改 URL */
  categorize: (ids: number[], category: MediaCategory) =>
    api<{ updated: number; denied?: number[] }>({ url: '/admin/media/categorize', method: 'post', data: { ids, category } }),
  /** 重命名：只改展示名，URL 不变 */
  rename: (id: number, filename: string) =>
    api<MediaAsset>({ url: `/admin/media/${id}`, method: 'patch', data: { filename } }),
  remove: (id: number) => api<void>({ url: `/admin/media/${id}`, method: 'delete' }),
}

export const adminTagsApi = {
  list: (type?: ContentType) => api<{ items: TagOut[] }>({ url: '/admin/tags', params: q({ type }) }),
  create: (name: string, type: ContentType) => api<TagOut>({ url: '/admin/tags', method: 'post', data: { name, type } }),
  rename: (id: number, name: string) => api<TagOut>({ url: `/admin/tags/${id}`, method: 'put', data: { name } }),
  remove: (id: number) => api<{ detached: number }>({ url: `/admin/tags/${id}`, method: 'delete' }),
}

export const adminAnnouncementsApi = {
  list: (limit?: number) => api<{ items: Announcement[] }>({ url: '/admin/announcements', params: q({ limit }) }),
  create: (body: { title: string; body_md?: string; status?: 'draft' | 'published'; published_at?: string | null }) =>
    api<Announcement>({ url: '/admin/announcements', method: 'post', data: body }),
  update: (id: number, body: Partial<{ title: string; body_md: string; status: 'draft' | 'published'; published_at: string | null }>) =>
    api<Announcement>({ url: `/admin/announcements/${id}`, method: 'put', data: body }),
  unread: () => api<{ items: Announcement[] }>({ url: '/admin/announcements/unread' }),
  markRead: (ids: number[]) => api<{ marked: number }>({ url: '/admin/announcements/read', method: 'post', data: { ids } }),
  remove: (id: number) => api<{ deleted: number }>({ url: `/admin/announcements/${id}`, method: 'delete' }),
}

export const adminColumnsApi = {
  list: (type?: ContentType) => api<{ items: ColumnOut[] }>({ url: '/admin/columns', params: q({ type }) }),
  create: (body: { name: string; slug?: string; summary?: string; sort_order?: number; type?: ContentType; parent_id?: number | null }) =>
    api<ColumnOut>({ url: '/admin/columns', method: 'post', data: body }),
  update: (id: number, body: { name: string; slug?: string; summary?: string; sort_order?: number; type?: ContentType; parent_id?: number | null }) =>
    api<ColumnOut>({ url: `/admin/columns/${id}`, method: 'put', data: body }),
  remove: (id: number) => api<{ detached: number }>({ url: `/admin/columns/${id}`, method: 'delete' }),
}

export const adminSettingsApi = {
  getAll: () => api<Record<string, Record<string, unknown>>>({ url: '/admin/settings' }),
  putGroup: (group: string, body: Record<string, unknown>) =>
    api<Record<string, unknown>>({ url: `/admin/settings/${group}`, method: 'put', data: body }),
}

export const adminProfileApi = {
  get: () => api<MyProfile>({ url: '/admin/profile' }),
  update: (body: Partial<Pick<MyProfile, 'nickname' | 'avatar' | 'signature' | 'social_links'
    | 'bio_md' | 'skills' | 'experience'>>) =>
    api<MyProfile>({ url: '/admin/profile', method: 'put', data: body }),
}

export const adminAdminsApi = {
  list: () => api<{ total: number; items: AdminAccount[] }>({ url: '/admin/admins' }),
  create: (body: { username: string; password: string; email: string; nickname?: string; note?: string; grants?: GrantOut[] }) =>
    api<AdminAccount>({ url: '/admin/admins', method: 'post', data: body }),
  update: (id: number, body: { nickname?: string; note?: string; email?: string; is_active?: boolean; password?: string;
    avatar?: string; signature?: string; social_links?: { platform: string; url: string }[];
    bio_md?: string; skills?: unknown[]; experience?: unknown[] }) =>
    api<AdminAccount>({ url: `/admin/admins/${id}`, method: 'put', data: body }),
  setGrants: (id: number, grants: GrantOut[]) =>
    api<AdminAccount>({ url: `/admin/admins/${id}/grants`, method: 'put', data: { grants } }),
  resetPassword: (id: number) =>
    api<AdminAccount & { password: string; message: string }>({ url: `/admin/admins/${id}/reset-password`, method: 'post' }),
  remove: (id: number) => api<void>({ url: `/admin/admins/${id}`, method: 'delete' }),
}

export interface LogFile { name: string, size: number, mtime: string }

export const adminLogsApi = {
  files: () => api<{ items: LogFile[] }>({ url: '/admin/logs/files' }),
  tail: (file: string, lines = 300, grep?: string) =>
    api<{ total: number, lines: string[] }>({ url: '/admin/logs/tail', params: q({ file, lines, grep }) }),
  download: async (file: string) =>
    (await http.get('/admin/logs/download', { params: { file }, responseType: 'blob' })).data as Blob,
  archive: async () =>
    (await http.get('/admin/logs/archive', { responseType: 'blob' })).data as Blob,
}

export const adminStatsApi = {
  overview: () => api<StatsOverview>({ url: '/admin/stats/overview' }),
  trend: (start?: string, end?: string) =>
    api<{ days: { day: string; pv: number; uv: number }[] }>({ url: '/admin/stats/trend', params: q({ start, end }) }),
  topContent: (range = '7d', limit = 10, type?: string) =>
    api<{ items: Record<string, unknown>[] }>({ url: '/admin/stats/top-content', params: q({ range, limit, type }) }),
  contentDrill: (id: number, start?: string, end?: string) =>
    api<{ days: unknown[]; sources: unknown[] }>({ url: `/admin/stats/content/${id}`, params: q({ start, end }) }),
  sources: (range = '7d') =>
    api<{ items: { referrer: string; pv: number }[]; direct: number; search: number; social: number; other: number }>(
      { url: '/admin/stats/sources', params: { range } }),
  exportUrl: (start?: string, end?: string) =>
    `/api/v1/admin/stats/export?${new URLSearchParams(q({ start, end }) as Record<string, string>)}`,
}

export const adminSeoApi = {
  config: () =>
    api<{ push_enabled: boolean; api_configured: boolean; rebuild_configured: boolean; rebuild_watcher: boolean; site_url: string }>(
      { url: '/admin/seo/config' }),
  push: (body: Record<string, unknown>) =>
    api<{ success: number; fail: number; skipped: number; already: number; notice: string[] }>(
      { url: '/admin/seo/push', method: 'post', data: body }),
  pushLogs: (page = 1) => api<Page<Record<string, unknown>>>({ url: '/admin/seo/push-logs', params: { page } }),
  rebuild: () => api<{ queued: boolean }>({ url: '/admin/seo/rebuild', method: 'post' }),
  jobs: () => api<{ items: Record<string, unknown>[] }>({ url: '/admin/seo/jobs' }),
}

export const adminAuthApi = {
  password: (old_password: string, new_password: string) =>
    api<void>({ url: '/admin/auth/password', method: 'post', data: { old_password, new_password } }),
  // 新口令只进邮件；服务端最坏要等发信 15s，默认 20s 余量太薄，这里单独放宽
  forgotPassword: (username: string) =>
    api<string>({ url: '/admin/auth/forgot-password', method: 'post', data: { username }, timeout: 30000 }),
}

export const commentsApi = {
  list: (contentId: number, page = 1, pageSize = 20) =>
    api<Page<CommentOut>>({ url: '/comments', params: { content_id: contentId, page, page_size: pageSize } }),
  create: (body: { content_id: number; nickname: string; email: string; body: string; website?: string }) =>
    api<{ pending: boolean }>({ url: '/comments', method: 'post', data: body }),
}

export const adminCommentsApi = {
  list: (params: Record<string, unknown> = {}) =>
    api<Page<AdminComment> & { pending: number }>({ url: '/admin/comments', params: q(params) }),
  moderate: (ids: number[], status: string) =>
    api<{ updated: number }>({ url: '/admin/comments/moderate', method: 'post', data: { ids, status } }),
  remove: (id: number) => api<void>({ url: `/admin/comments/${id}`, method: 'delete' }),
}

export type { AdminContent, TokenPair, AdminUser }
