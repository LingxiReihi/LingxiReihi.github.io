/** Markdown 图片语法解析 + 「本地链接」判定（与后端 app/services/image_import.py 同一口径）。
 *
 *  只做「找出要下载的外链」这一件事，真正的下载在服务端完成（浏览器跨域抓图会被 CORS 拦掉）。
 *  本地链接指：相对路径 / 根路径、本站地址（含 www 与 apex 变体）、本机地址、data: 等内联数据 ——
 *  这些都不该再下载一遍，回写后重复点按钮也不会重复入库。
 */

// ![alt](url "title")，URL 允许 <> 包裹（含空格时必须）
const MD_IMG = /!\[[^\]]*\]\(\s*(<[^<>]*>|[^\s)]+)(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)/g

const NON_FETCH = /^(data|blob|javascript|mailto|tel|about):/i
const LOOPBACK = new Set(['localhost', '127.0.0.1', '::1', '0.0.0.0'])

const unwrap = (raw: string) => (raw.startsWith('<') && raw.endsWith('>') ? raw.slice(1, -1) : raw)

/** 当前访问的主机及其 www/apex 变体 —— 与后端 site_url 的判定结果保持一致 */
function siteHosts(): string[] {
  if (typeof location === 'undefined') return []
  const h = location.hostname.toLowerCase()
  if (!h) return []
  return h.startsWith('www.') ? [h, h.slice(4)] : [h, `www.${h}`]
}

/** 本地链接的判定原因；空串表示这是需要下载入库的外链 */
export function localImageReason(raw: string): string {
  const url = (raw || '').trim()
  if (!url) return '空地址'
  if (NON_FETCH.test(url)) return '内联数据'
  if (url.startsWith('//')) return '站内相对路径'
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return '站内相对路径'          // /media/…、images/x.png 这类没有协议头的地址
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return '站内相对路径'
  const host = u.hostname.toLowerCase()
  if (LOOPBACK.has(host)) return '本机地址'
  if (siteHosts().includes(host)) return '本站地址'
  return ''
}

export function isExternalImageUrl(url: string): boolean {
  return localImageReason(url) === ''
}

/** 正文里所有图片地址（去重，保持出现顺序） */
export function mdImageUrls(md: string): string[] {
  if (!md || !md.includes('![')) return []
  const out: string[] = []
  for (const m of md.matchAll(MD_IMG)) {
    const url = unwrap(m[1])
    if (url && !out.includes(url)) out.push(url)
  }
  return out
}

/** 需要下载入库的外链 */
export function externalImageUrls(md: string): string[] {
  return mdImageUrls(md).filter(isExternalImageUrl)
}

/** 已经在本地的链接（站内 / 本机 / 相对路径 / 内联数据），按钮计数时排除 */
export function localImageUrls(md: string): string[] {
  return mdImageUrls(md).filter((u) => !isExternalImageUrl(u))
}
