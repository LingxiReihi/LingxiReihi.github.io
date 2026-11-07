import MarkdownIt from 'markdown-it'
import type { Token } from 'markdown-it'
import katexModule from '@vscode/markdown-it-katex'
import markdownItMark from 'markdown-it-mark'
import markdownItSub from 'markdown-it-sub'
import markdownItSup from 'markdown-it-sup'

// 这个包只有 CJS 产物：Node（vite-ssg 构建期）走 cjs-module-lexer 会把 default 再包一层，
// 浏览器侧 vite 预打包后 default 就是函数本身。本文件两个环境都要跑，所以取一次兜底。
const katexPlugin = ((katexModule as unknown as { default?: unknown }).default ?? katexModule) as
  (md: InstanceType<typeof MarkdownIt>, options?: Record<string, unknown>) => void

export interface TocItem {
  id: string
  level: number
  text: string
}

function inlineText(tokens: Token[] | null = []): string {
  return (tokens ?? []).filter((t) => t.type === 'text' || t.type === 'code_inline').map((t) => t.content).join('')
}

function createMd(toc: TocItem[]) {
  const md = new MarkdownIt({ html: false, linkify: true, typographer: false })
  // 扩展语法：H~2~O 下标、X^2^ 上标、==高亮==、$E=mc^2$ 行内公式；
  // ~~删除线~~ 不用装插件——markdown-it 的 default 预设自带 del 规则。
  // KaTeX 只产 HTML+MathML、不碰 DOM，所以 vite-ssg 构建期照跑，公式进得了预渲染 HTML。
  md.use(markdownItSub).use(markdownItSup).use(markdownItMark)
    .use(katexPlugin, { throwOnError: false })
  md.renderer.rules.fence = (tokens, idx) => {
    const t = tokens[idx]
    const lang = (t.info || '').split(/\s+/)[0] || 'text'
    return `<pre class="code-block"><code class="language-${lang}">${md.utils.escapeHtml(t.content)}</code></pre>\n`
  }
  // 表格套滚动容器：窄屏不再把列挤成竖排，超宽时左右滑动
  md.renderer.rules.table_open = () => '<div class="table-wrap"><table>'
  md.renderer.rules.table_close = () => '</table></div>'
  const origHeading = md.renderer.rules.heading_open
  // 可读锚点：保留中文/数字/点/下划线/连字符（如「2.使用教程」），其余字符换成 -；
  // 重名追加 -2 / -3，保证 id 唯一。地址栏直接用 #<id> 即可原生跳转。
  const usedIds = new Map<string, number>()
  const headingId = (text: string) => {
    const base = text
      .replace(/\s+/g, '')
      .replace(/[^\p{L}\p{N}._-]+/gu, '-')
      .replace(/-+/g, '-')
      .replace(/^-+|-+$/g, '')
    const key = base || 'section'
    const n = usedIds.get(key) ?? 0
    usedIds.set(key, n + 1)
    return n === 0 ? key : `${key}-${n + 1}`
  }
  md.renderer.rules.heading_open = (tokens, idx, options, env, self) => {
    const t = tokens[idx]
    const level = Number(t.tag.slice(1))
    if (level >= 2 && level <= 3) {
      const text = inlineText(tokens[idx + 1]?.children).trim()
      const id = headingId(text)
      toc.push({ id, level, text })
      t.attrSet('id', id)
      // 原文兜底：#<原文> 在 id 被 slug 化时仍可定位到这一节
      if (text) t.attrSet('data-a', text)
    }
    return origHeading
      ? origHeading(tokens, idx, options, env, self)
      : `<h${level}${self.renderAttrs(t)}>`
  }
  return md
}

/** CSDN 风格内嵌目录占位符：整行 @[TOC] 或 @[TOC](自定义标题) */
const TOC_LINE = /^@\[TOC\](?:\(([^)]*)\))?[ \t]*$/gm

/**
 * CommonMark 规则：闭合 ** 前是全角标点、后接汉字时不构成 right-flanking，
 * `**方法一+拼接：**虽然` 整串按字面输出。此类场景在 ** 后补一个半角空格
 * （CJK 排版下几乎不可见）即可恢复加粗。
 */
