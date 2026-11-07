import { useIntersectionObserver } from '@vueuse/core'
import { nextTick, type Ref } from 'vue'

/** 触底加载：哨兵进入视口前 margin 像素就预取下一批。
 *
 *  IntersectionObserver 只在「状态变化」时回调 —— 筛选后列表变短、哨兵一直可见时
 *  不会再触发，所以每批落地后要调一次 `notifyLoaded()`，按 rect 再判一次把首屏填满。
 */
export function useInfiniteScroll(
  sentinel: Ref<HTMLElement | null>,
  opts: { canLoad: () => boolean; load: () => void; margin?: number },
) {
  const margin = opts.margin ?? 300

  function nearViewport() {
    const el = sentinel.value
    if (!el) return false
    // 滚动发生在 main 内部，用它的底边判断比 window 更准
    const root = el.closest('main') ?? document.documentElement
    return el.getBoundingClientRect().top <= root.getBoundingClientRect().bottom + margin
  }

  function trigger() {
    if (opts.canLoad()) opts.load()
  }

  useIntersectionObserver(
    sentinel,
    ([entry]) => { if (entry?.isIntersecting) trigger() },
    { rootMargin: `0px 0px ${margin}px 0px` },
  )

  async function notifyLoaded() {
    await nextTick()
    if (opts.canLoad() && nearViewport()) trigger()
  }

  return { notifyLoaded }
}
