// 本地预览 dist（模拟 GitHub Pages：目录 index、extensionless、404.html）。
import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const PORT = Number(process.env.PORT || 4173)
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
  '.glb': 'model/gltf-binary', '.zip': 'application/zip', '.xml': 'application/xml; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8', '.woff2': 'font/woff2', '.mp4': 'video/mp4',
}

async function find(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0])
  const candidates = [clean, path.join(clean, 'index.html'), `${clean}.html`]
  for (const c of candidates) {
    const p = path.resolve(ROOT, '.' + (c.startsWith('/') ? c : `/${c}`))
    if (!p.startsWith(ROOT)) continue
    try {
      if ((await stat(p)).isFile()) return p
    } catch { /* try next */ }
  }
  return null
}

createServer(async (req, res) => {
  const file = await find(req.url || '/')
  const target = file || path.join(ROOT, '404.html')
  const ext = path.extname(target)
  res.writeHead(file ? 200 : 404, { 'content-type': MIME[ext] || 'application/octet-stream' })
  createReadStream(target).pipe(res)
}).listen(PORT, '127.0.0.1', () => {
  console.log(`[preview-static] http://127.0.0.1:${PORT} → ${ROOT}`)
})