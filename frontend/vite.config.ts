import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import type { ViteSSGOptions } from 'vite-ssg'

const ROOT = fileURLToPath(new URL('.', import.meta.url))
const STATIC = process.env.VITE_STATIC === 'true'
const SSG_API = process.env.SSG_API_BASE || 'http://127.0.0.1:8000/api/v1'
// 本机 8000 常被无 PID 的旧 uvicorn 占着，用它改指 dev 代理端口，不必把工作树改脏
const DEV_PROXY_TARGET = process.env.DEV_PROXY_TARGET || 'http://127.0.0.1:8000'

async function unwrap(path: string): Promise<any> {
  const r = await fetch(SSG_API + path)
  if (!r.ok) throw new Error(`[vite-ssg] 路由枚举失败 ${path}: HTTP ${r.status}`)
  const j = await r.json() as { code: number; message?: string; data: any }
  if (j.code !== 0) throw new Error(`[vite-ssg] 路由枚举 API 错误 ${path}: ${j.message}`)
  return j.data
}

const ssgOptions: ViteSSGOptions = {
  // 1.6G 小机：页面串行渲染，避免默认 20 并发在构建期把内存/CPU 打满
  concurrency: 1,
  // GitHub Pages 按目录出页：/blog/<slug>/index.html 才能被无扩展名访问
  dirStyle: 'nested',
  // M6：构建期枚举动态路由。静态模式直接读本地快照，CI 无需后端；否则拉后端并 fail-fast
  includedRoutes: async (paths) => {
    const statics = paths.filter(
      (p) => p && !p.startsWith('/admin') && !p.includes(':') && !p.includes('*'),
    )
    if (STATIC) {
      const file = path.join(ROOT, 'static-data', 'site.json')
      let data: any
      try {
        data = JSON.parse(readFileSync(file, 'utf8'))
      } catch {
        throw new Error(`[vite-ssg] 找不到静态快照 ${file}，先运行 npm run export:static`)
      }
      const lists = data.lists ?? {}
      if (!lists.article?.length && !lists.model?.length && !lists.chat?.length) {
        throw new Error('[vite-ssg] 静态快照里没有任何内容，中止构建')
      }
      return [
        ...statics,
        ...(lists.article ?? []).map((c: any) => `/blog/${c.slug}`),
        ...(lists.model ?? []).map((c: any) => `/models/${c.slug}`),
        ...(lists.chat ?? [])
          .filter((c: any) => (c.body_md ?? '').length > 300)
          .map((c: any) => `/chats/${c.id}`),
      ]
    }
    const [posts, models, chats] = await Promise.all([
      unwrap('/posts?page_size=50'),
      unwrap('/models?page_size=50'),
      unwrap('/chats?limit=50'),
    ])
    if (!posts.items.length && !models.items.length) {
      throw new Error('[vite-ssg] 后端可达但无任何 published 内容，中止构建')
    }
    return [
      ...statics,
      ...posts.items.map((c: any) => `/blog/${c.slug}`),
      ...models.items.map((c: any) => `/models/${c.slug}`),
      // 与前端 D2 规则一致：仅长杂谈生成独立可分享页
      ...chats.items
        .filter((c: any) => (c.body_md ?? '').length > 300)
        .map((c: any) => `/chats/${c.id}`),
    ]
  },
}

export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [
    vue({
      template: {
        compilerOptions: { isCustomElement: (tag) => tag === 'model-viewer' },
      },
    }),
    tailwindcss(),
  ],
  ssgOptions,
  // jszip 只在模型工作台打包时动态 import，Vite 扫描不到，不显式声明会在 dev 里
  // 报「Failed to fetch dynamically imported module /deps/jszip.js」
  optimizeDeps: { include: ['jszip'] },
  build: {
    outDir: process.env.SSG_OUT_DIR || 'dist',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': DEV_PROXY_TARGET,
      '/media': DEV_PROXY_TARGET,
      '/sitemap.xml': DEV_PROXY_TARGET,
      '/sitemap.txt': DEV_PROXY_TARGET,
      '/robots.txt': DEV_PROXY_TARGET,
      '/feed.xml': { target: DEV_PROXY_TARGET, rewrite: () => '/api/v1/rss' },
    },
  },
})
