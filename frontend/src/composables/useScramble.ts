/**
 * 数字乱码解码动画（rAF 自驱，只动文本节点的 nodeValue）。
 *
 * 为什么不用 anime 的 scrambleText：它按 innerHTML 逐帧重写，会把 Vue 渲染 `{{ label }}`
 * 时持有的那个文本节点换成新节点 —— 之后在站点设置里改了站名或导航名，Vue 的补丁写到游离
 * 节点上，顶栏就永远停在旧文案。写 nodeValue 则始终是同一个节点，两边互不抢所有权。
 *
 * 为什么用 rAF 而不是 anime 驱动补间：只是改一行文本，rAF 更直白、也更容易当场验；
 * 实测过 anime 的 ticker 在标签页未真正绘制时不推进（DOM 目标 animate 300ms 后 opacity 仍是 0），
 * 面板真正显示后它又会正常逐帧推进 —— 也就是说那条路能不能验取决于标签页状态。
 * 卡片入场、顶栏逐字符跳动等仍用 anime。
 */
type Owner = { cancel: () => void }

const owners = new WeakMap<Text, Owner>()

const digits = () => String((Math.random() * 10) | 0)

export function decodeText(el: HTMLElement | null | undefined, opt: { delay?: number; duration?: number } = {}) {
  if (typeof window === 'undefined' || !el) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  // v-html 渲染的行内 Markdown 会把一句话拆成多个文本节点（链接前后各一段），
  // 只取 firstChild 会漏掉链接之后的文字、整行动画也只剩一个字符；故遍历全部后代文本节点。
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  for (let n = walker.nextNode(); n; n = walker.nextNode()) decodeNode(n as Text, opt)
}

function decodeNode(node: Text, opt: { delay?: number; duration?: number }) {
  // 必须先让上一轮收尾再读原文：否则读到的是它留下的乱码数字，会被当成「原文案」永久还原
  owners.get(node)?.cancel()
  const text = node.nodeValue ?? ''
  if (!text.trim()) return

  const owner: Owner = { cancel: () => {} }
  owners.set(node, owner)
  const delay = opt.delay ?? 0
  const duration = opt.duration ?? 520

  const restore = () => {
    node.nodeValue = text
    if (owners.get(node) === owner) owners.delete(node)
  }
  owner.cancel = restore

  const startAt = performance.now() + delay
  const frame = (now: number) => {
    if (owners.get(node) !== owner) return          // 期间已被新的解码接管
    const p = Math.min(1, Math.max(0, (now - startAt) / duration))
    const shown = Math.floor(p * text.length)
    let out = ''
    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i]
      out += i < shown || ch === ' ' ? ch : digits()
    }
    node.nodeValue = out
    if (p < 1) requestAnimationFrame(frame)
    else restore()
  }
  requestAnimationFrame(frame)
}
