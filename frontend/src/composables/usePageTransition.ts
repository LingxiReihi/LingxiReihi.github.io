/**
 * 路由切换过渡（anime.js v4，仅前台布局使用）：
 * out-in 模式，旧页快速淡出上移 → 新页淡入上浮，总时长 ~360ms。
 * prefers-reduced-motion 时直接放行 done()，零动画。
 * animejs 动态 import：不进 SSR/首屏 chunk（与 useReveal 共享同一懒 chunk）。
 *
 * done() 必须「无论如何都会到」。`<Transition mode="out-in">` 下旧页的 leave 不结束，新页就永不
 * 挂载，而 URL 已经变了 —— 表现是「点导航没反应，只有刷新才好」（本地注入失败 import 实测复现）。
 * 三条漏 done 的路都堵上：① import 失败（每天定时重建 + 只保留 3 个 release，旧 chunk 会被删；
 * 且模块表会记住失败，之后每次点都立刻失败）；② anime 靠 rAF 推进，后台标签页里 rAF 冻结，
 * onComplete 不来；③ 动画本身丢帧。
 */
const reduced = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** 幂等收尾 + 到点兜底：anime 的 onComplete 与定时器谁先到都只放行一次。 */
function settle(done: () => void, guardMs: number) {
  let spent = false
  const finish = () => {
    if (spent) return
    spent = true
    clearTimeout(timer)
    done()
  }
  const timer = setTimeout(finish, guardMs)
  return { finish, get spent() { return spent } }
}

export function usePageTransition() {
  async function onEnter(el: Element, done: () => void) {
    const node = el as HTMLElement
    // 收尾时把终态一并钉死：anime 只写了起始值（opacity 0）就被冻结的 rAF 撂在半路时，
    // 兜底放行会让新页挂载却看不见。这两条正是动画的终值，正常播完时重复赋同值无副作用。
    const s = settle(() => {
      node.style.opacity = '1'
      node.style.transform = ''
      done()
    }, 620)
    if (reduced()) return s.finish()
    try {
      const { animate } = await import('animejs')
      if (s.spent) return      // 兜底已放行，别再从零淡入把页面闪一下
      animate(el as HTMLElement, {
        opacity: [0, 1], translateY: [14, 0],
        duration: 220, ease: 'outQuad', onComplete: s.finish,
      })
    } catch {
      s.finish()
    }
  }
  async function onLeave(el: Element, done: () => void) {
    const s = settle(done, 540)
    if (reduced()) return s.finish()
    try {
      const { animate } = await import('animejs')
      if (s.spent) return
      animate(el as HTMLElement, {
        opacity: 0, translateY: -10,
        duration: 140, ease: 'inQuad', onComplete: s.finish,
      })
    } catch {
      s.finish()
    }
  }
  return { onEnter, onLeave }
}