const CJK_PUNCT = '[\u3001\u3002\u300a\u300b\u300c\u300d\u300e\u300f\uff01\uff08\uff09\uff0c\uff1a\uff1b\uff1f\uff5e\u201c\u201d\u2018\u2019\u2026\u2014]'
function fixCjkEmphasis(src: string): string {
  return src.replace(new RegExp(`(${CJK_PUNCT})\\*\\*(?=[\\u4e00-\\u9fff])`, 'g'), '$1** ')
}

/** Typora 导出常带 <img src="…" style="zoom:50%"/>：html:false 下会按字面输出。
 *  预转成 markdown 图片并记下缩放比例，渲染后回填 width。 */
function extractImgZoom(src: string, widths: Map<string, string>): string {
  return src.replace(/<img\b[^>]*>/gi, (tag) => {
    const s = tag.match(/\bsrc\s*=\s*"([^"]+)"|\bsrc\s*=\s*'([^']+)'/i)
    if (!s) return tag
    const url = s[1] ?? s[2]
    const alt = tag.match(/\balt\s*=\s*"([^"]*)"/i)?.[1] ?? ''
    const zoom = tag.match(/zoom:\s*(\d+(?:\.\d+)?)\s*%/i)?.[1]
    const w = tag.match(/\bwidth\s*=\s*"(\d+(?:\.\d+)?)(%|px)?"/i)
    if (zoom) widths.set(url, `${zoom}%`)
    else if (w) widths.set(url, `${w[1]}${w[2] ?? 'px'}`)
    return `![${alt}](<${url}>)`
  })
}

/** 代码区外才做文本替换：正文里的 ``` 围栏与 `行内代码` 必须原样保留，
 *  否则教程里写的 <br> 示例会被换成哨兵、再被还原成真标签。
 *  不用 `({3,})...\1` 那种反向引用：组号指向整个交替式，围栏会被截断成「只有开头那行」。 */
const CODE_REGION = /(```[^\n]*\n[\s\S]*?```|~~~[^\n]*\n[\s\S]*?~~~|`[^`\n]*`)/g

/** 渲染结果里的代码区（回填哨兵时要跳过） */
const OUT_CODE_HTML = /(<code[\s\S]*?<\/code>|<pre[\s\S]*?<\/pre>)/g

function mapOutsideCode(src: string, fn: (text: string) => string): string {
  return src.split(CODE_REGION).map((part, i) => (i % 2 === 1 ? part : fn(part))).join('')
}

/** style 白名单：够排布与字号字色用，不给定位能力（position 一律拒绝，防覆盖全站 UI）。 */
const STYLE_PROPS = new Set([
  'color', 'background-color', 'font-size', 'font-weight', 'font-style', 'font-family',
  'text-align', 'text-decoration', 'text-indent', 'line-height', 'letter-spacing',
  'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
  'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'width', 'max-width', 'min-width', 'border', 'border-radius', 'display',
  'white-space', 'vertical-align',
])
const STYLE_BAD = /url\s*\(|expression|behavior|-moz-binding|javascript:|image-set|@import/i

function cleanStyle(value: string): string {
  return value.split(';').map((d) => {
    const i = d.indexOf(':')
    if (i < 0) return ''
    const prop = d.slice(0, i).trim().toLowerCase()
    const val = d.slice(i + 1).trim()
    return STYLE_PROPS.has(prop) && val && val.length <= 120 && !STYLE_BAD.test(val) ? `${prop}:${val}` : ''
  }).filter(Boolean).join(';')
}

/** 只放行无 scheme 的站内相对地址与 http(s)/mailto；data: 与 javascript: 一律丢。 */
function cleanUrl(value: string): string {
  const v = value.trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return /^(https?:|mailto:)/i.test(v) ? v : ''
  return v
}

const ATTR_RULES: Record<string, (v: string) => boolean> = {
  align: (v) => /^(left|right|center|justify)$/i.test(v),
  width: (v) => /^\d{1,4}(px|%)?$/i.test(v),
  height: (v) => /^\d{1,4}(px|%)?$/i.test(v),
  colspan: (v) => /^\d{1,2}$/.test(v),
  rowspan: (v) => /^\d{1,2}$/.test(v),
  span: (v) => /^\d{1,3}$/.test(v),
  size: (v) => /^[+-]?[1-7]$/.test(v),
  color: (v) => /^#[0-9a-f]{3,6}$|^[\w]{3,20}$/i.test(v),
  face: (v) => /^[\w ,'-]{1,60}$/.test(v),
  type: (v) => /^[\w/.+-]{1,60}$/.test(v),
  target: (v) => /^_blank$/i.test(v),
  href: (v) => cleanUrl(v) !== '',
  src: (v) => cleanUrl(v) !== '',
  poster: (v) => cleanUrl(v) !== '',
  title: (v) => v.length <= 200,
  alt: (v) => v.length <= 200,
  open: (v) => v === '' || /^open$/i.test(v),
  controls: (v) => v === '' || /^controls$/i.test(v),
}

const URL_ATTRS = new Set(['href', 'src', 'poster'])
/** 无值布尔属性：`<video controls>` 不带 =""，不能因为值为空就被丢掉 */
const BOOLEAN_ATTRS = new Set(['controls', 'open', 'loop', 'muted', 'autoplay', 'playsinline'])

const ATTR_RE = /([a-zA-Z-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'`=<>]+)))?/g

