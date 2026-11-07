import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, setAccessToken, tokenStorage } from '@/api/http'
import type { AdminUser, TokenPair } from '@/api/types'
import type { AxiosRequestConfig } from 'axios'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AdminUser | null>(null)
  const ready = ref(false) // 是否已完成 me 探测

  const isAuthed = () => !!user.value
  const isSuper = computed(() => !!user.value?.is_super)
  const perms = computed(() => new Set(user.value?.permissions ?? []))

  /** 只用于菜单/按钮显隐；逐条「能不能改这条内容」由服务端在列表里回报（can_edit）。 */
  const can = (perm: string) => isSuper.value || perms.value.has(perm)

  async function login(username: string, password: string, remember: boolean) {
    const d = await api<TokenPair>({
      url: '/admin/auth/login', method: 'post',
      data: { username, password, remember },
    } as AxiosRequestConfig & { _noAuth?: boolean })
    setAccessToken(d.access_token)
    tokenStorage.set({ refresh_token: d.refresh_token, remember })
    user.value = d.user ?? null
    ready.value = true
    return d
  }

  async function logout() {
    try {
      await api({ url: '/admin/auth/logout', method: 'post' })
    } catch { /* 忽略：本地清理优先 */ }
    setAccessToken(null)
    tokenStorage.clear()
    user.value = null
  }

  /** 应用启动/守卫首次进入 admin 时尝试恢复会话。 */
  async function restore(): Promise<boolean> {
    if (user.value) return true
    if (tokenStorage.refresh) {
      // 走一次 refresh 拿 access（http 拦截器兜底后续 401）
      try {
        const d = await api<{ access_token: string; refresh_token: string }>({
          url: '/admin/auth/refresh', method: 'post',
          data: { refresh_token: tokenStorage.refresh },
        } as AxiosRequestConfig & { _noAuth?: boolean })
        setAccessToken(d.access_token)
        tokenStorage.set({ refresh_token: d.refresh_token, remember: !!localStorage.getItem('pw-refresh') })
      } catch {
        setAccessToken(null)
        tokenStorage.clear()
      }
    }
    try {
      user.value = await api<AdminUser>({ url: '/admin/auth/me' })
    } catch {
      user.value = null
    }
    ready.value = true
    return !!user.value
  }

  return { user, ready, isAuthed, isSuper, perms, can, login, logout, restore }
})
