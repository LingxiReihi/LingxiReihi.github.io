import { onMounted, onServerPrefetch, ref } from 'vue'

import { readSeed, writeSeed } from './ssgState'

interface AsyncState<T> {
  data: ReturnType<typeof ref<T | null>>
  loading: ReturnType<typeof ref<boolean>>
  error: ReturnType<typeof ref<string | null>>
  retry: () => Promise<void>
}

const IS_SSG = (import.meta as any).env?.VITE_SSG === 'true'

/**
 * 数据屏三态（空/加载/错误）统一封装。
 * SSG 构建期在 onServerPrefetch 中拉取真实数据进 HTML（fail-soft），并写入
 * initialState[key]（若给 key）；客户端读回做种子 —— 首帧即真实数据、动画立播，
 * 后台静默复验不再切 loading，消除「默认数据闪现 → 整页换血重播动画」。
 */
export function useAsync<T>(fn: () => Promise<T>, key?: string): AsyncState<T> {
  const seed = !IS_SSG && key ? readSeed<T>(key) : undefined
  const data = ref((seed ?? null) as T | null) as ReturnType<typeof ref<T | null>>
  const loading = ref(seed === undefined) as ReturnType<typeof ref<boolean>>
  const error = ref<string | null>(null) as ReturnType<typeof ref<string | null>>

  async function run(background = false) {
    if (!background) {
      loading.value = true
      error.value = null
    }
    try {
      const next = await fn()
      data.value = next
      if (IS_SSG && key) writeSeed(key, next)
    } catch (e: any) {
      if (!background) error.value = e?.message || '加载失败'
    } finally {
      if (!background) loading.value = false
    }
  }

  if (IS_SSG) {
    const first = run()
    onServerPrefetch(() => first)
  } else {
    onMounted(() => (seed === undefined ? run() : void run(true)))
  }
  return { data, loading, error, retry: () => run() }
}
