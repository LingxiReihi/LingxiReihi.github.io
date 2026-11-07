// 纯静态数据源：浏览器读 /data/*.json，SSG 构建期读 static-data/*.json。
// 只在 VITE_STATIC=true 时启用，替代运行时的 /api/v1。
import type { AxiosRequestConfig } from 'axios'

import type {
  ColumnOut, ContentDetail, ContentOut, CursorPage, Page, SiteConfig, TagOut,
} from './types'

interface Bundle {
  version: string
  origin: string
  siteConfig: SiteConfig
  home: any
  about: any
  tags: TagOut[]
  columns: ColumnOut[]
  lists: { article: ContentOut[]; model: ContentOut[]; chat: ContentOut[] }
}

interface SearchEntry { id: number; type: string; text: string }

type Params = Record<string, string>

const BASE = import.meta.env.BASE_URL || '/'
const VER = import.meta.env.VITE_STATIC_VERSION || ''
const cache = new Map<string, Promise<any>>()

function dataUrl(name: string) {
  return `${BASE}data/${name}${VER ? `?v=${encodeURIComponent(VER)}` : ''}`
}

async function readJson<T>(name: string): Promise<T> {
  const hit = cache.get(name)
  if (hit) return hit as Promise<T>
  const p = (async () => {
    if (typeof window === 'undefined') {
      const fsSpec = 'node:fs/promises'
      const pathSpec = 'node:path'
      const fs = await import(/* @vite-ignore */ fsSpec)
      const path = await import(/* @vite-ignore */ pathSpec)
      const file = path.resolve(process.cwd(), 'static-data', name)
      return JSON.parse(await fs.readFile(file, 'utf8'))
    }
    const r = await fetch(dataUrl(name))
    if (!r.ok) throw new Error(`静态数据缺失（${name}: HTTP ${r.status}）`)
    return r.json()
  })()
  cache.set(name, p)
  p.catch(() => cache.delete(name))
  return p
}

const bundle = () => readJson<Bundle>('site.json')
const searchIndex = () => readJson<SearchEntry[]>('search.json')

function detailName(type: string, key: string) {
  if (type === 'article') return `content/post/${encodeURIComponent(key)}.json`
  if (type === 'model') return `content/model/${encodeURIComponent(key)}.json`
  return `content/chat/${encodeURIComponent(key)}.json`
}

function parse(config: AxiosRequestConfig): { path: string, params: Params } {
  const url = String(config.url || '')
  const [raw, qs] = url.split('?')
  const params: Params = {}
  if (qs) for (const [k, v] of new URLSearchParams(qs)) params[k] = v
  for (const [k, v] of Object.entries((config.params ?? {}) as Record<string, unknown>)) {
    if (v !== undefined && v !== null && v !== '') params[k] = String(v)
  }
  return { path: raw.replace(/\/+$/, '') || '/', params }
}

function paginate<T>(items: T[], params: Params, fallbackSize = 12): Page<T> {
  const page = Math.max(1, Number(params.page || 1))
  const size = Math.min(50, Math.max(1, Number(params.page_size || fallbackSize)))
  return {
    total: items.length,
    page,
    page_size: size,
    items: items.slice((page - 1) * size, page * size),
  }
}

function scopedColumns(columns: ColumnOut[], type?: string) {
  return type ? columns.filter((c) => c.type === type) : columns
}

function columnSlugs(columns: ColumnOut[], type: string, slug: string, direct: boolean) {
  if (direct) return new Set([slug])
  const scoped = scopedColumns(columns, type)
  const root = scoped.find((c) => c.slug === slug)
  const out = new Set<string>([slug])
  if (!root) return out
  const walk = (c: ColumnOut) => {
    out.add(c.slug)
    for (const k of scoped.filter((x) => x.parent_id === c.id)) walk(k)
  }
  walk(root)
  return out
}

async function searchIds(q: string, type?: string) {
  const kw = q.trim().toLowerCase()
  if (!kw) return new Set<number>()
  const idx = await searchIndex()
  return new Set(idx.filter((e) => (!type || e.type === type) && e.text.includes(kw)).map((e) => e.id))
}

