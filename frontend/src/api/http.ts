import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

import { staticApi } from './static'

interface Envelope<T = unknown> {
  code: number
  message: string
  data: T
}

export class ApiError extends Error {
  code: number
  data?: unknown

  constructor(code: number, message: string, data?: unknown) {
    super(message)
    this.code = code
    this.data = data
  }
}

const IS_SSG = (import.meta as any).env?.VITE_SSG === 'true'
const STATIC = (import.meta as any).env?.VITE_STATIC === 'true'

export const http = axios.create({
  // SSG 构建期在 Node 中运行，需绝对地址（rebuild 脚本注入 SSG_API_BASE）
  baseURL: IS_SSG
    ? ((import.meta as any).env?.VITE_SSG_API_BASE || 'http://127.0.0.1:8000/api/v1')
    : '/api/v1',
  timeout: 20000,
})

// ── token 存取（SSR 构建期无 window） ──
export const tokenStorage = {
  get refresh(): string | null {
    if (IS_SSG) return null
    return localStorage.getItem('pw-refresh') ?? sessionStorage.getItem('pw-refresh')
  },
  set(pair: { refresh_token: string; remember?: boolean }) {
    if (IS_SSG) return
    tokenStorage.clear()
    const store = pair.remember ? localStorage : sessionStorage
    store.setItem('pw-refresh', pair.refresh_token)
  },
  clear() {
    if (IS_SSG) return
    localStorage.removeItem('pw-refresh')
    sessionStorage.removeItem('pw-refresh')
  },
}

let accessToken: string | null = null
export function setAccessToken(t: string | null) {
  accessToken = t
}

type Retriable = AxiosRequestConfig & { _retried?: boolean; _noAuth?: boolean }

let refreshing: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  const refresh = tokenStorage.refresh
  if (!refresh) return null
  const remember = !!localStorage.getItem('pw-refresh')
  try {
    const r = await axios.post<Envelope<{ access_token: string; refresh_token: string }>>(
      '/api/v1/admin/auth/refresh',
      { refresh_token: refresh },
    )
    if (r.data.code !== 0) return null
    const d = r.data.data
    tokenStorage.set({ refresh_token: d.refresh_token, remember })
    return d.access_token
  } catch {
    return null
  }
}

// 落地来源：浏览器只在真正的跨文档导航时写 document.referrer，SPA 内 pushState 不改它，
// 所以一次访问里的后续请求都保留最初的来源。SSG 构建期跑在 Node 里没有 document。
const LANDING_REFERRER = typeof document === 'undefined' ? '' : document.referrer

http.interceptors.request.use((config) => {
  if (accessToken && !(config as Retriable)._noAuth) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  // 同源 XHR 自带的 referer 恒等于本页 URL，后端拿不到真来源，只能由前端上报
  if (LANDING_REFERRER) config.headers['X-Page-Referrer'] = LANDING_REFERRER
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<Envelope>) => {
    const config = error.config as Retriable | undefined
    const envelope = error.response?.data
    const isAuthPath = config?.url?.includes('/auth/login') || config?.url?.includes('/auth/refresh')
    if (envelope && envelope.code === 40100 && config && !config._retried && !isAuthPath && !config._noAuth) {
      config._retried = true
      refreshing = refreshing ?? doRefresh().finally(() => (refreshing = null))
      const newToken = await refreshing
      if (newToken) {
        setAccessToken(newToken)
        return http(config)
      }
      setAccessToken(null)
      tokenStorage.clear()
      // 通知路由层跳登录（M5 接线 router）
      window.dispatchEvent(new CustomEvent('pw:unauthorized'))
    }
    return Promise.reject(error)
  },
)

/** 剥壳调用：成功返回 data，业务错误抛 ApiError。静态构建下改读本地快照。 */
export async function api<T>(config: AxiosRequestConfig): Promise<T> {
  if (STATIC) return staticApi<T>({ method: 'get', ...config })
  try {
    const r = await http.request<Envelope<T>>({ method: 'get', ...config })
    if (r.data.code !== 0) throw new ApiError(r.data.code, r.data.message, r.data.data)
    return r.data.data
  } catch (e) {
    if (e instanceof ApiError) throw e
    const ax = e as AxiosError<Envelope>
    if (ax.response?.data && typeof ax.response.data.code === 'number') {
      throw new ApiError(ax.response.data.code, ax.response.data.message, ax.response.data.data)
    }
    throw new ApiError(-1, '网络错误，请稍后重试')
  }
}
