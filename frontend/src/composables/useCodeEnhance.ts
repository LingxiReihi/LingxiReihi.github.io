/**
 * 代码块增强（CSDN 风格）：语言标签 + 复制按钮顶栏 + Shiki 多语言关键字高亮（双主题）。
 * 在 prose 渲染完成后调用 enhanceCodeBlocks(root)。
 */
let shikiLoader: Promise<typeof import('shiki')> | null = null
function loadShiki() {
  shikiLoader ??= import('shiki')
  return shikiLoader
}

/** fence info 归一化：'C++'→cpp、'C#'→csharp、'py'→python…（Shiki 语言 id 全小写无符号） */
const ALIASES: Record<string, string> = {
  'c++': 'cpp', 'c#': 'csharp', 'f#': 'fsharp', 'objective-c': 'objectivec', objc: 'objectivec',
  js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
  py: 'python', rb: 'ruby', rs: 'rust', golang: 'go', 'c-+': 'cpp', 'c-#': 'csharp',
  sh: 'shell', bash: 'shell', zsh: 'shell', console: 'shell', shellsession: 'shell',
  yml: 'yaml', md: 'markdown', text: 'text', plain: 'text', docker: 'dockerfile',
  ps: 'powershell', pwsh: 'powershell', 'objective c': 'objectivec',
}
function normalizeLang(raw: string): string {
  const l = (raw || '').trim().toLowerCase().replace(/\s+/g, '')
  return ALIASES[l] ?? (/^[a-z][\w.-]*$/.test(l) ? l : 'text')
}

/** 展示名（官方写法）；未收录的显示首字母大写 */
const LANG_LABELS: Record<string, string> = {
  bash: 'Shell', c: 'C', cpp: 'C++', csharp: 'C#', css: 'CSS', dart: 'Dart',
  dockerfile: 'Dockerfile', fsharp: 'F#', git: 'Git', go: 'Go', graphql: 'GraphQL',
  html: 'HTML', java: 'Java', javascript: 'JavaScript', json: 'JSON', jsx: 'JSX',
  kotlin: 'Kotlin', latex: 'LaTeX', lua: 'Lua', markdown: 'Markdown', nginx: 'Nginx',
  objectivec: 'Objective-C', php: 'PHP', plaintext: 'Text', powershell: 'PowerShell',
  python: 'Python', r: 'R', ruby: 'Ruby', rust: 'Rust', sass: 'Sass', scss: 'SCSS',
  shell: 'Shell', shellscript: 'Shell', sql: 'SQL', swift: 'Swift', toml: 'TOML',
  typescript: 'TypeScript', tsx: 'TSX', vue: 'Vue', wasm: 'Wasm', xml: 'XML',
  yaml: 'YAML', zig: 'Zig', text: 'Text',
}
function displayLabel(id: string): string {
  return LANG_LABELS[id] ?? (id ? id[0].toUpperCase() + id.slice(1) : 'Text')
}

/** 复制：Clipboard API 失败（内嵌浏览器沙箱/非安全上下文）时回落 execCommand */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch { /* fall through */ }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.cssText = 'position:fixed;top:0;left:-9999px;opacity:0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  } catch {
    return false
  }
}

export async function enhanceCodeBlocks(root: HTMLElement | Document) {
  const pres = Array.from(root.querySelectorAll<HTMLElement>('pre.code-block'))
  for (const pre of pres) {
    if (pre.dataset.enhanced) continue
    pre.dataset.enhanced = '1'
    const code = pre.querySelector('code')
    // 捕获 language- 后全部非空白字符（含 + # . 等符号）
    const rawLang = /language-([^\s"]+)/.exec(code?.className ?? '')?.[1] ?? ''
    const lang = normalizeLang(rawLang)
    const source = code?.textContent ?? ''
    // 只剥复制内容的尾部换行，不动 source 本身（Shiki 高亮仍按原样渲染）。
    // markdown-it 的 fence token 会带上围栏内每一行的换行，闭合 ``` 前一个空行就是两个 \n，
    // 复制出来末尾多出行；整块只有空行时保留原文，避免出现「已复制 ✓」却复制了个空。
    const copySource = source.replace(/\n+$/, '') || source

    const card = document.createElement('div')
    card.className = 'code-card'
    const head = document.createElement('div')
    head.className = 'code-head'
    const langEl = document.createElement('span')
    langEl.className = 'code-lang'
    langEl.textContent = displayLabel(lang)
    const copyBtn = document.createElement('button')
    copyBtn.type = 'button'
    copyBtn.className = 'copy-btn'
    copyBtn.textContent = '复制'
    copyBtn.addEventListener('click', async () => {
      copyBtn.textContent = '…'
      copyBtn.disabled = true
      copyBtn.textContent = (await copyText(copySource)) ? '已复制 ✓' : '复制失败'
      copyBtn.disabled = false
      setTimeout(() => (copyBtn.textContent = '复制'), 2000)
    })
    head.append(langEl, copyBtn)
    pre.parentElement?.insertBefore(card, pre)
    card.append(head)

    // Shiki 高亮；语言未知回落 text，仍保留卡片结构
    try {
      const { codeToHtml } = await loadShiki()
      let out: string
      try {
        out = await codeToHtml(source, {
          lang, themes: { light: 'github-light', dark: 'github-dark' }, defaultColor: false,
        })
      } catch {
        out = await codeToHtml(source, {
          lang: 'text', themes: { light: 'github-light', dark: 'github-dark' }, defaultColor: false,
        })
      }
      const tmp = document.createElement('div')
      tmp.innerHTML = out
      const highlighted = tmp.querySelector('pre')
      if (highlighted) {
        highlighted.classList.add('code-body')
        card.append(highlighted)
        pre.remove()
        continue
      }
    } catch { /* shiki 加载失败：保留纯文本 */ }
    card.append(pre)
  }
}
