import type { ViteSSGContext } from 'vite-ssg'

/**
 * vite-ssg initialState 桥：SSG 构建期组件把已取数据写入（随 HTML 序列化），
 * 客户端启动时读回做种子 —— 消除「默认数据闪现 → API 回来后整页换血重播动画」。
 *
 * 陷阱：多路由构建时 vite-ssg 在 setup 回调之后会把 context.initialState 换成
 * route.meta.state（常为新空对象），setup 里绑定的引用会成孤儿 ——
 * 因此服务端写入先进 collected 暂存，onSSRAppRendered 时再并入真正的 appCtx.initialState。
 */
let store: Record<string, unknown> = {}
let collected: Record<string, unknown> = {}

export function bindInitialState(obj: ViteSSGContext['initialState']) {
  store = obj as Record<string, unknown>
}

export function resetCollected() {
  collected = {}
}

export function readSeed<T>(key: string): T | undefined {
  return store[key] as T | undefined
}

export function writeSeed(key: string, value: unknown) {
  store[key] = value
  collected[key] = value
}

/** 注册进 vite-ssg onSSRAppRendered：渲染完成后把 collected 合并进真正被序列化的对象 */
export function flushCollected(getTarget: () => Record<string, unknown> | undefined) {
  const t = getTarget()
  if (t) Object.assign(t, collected)
}
