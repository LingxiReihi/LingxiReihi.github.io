// 从本地后端导出静态站点所需数据（构建期一次运行，产物进 static-data/）。
// 运行：STATIC_API_BASE=http://127.0.0.1:8000/api/v1 node scripts/export-static-data.mjs
import { cp, mkdir, rm, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const OUT = path.join(FRONTEND, 'static-data')
const API = (process.env.STATIC_API_BASE || process.env.SSG_API_BASE || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
const ORIGIN = (process.env.STATIC_SITE_ORIGIN || process.env.VITE_SITE_ORIGIN || 'https://www.lingxi-reihi.cn').replace(/\/$/, '')
const MEDIA_ROOT = process.env.STATIC_MEDIA_ROOT || path.join(FRONTEND, '..', 'backend', 'data', 'media')
const GH_LIMIT = 100 * 1024 * 1024

async function get(pathname) {
  const r = await fetch(API + pathname)
  if (!r.ok) throw new Error(`[static-export] ${pathname}: HTTP ${r.status}`)
  const j = await r.json()
  if (j.code !== 0) throw new Error(`[static-export] ${pathname}: ${j.message}`)
  return j.data
}

async function allPages(pathname) {
  const items = []
  for (let page = 1; page < 1000; page++) {
    const d = await get(`${pathname}?page=${page}&page_size=50`)
    items.push(...d.items)
    if (items.length >= d.total || !d.items.length) return items
  }
  throw new Error(`[static-export] ${pathname}: 分页超过 1000 页`)
}

async function allChats() {
  const items = []
  let cursor = null
  for (let i = 0; i < 1000; i++) {
    const q = cursor ? `?limit=50&cursor=${encodeURIComponent(cursor)}` : '?limit=50'
    const d = await get('/chats' + q)
    items.push(...d.items)
    if (!d.next_cursor) return items
    cursor = d.next_cursor
  }
  throw new Error('[static-export] /chats: 游标超过 1000 页')
}

const stripMd = (s) => String(s || '')
  .replace(/```[\s\S]*?```/g, ' ')
  .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
  .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
  .replace(/<[^>]+>/g, ' ')
  .replace(/[#>*_`~|]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

const enc = (s) => encodeURIComponent(String(s))

async function writeJson(rel, value) {
  const file = path.join(OUT, rel)
  await mkdir(path.dirname(file), { recursive: true })
  await writeFile(file, JSON.stringify(value))
}

async function checkMediaSize(dir) {
  let total = 0
  let max = { size: 0, file: '' }
  async function walk(d) {
    const { readdir } = await import('node:fs/promises')
    for (const e of await readdir(d, { withFileTypes: true })) {
      const p = path.join(d, e.name)
      if (e.isDirectory()) await walk(p)
      else {
        const s = (await stat(p)).size
        total += s
        if (s > max.size) max = { size: s, file: p }
      }
    }
  }
  await walk(dir)
  return { total, max }
}

console.log(`[static-export] API ${API}`)
console.log(`[static-export] ORIGIN ${ORIGIN}`)

const [siteConfig, home, about, tags, columns] = await Promise.all([
  get('/site-config'),
  get('/home'),
  get('/about'),
  get('/tags'),
  get('/columns'),
])
const allTags = tags.items ?? []
const allColumns = columns.items ?? []

const [posts, models, chats] = await Promise.all([
  allPages('/posts'),
  allPages('/models'),
  allChats(),
])
console.log(`[static-export] posts=${posts.length} models=${models.length} chats=${chats.length}`)

await rm(OUT, { recursive: true, force: true })
await mkdir(path.join(OUT, 'content'), { recursive: true })

const details = { article: {}, model: {}, chat: {} }
const search = []
const updatedAt = new Map()

async function fetchDetail(type, key, pathname) {
  const d = await get(pathname)
  details[type][String(key)] = d
  const slugPart = type === 'article' ? 'post' : type === 'model' ? 'model' : 'chat'
  const fileKey = type === 'chat' ? String(d.id) : enc(d.slug)
  await writeJson(`content/${slugPart}/${fileKey}.json`, d)
  updatedAt.set(`${type}:${d.id}`, d.updated_at || d.published_at)
  search.push({
    id: d.id,
    type,
    text: [d.title, d.summary, ...(d.tags || []).map((t) => t.name), stripMd(d.body_md)]
      .filter(Boolean).join(' ').toLowerCase(),
  })
  return d
}

for (const c of posts) await fetchDetail('article', c.slug, `/posts/${enc(c.slug)}`)
for (const c of models) await fetchDetail('model', c.slug, `/models/${enc(c.slug)}`)
for (const c of chats) await fetchDetail('chat', c.id, `/chats/${c.id}`)

const version = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)
const site = {
  version,
  origin: ORIGIN,
  generatedAt: new Date().toISOString(),
  siteConfig,
  home,
  about,
  tags: allTags,
  columns: allColumns,
  lists: { article: posts, model: models, chat: chats },
}
await writeJson('site.json', site)
await writeJson('search.json', search)

// ── SEO 静态文件 ──
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const siteTitle = siteConfig?.site?.title || 'Blog'
const siteDesc = stripMd(siteConfig?.site?.description || '')

const recent = [...posts].slice(0, 20)
const rss = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
  + `<title>${esc(siteTitle)}</title><link>${ORIGIN}</link><description>${esc(siteDesc)}</description>`
  + recent.map((c) => {
    const link = `${ORIGIN}/blog/${c.slug}`
    const pub = new Date(c.published_at || c.updated_at || Date.now()).toUTCString()
    return `<item><title>${esc(c.title)}</title><link>${link}</link><guid>${link}</guid>`
      + `<pubDate>${pub}</pubDate><description>${esc(c.summary)}</description></item>`
  }).join('')
  + '</channel></rss>'
await writeFile(path.join(OUT, 'feed.xml'), rss)

const sections = [['/', 'hourly'], ['/blog', 'daily'], ['/models', 'daily'], ['/chats', 'hourly'], ['/about', 'weekly']]
const rows = [
  ...posts.map((c) => ({ loc: `${ORIGIN}/blog/${c.slug}`, lastmod: updatedAt.get(`article:${c.id}`) })),
  ...models.map((c) => ({ loc: `${ORIGIN}/models/${c.slug}`, lastmod: updatedAt.get(`model:${c.id}`) })),
  ...chats.map((c) => ({ loc: `${ORIGIN}/chats/${c.id}`, lastmod: updatedAt.get(`chat:${c.id}`) })),
].sort((a, b) => String(b.lastmod || '').localeCompare(String(a.lastmod || '')))
const iso = (v) => (v ? new Date(v).toISOString().replace(/\.\d{3}Z$/, 'Z') : '')
const xml = ['<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for (const [p, freq] of sections) xml.push(`<url><loc>${ORIGIN}${p}</loc><changefreq>${freq}</changefreq></url>`)
for (const r of rows) xml.push(`<url><loc>${r.loc}</loc>${r.lastmod ? `<lastmod>${iso(r.lastmod)}</lastmod>` : ''}<changefreq>weekly</changefreq></url>`)
xml.push('</urlset>')
await writeFile(path.join(OUT, 'sitemap.xml'), xml.join('\n'))
await writeFile(path.join(OUT, 'sitemap.txt'),
  [...sections.map(([p]) => `${ORIGIN}${p}`), ...rows.map((r) => r.loc)].join('\n'))
await writeFile(path.join(OUT, 'robots.txt'),
  `User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nContent-Signal: ai-train=no, search=yes, ai-input=no\n\nSitemap: ${ORIGIN}/sitemap.xml\n`)

// ── media ──
let mediaSummary = 'skipped'
try {
  const info = await stat(MEDIA_ROOT)
  if (!info.isDirectory()) throw new Error('not a directory')
  await cp(MEDIA_ROOT, path.join(OUT, 'media'), { recursive: true })
  const { total, max } = await checkMediaSize(path.join(OUT, 'media'))
  mediaSummary = `${(total / 1048576).toFixed(1)}MB, max ${(max.size / 1048576).toFixed(1)}MB ${max.file}`
  if (max.size >= GH_LIMIT) throw new Error(`[static-export] 单个文件超过 GitHub 100MB 限制：${max.file}`)
} catch (e) {
  if (e?.code !== 'ENOENT') throw e
  console.warn(`[static-export] media 目录不存在，跳过：${MEDIA_ROOT}`)
}

console.log(`[static-export] 输出 ${OUT}`)
console.log(`[static-export] 详情 ${search.length} 条，media ${mediaSummary}`)