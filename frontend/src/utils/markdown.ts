/** 内容 → Markdown 导出（后台「下载 MD」用）。
 *  正文直接取 body_md 原文，不经过渲染；元信息按 YAML front-matter 输出，
 *  方便 Hexo / Hugo / Obsidian 等工具二次导入。 */

export interface MarkdownSource {
  id: number
  type: string
  title: string
  slug?: string | null
  status?: string
  summary?: string
  cover?: string | null
  tags?: { name: string }[]
  column?: { name: string } | null
  published_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  body_md?: string | null
}

/** JSON 字符串（双引号 + 反斜杠转义）本身就是合法的 YAML 双引号标量 */
const yamlStr = (v: string) => JSON.stringify(v)

function frontMatter(c: MarkdownSource): string {
  const lines = ['---', `title: ${yamlStr(c.title)}`]
  if (c.slug) lines.push(`slug: ${yamlStr(c.slug)}`)
  lines.push(`type: ${c.type}`)
  if (c.status) lines.push(`status: ${c.status}`)
  if (c.column?.name) lines.push(`column: ${yamlStr(c.column.name)}`)
  const tags = (c.tags ?? []).map((t) => t.name)
  lines.push(tags.length ? `tags: [${tags.map(yamlStr).join(', ')}]` : 'tags: []')
  if (c.summary) lines.push(`summary: ${yamlStr(c.summary)}`)
  if (c.cover) lines.push(`cover: ${yamlStr(c.cover)}`)
  const dates: [string, string | null | undefined][] = [
    ['created_at', c.created_at], ['updated_at', c.updated_at], ['published_at', c.published_at],
  ]
  for (const [k, v] of dates) if (v) lines.push(`${k}: ${yamlStr(v)}`)
  lines.push('---', '')
  return lines.join('\n')
}

/** slug 优先，退回标题；去掉路径非法字符，避免 Windows 下载报错 */
export function markdownFilename(c: MarkdownSource): string {
  const raw = (c.slug || c.title || `content-${c.id}`).trim()
  const base = raw
    .replace(/[\\/:*?"<>|\s]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
  return `${base || `content-${c.id}`}.md`
}

/** frontMatter=false 时只输出正文，并补一级标题（正文已自带 H1 则不重复） */
export function buildMarkdown(c: MarkdownSource, opts: { frontMatter?: boolean } = {}): string {
  const body = (c.body_md ?? '').replace(/^\uFEFF/, '').trim()
  if (opts.frontMatter !== false) return `${frontMatter(c)}\n${body}\n`
  const hasH1 = /^#\s+\S/m.test(body)
  return `${hasH1 ? '' : `# ${c.title}\n\n`}${body}\n`
}

export function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  // 立即 revoke 会让部分浏览器取消下载，延后释放
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  // 非安全上下文（http / 旧浏览器）走 textarea 兜底
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.top = '-9999px'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  const ok = document.execCommand('copy')
  ta.remove()
  if (!ok) throw new Error('copy failed')
}
