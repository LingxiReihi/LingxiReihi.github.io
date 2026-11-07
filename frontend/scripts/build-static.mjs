// 静态站构建：导出数据 → vite-ssg 预渲染 → 拷 media / SEO / Pages 文件。
// 本地：npm run build:static（需要后端）；CI：npm run build:static:ci（用已提交的 static-data）。
import { spawnSync } from 'node:child_process'
import { cp, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const DIST = path.join(FRONTEND, 'dist')
const DATA = path.join(FRONTEND, 'static-data')
const noExport = process.argv.includes('--no-export')
const ORIGIN = (process.env.VITE_SITE_ORIGIN || 'https://www.lingxi-reihi.cn').replace(/\/$/, '')
const BASE = process.env.VITE_BASE || '/'
const GH_LIMIT = 100 * 1024 * 1024

function run(cmd, args, env = {}) {
  const r = spawnSync(cmd, args, {
    cwd: FRONTEND,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: { ...process.env, ...env },
  })
  if (r.status !== 0) process.exit(r.status ?? 1)
}

async function exists(p) {
  try { await stat(p); return true } catch { return false }
}

async function walk(dir, out = []) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) await walk(p, out)
    else out.push({ file: p, size: (await stat(p)).size })
  }
  return out
}

if (!noExport) run(process.execPath, [path.join('scripts', 'export-static-data.mjs')])

const site = JSON.parse(await readFile(path.join(DATA, 'site.json'), 'utf8'))
const version = site.version || Date.now().toString(36)
console.log(`[static-build] data version ${version}, origin ${ORIGIN}, base ${BASE}`)

await rm(DIST, { recursive: true, force: true })
run(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', 'build:ssg'], {
  VITE_STATIC: 'true',
  VITE_BASE: BASE,
  VITE_SITE_ORIGIN: ORIGIN,
  VITE_STATIC_VERSION: version,
  SSG_OUT_DIR: 'dist',
})

const dataOut = path.join(DIST, 'data')
await mkdir(dataOut, { recursive: true })
await cp(path.join(DATA, 'site.json'), path.join(dataOut, 'site.json'))
await cp(path.join(DATA, 'search.json'), path.join(dataOut, 'search.json'))
await cp(path.join(DATA, 'content'), path.join(dataOut, 'content'), { recursive: true })

if (await exists(path.join(DATA, 'media'))) {
  await cp(path.join(DATA, 'media'), path.join(DIST, 'media'), { recursive: true })
}

for (const f of ['feed.xml', 'sitemap.xml', 'sitemap.txt', 'robots.txt']) {
  if (await exists(path.join(DATA, f))) await cp(path.join(DATA, f), path.join(DIST, f))
}

// GitHub Pages：仓库根 404.html 兜住未知路径，让前端路由显示 404 页
await cp(path.join(DIST, 'index.html'), path.join(DIST, '404.html'))
await writeFile(path.join(DIST, '.nojekyll'), '')
if (!(await exists(path.join(DIST, 'CNAME')))) await writeFile(path.join(DIST, 'CNAME'), 'www.lingxi-reihi.cn\n')

const files = await walk(DIST)
const grow = files.filter((f) => f.size >= GH_LIMIT)
if (grow.length) {
  for (const f of grow) console.error(`[static-build] 超过 GitHub 100MB：${path.relative(DIST, f.file)} ${(f.size / 1048576).toFixed(1)}MB`)
  process.exit(1)
}
const total = files.reduce((n, f) => n + f.size, 0)
console.log(`[static-build] dist ${files.length} 个文件 ${(total / 1048576).toFixed(1)}MB → ${DIST}`)