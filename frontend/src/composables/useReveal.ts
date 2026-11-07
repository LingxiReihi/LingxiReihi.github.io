import { onBeforeUnmount, onMounted } from 'vue'

/**
 * 列表卡片入场动画（anime.js v4，仅客户端）：
 * 元素带 data-reveal，进入视口时淡入+上移，同批交错 60ms。
 * prefers-reduced-motion 或 IO 不可用时完全不介入（元素保持可见）。
 * animejs 动态 import：不进 SSR 路径，也不进首屏 chunk。
 */
export function useReveal(rootSelector = 'main') {
  let io: IntersectionObserver | null = null
  const seen = new WeakSet<Element>()

  async function play(entries: IntersectionObserverEntry[]) {
    const targets = entries.map((e) => e.target as HTMLElement)
    targets.forEach((t) => io?.unobserve(t))
    const { animate, stagger } = await import('animejs')
    animate(targets, {
      opacity: [0, 1],
      translateY: [26, 0],
      duration: 520,
      ease: 'outQuad',
      delay: stagger(60),
    })
  }

  function refresh() {
    if (!io) return
    document.querySelectorAll<HTMLElement>(`${rootSelector} [data-reveal]`).forEach((el) => {
      if (seen.has(el)) return
      seen.add(el)
      el.style.opacity = '0'
      io!.observe(el)
    })
  }

  onMounted(() => {
    if (typeof IntersectionObserver === 'undefined') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    io = new IntersectionObserver((entries) => {
      const vis = entries.filter((e) => e.isIntersecting)
      if (vis.length) play(vis)
    }, { rootMargin: '0px 0px -5% 0px' })
    refresh()
  })

  onBeforeUnmount(() => io?.disconnect())

  return { refresh }
}