/** 按白名单重建开标签属性；class 与 on* 一律不进（用户拍板），<a> 强制补 rel。 */
function rebuildOpenTag(tag: string, raw: string, spec: MdHtmlTag): string {
  const allowed = new Set([...(spec.attrs ?? []), ...(spec.style === false ? [] : ['style'])])
  const parts: string[] = []
  for (const m of raw.matchAll(ATTR_RE)) {
    const name = m[1].toLowerCase()
    if (!allowed.has(name)) continue
    if (!m[0].includes('=')) {
      if (BOOLEAN_ATTRS.has(name)) parts.push(name)
      continue
    }
    const value = (m[2] ?? m[3] ?? m[4] ?? '').trim()
    const rule = ATTR_RULES[name]
    if (rule && !rule(value)) continue
    const safe = name === 'style' ? cleanStyle(value) : (URL_ATTRS.has(name) ? cleanUrl(value) : value)
    if (!safe) continue
    parts.push(`${name}="${escapeText(safe)}"`)
  }
  if (tag === 'a' && parts.some((p) => p.startsWith('target='))) parts.push('rel="noopener noreferrer"')
  return `<${tag}${parts.length ? ' ' + parts.join(' ') : ''}>`
}

/** 正文里放行的 HTML 标签。走「哨兵预转换 + 属性白名单重建」，不是 markdown-it 的 html:true，
 *  所以 <script>、on*、class、<style>、<iframe> 一律按字面显示（这三项由用户拍板全禁）。
 *  右侧「语法」抽屉直接读这张表生成 —— 改这里界面跟着变，不会两处漂移。 */
export interface MdHtmlTag {
  /** 除 style 外额外放行的属性；style 默认放行，除非 style:false */
  attrs?: string[]
  /** 块级：独占一行时不会被 <p> 包住 */
  block?: boolean
  /** 自闭合：写成 </br> 这类收尾也当它本体 */
  void?: boolean
  style?: false
  desc: string
  eg: string
}

