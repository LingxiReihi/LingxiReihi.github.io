import type { ContentOut } from '@/api/types'

/** 内容的前台链接：文章/模型走 slug，杂谈走 id（此前在四处各写一遍，收成一个）。 */
export function contentLink(c: Pick<ContentOut, 'type' | 'slug' | 'id'>): string {
  if (c.type === 'chat') return `/chats/${c.id}`
  return `/${c.type === 'model' ? 'models' : 'blog'}/${c.slug}`
}

/** 友站等站外链接：值是后台手填的自由文本，只认 http(s) 绝对地址。
 *  javascript:/data: 会直接进 <a href>，协议相对（//host）语义不确定，一律当无效丢掉。 */
export function safeExternalUrl(raw: string): string {
  const url = String(raw ?? '').trim()
  return /^https?:\/\//i.test(url) ? url : ''
}

/** 把地址栏同步为 #<标题 id>；顺手清掉遗留的 ?a= 参数。
 *  id 为空（例如点文章标题那一条）时清除 hash。
 *  用 replaceState 而不是路由跳转：目录点击本身已经滚动过，不能再触发一次锚点定位。 */
export function setAnchorHash(id: string) {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  url.searchParams.delete('a')
  url.hash = id
  window.history.replaceState(window.history.state, '', url)
}

export const TYPE_LABEL: Record<ContentOut['type'], string> = {
  article: '文章',
  model: '作品',
  chat: '杂谈',
}