async function filterList(
  items: ContentOut[], type: string, params: Params,
  columnsBySlug: (slug: string, direct: boolean) => Set<string>,
) {
  let out = items
  if (params.q) {
    const ids = await searchIds(params.q, type)
    out = out.filter((c) => ids.has(c.id))
  }
  if (params.tag) {
    const slugs = params.tag.split(',').filter(Boolean)
    out = out.filter((c) => slugs.every((s) => (c.tags ?? []).some((t) => t.slug === s)))
  }
  if (params.column) {
    const allowed = columnsBySlug(params.column, params.column_direct === 'true')
    out = out.filter((c) => c.column && allowed.has(c.column.slug))
  }
  return out
}

// Node 在 SSG 构建期没有 fetch 相对路径；上面已分支为读文件，这里只处理路由。
export async function staticApi<T>(config: AxiosRequestConfig): Promise<T> {
  const { path, params } = parse({ method: 'get', ...config })
  const method = String(config.method || 'get').toUpperCase()
  const b = await bundle()

  // 模型下载：静态站直接给 media URL（不再累加下载数）
  const dl = path.match(/^\/models\/([^/]+)\/download$/)
  if (dl && method === 'POST') {
    const d = await readJson<ContentDetail>(detailName('model', decodeURIComponent(dl[1])))
    const models = (d.assets ?? []).filter((a) => a.kind === 'model3d')
    const asset = params.asset_id
      ? models.find((a) => a.id === Number(params.asset_id))
      : models[0]
    if (!asset) throw new Error('该作品不提供下载')
    return {
      url: asset.url || `/media/${asset.storage_key}`,
      filename: asset.filename,
    } as T
  }
  if (method !== 'GET') throw new Error('静态站点为只读模式，不支持该操作')

  const d = path.match(/^\/posts\/([^/]+)\/preview$/)
  if (d) throw new Error('静态站点不支持草稿预览')

  if (path === '/site-config') return b.siteConfig as T
  if (path === '/home') return b.home as T
  if (path === '/about') return b.about as T
  if (path === '/tags') {
    const items = params.type ? b.tags.filter((t) => t.type === params.type) : b.tags
    return { items } as T
  }
  if (path === '/columns') {
    const items = params.type ? b.columns.filter((c) => c.type === params.type) : b.columns
    return { items } as T
  }

  if (path === '/posts') {
    const out = await filterList(b.lists.article, 'article', params,
      (slug, direct) => columnSlugs(b.columns, 'article', slug, direct))
    return paginate(out, params, 10) as T
  }
  if (path === '/models') {
    let out = await filterList(b.lists.model, 'model', params,
      (slug, direct) => columnSlugs(b.columns, 'model', slug, direct))
    if (params.kind && params.kind !== 'all') out = out.filter((c) => c.media_kind === params.kind)
    return paginate(out, params, 10) as T
  }
  if (path === '/chats') {
    const out = await filterList(b.lists.chat, 'chat', params,
      (slug, direct) => columnSlugs(b.columns, 'chat', slug, direct))
    const limit = Math.min(50, Math.max(1, Number(params.limit || 20)))
    const offset = Math.max(0, Number(params.cursor || 0))
    const items = out.slice(offset, offset + limit)
    const next = offset + limit < out.length ? String(offset + limit) : null
    return { items, next_cursor: next } as CursorPage<ContentOut> as T
  }

  if (path === '/search') {
    const kw = (params.q ?? '').trim()
    if (!kw) return { items: [] } as T
    const idx = await searchIndex()
    const byKey = new Map<string, ContentOut>()
    for (const c of [...b.lists.article, ...b.lists.model, ...b.lists.chat]) {
      byKey.set(`${c.type}:${c.id}`, c)
    }
    const items = idx
      .filter((e) => (!params.type || e.type === params.type) && e.text.includes(kw.toLowerCase()))
      .slice(0, 20)
      .map((e) => byKey.get(`${e.type}:${e.id}`))
      .filter((c): c is ContentOut => !!c)
    return { items } as T
  }

  const post = path.match(/^\/posts\/([^/]+)$/)
  if (post) return readJson<ContentDetail>(detailName('article', decodeURIComponent(post[1]))) as Promise<T>

  const model = path.match(/^\/models\/([^/]+)$/)
  if (model) return readJson<ContentDetail>(detailName('model', decodeURIComponent(model[1]))) as Promise<T>

  const chat = path.match(/^\/chats\/(\d+)$/)
  if (chat) return readJson<ContentDetail>(detailName('chat', chat[1])) as Promise<T>

  throw new Error(`静态站点未实现该接口：${path}`)
}