export const MD_HTML_TAGS: Record<string, MdHtmlTag> = {
  br: { void: true, desc: '强制换行', eg: '第一段<br>第二段' },
  hr: { void: true, block: true, desc: '分隔线', eg: '<hr>' },
  b: { desc: '加粗', eg: '<b>重要</b>' },
  strong: { desc: '加粗（语义）', eg: '<strong>重要</strong>' },
  i: { desc: '斜体', eg: '<i>斜体</i>' },
  em: { desc: '斜体（语义）', eg: '<em>斜体</em>' },
  u: { desc: '下划线（Markdown 无对应语法）', eg: '<u>下划线</u>' },
  s: { desc: '删除线', eg: '<s>旧值</s>' },
  del: { desc: '删除线（语义）', eg: '<del>旧值</del>' },
  strike: { desc: '删除线（兼容标签）', eg: '<strike>旧值</strike>' },
  ins: { desc: '插入/下划线（Markdown 无对应语法）', eg: '<ins>新增</ins>' },
  mark: { desc: '高亮底色', eg: '<mark>划重点</mark>' },
  small: { desc: '小字', eg: '<small>注脚</small>' },
  big: { desc: '大字', eg: '<big>强调</big>' },
  sub: { desc: '下标（化学式）', eg: 'H<sub>2</sub>O' },
  sup: { desc: '上标 / 角标', eg: 'x<sup>2</sup>' },
  code: { desc: '行内代码', eg: '<code>npm ci</code>' },
  kbd: { desc: '按键（Markdown 无对应语法）', eg: '按 <kbd>Ctrl</kbd>+<kbd>S</kbd>' },
  abbr: { attrs: ['title'], style: false, desc: '缩写带悬停提示', eg: '<abbr title="Application Programming Interface">API</abbr>' },
  span: { desc: '行内改样式（字色/字号/底色）', eg: '<span style="color:#e11d48;font-size:18px">红字</span>' },
  font: { attrs: ['size', 'color', 'face'], style: false, desc: '老式字体标签（Word/CSDN 粘贴常见）', eg: '<font color="#39c5bb" size="5">绿大字</font>' },
  a: { attrs: ['href', 'title', 'target'], style: false, desc: '链接（target=_blank 自动补 rel）', eg: '<a href="https://example.com">外部站</a>' },
  ruby: { desc: '汉字注音', eg: '<ruby>晴<rt>qing</rt></ruby>' },
  rt: { desc: '注音正文（配 ruby）', eg: '<ruby>晴<rt>qing</rt></ruby>' },
  rp: { desc: '注音回落括号（配 ruby）', eg: '<ruby>晴<rp>(</rp><rt>qing</rt><rp>)</rp></ruby>' },
  p: { block: true, desc: '段落（可整段对齐）', eg: '<p style="text-align:right">右对齐落款</p>' },
  div: { attrs: ['align'], block: true, desc: '块容器（居中/留白）', eg: '<div align="center">整块居中</div>' },
  center: { block: true, desc: '整块居中（等价 div align=center）', eg: '<center>居中内容</center>' },
  blockquote: { block: true, desc: '引用块', eg: '<blockquote>引文</blockquote>' },
  pre: { block: true, desc: '保留空白的预格式文本', eg: '<pre>列  对  齐</pre>' },
  figure: { block: true, desc: '图 + 图注容器', eg: '<figure><img src="/media/x.png" width="320"><figcaption>图一</figcaption></figure>' },
  figcaption: { desc: '图注', eg: '<figure><img src="/media/x.png"><figcaption>图一</figcaption></figure>' },
  details: { block: true, attrs: ['open'], style: false, desc: '折叠块（不支持行内样式）', eg: '<details><summary>点开看答案</summary>答案在这里</details>' },
  summary: { desc: '折叠块标题行', eg: '<details><summary>点开看答案</summary>答案</details>' },
  table: { block: true, desc: '表格容器', eg: '<table><tr><td>甲</td><td>乙</td></tr></table>' },
  thead: { block: true, desc: '表头组', eg: '<table><thead><tr><th>项</th></tr></thead><tbody><tr><td>值</td></tr></tbody></table>' },
  tbody: { block: true, desc: '表体组', eg: '<table><tbody><tr><td>值</td></tr></tbody></table>' },
  tr: { desc: '表格行', eg: '<table><tr><td>甲</td></tr></table>' },
  td: { attrs: ['colspan', 'rowspan', 'align', 'width'], desc: '单元格', eg: '<td colspan="2" align="center">跨两列</td>' },
  th: { attrs: ['colspan', 'rowspan', 'align', 'width'], desc: '表头单元格', eg: '<th align="right">数值</th>' },
  caption: { desc: '表格标题', eg: '<table><caption>价格表</caption><tr><td>甲</td></tr></table>' },
  colgroup: { block: true, desc: '列组', eg: '<table><colgroup><col span="2" width="80"></colgroup><tr><td>甲</td></tr></table>' },
  col: { void: true, attrs: ['span', 'width', 'align'], desc: '列宽/对齐', eg: '<col span="2" width="80">' },
  img: { attrs: ['src', 'alt', 'width', 'height', 'align'], desc: '图片（含 Typora 的 zoom:67% 缩放）', eg: '<img src="/media/x.png" width="320">' },
  video: { attrs: ['src', 'poster', 'controls', 'width'], block: true, desc: '视频（src 限本站或 http(s)）', eg: '<video src="/media/a.mp4" controls width="640"></video>' },
  source: { void: true, attrs: ['src', 'type'], desc: '多格式视频源（配 video）', eg: '<video controls><source src="/media/a.mp4" type="video/mp4"></video>' },
}

function allowHtml(src: string, out: string[]): string {
  return src.replace(/<\/?([a-zA-Z][a-zA-Z0-9-]*)([^>]*)>/g, (match, name: string, raw: string) => {
    const tag = name.toLowerCase()
    const spec = MD_HTML_TAGS[tag]
    if (!spec) return match
    const closing = match.startsWith('</')
    const html = closing && !spec.void ? `</${tag}>` : rebuildOpenTag(tag, raw, spec)
    const sentinel = `[[pw-h${out.push(html) - 1}]]`
    // 块级标签两侧补空行，让它独占一段，回填时才不会被 <p> 包住
    return spec.block ? `\n\n${sentinel}\n\n` : sentinel
  })
}

function escapeText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function tocHtml(title: string, toc: TocItem[]): string {
  if (!toc.length) return ''
  const items = toc.map((i) => `<li class="toc-l${i.level}"><a href="#${i.id}">${escapeText(i.text)}</a></li>`).join('')
  return `<nav class="md-toc"><p class="md-toc-title">${escapeText(title)}</p><ul>${items}</ul></nav>`
}

/** 渲染 MD 并产出 TOC（SSG 构建期与客户端同构执行）。 */
export function renderMd(src: string): { html: string; toc: TocItem[] } {
  const toc: TocItem[] = []
  const titles: string[] = []
  const tags: string[] = []
  const widths = new Map<string, string>()
  // 占位符先换成哨兵 token：目录条目要等渲染收集完 heading 才可知。
  // 不能用 \u0000——markdown-it normalize 会把空字符替换为 \ufffd
  const pre = src.replace(TOC_LINE, (_m, t?: string) => {
    titles.push(t || '文章目录')
    return `[[pw-toc-${titles.length - 1}]]`
  })
  // 两步预转换都必须避开代码区，否则教程里写的 <img>/<br> 示例会被当成真标签处理
  const body = mapOutsideCode(
    mapOutsideCode(fixCjkEmphasis(pre), (s) => extractImgZoom(s, widths)),
    (s) => allowHtml(s, tags),
  )
  let html = createMd(toc).render(body)
  if (widths.size) {
    html = html.replace(/<img((?:[^>]*?))src="([^"]+)"([^>]*?)>/g, (m, a: string, u: string, b: string) =>
      widths.has(u) ? `<img${a}src="${u}"${b} style="width:${widths.get(u)};max-width:100%">` : m)
  }
  html = html.replace(/<p>\s*\[\[pw-toc-(\d+)\]\]\s*<\/p>/g, (_m, i) => tocHtml(titles[Number(i)], toc))
  html = html.replace(/\[\[pw-toc-(\d+)\]\]/g, (_m, i) => tocHtml(titles[Number(i)], toc))
  // 回填放行标签：跳过 <code>/<pre> 内部，让漏网的哨兵（如四空格缩进式代码块）
  // 按字面显示成 [[pw-hN]]，也不至于变成注入进代码示例里的真标签
  const putTags = (s: string) => s
    .replace(/<p>\s*\[\[pw-h(\d+)\]\]\s*<\/p>/g, (m, i) => tags[Number(i)] ?? m)
    .replace(/\[\[pw-h(\d+)\]\]/g, (m, i) => tags[Number(i)] ?? m)
  return { html: html.split(OUT_CODE_HTML).map((p, i) => (i % 2 === 1 ? p : putTags(p))).join(''), toc }
}

/**
 * 行内 Markdown 渲染（链接/加粗/斜体/行内代码），不产 `<p>` 包裹。
 * 供「一句话」型文案使用：首屏简介与 meta/og 描述同源，块级语法（标题/列表/代码块）在此不生效——
 * 这类文案同时是 og:description，本来也只该是一段话。
 */
export function renderMdInline(src: string): string {
  return createMd([]).renderInline(fixCjkEmphasis(src))
}

/** 行内 Markdown → 纯文本（去标签 + 反转义），供 meta/og description 这类不能带标记的位置。 */
export function mdInlineToText(src: string): string {
  return renderMdInline(src)
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
}
