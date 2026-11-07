// vite-ssg 入口：dev 与 build 共用（docs/frontend-design.md §10.1）
import './style.css'

import { createPinia } from 'pinia'
import { ViteSSG } from 'vite-ssg'

import App from './App.vue'
import { routes } from './router/routes'
import { useAuthStore } from './stores/auth'
import { useThemeStore } from './stores/theme'
import { bindInitialState, flushCollected, resetCollected } from './composables/ssgState'

const IS_SSG = (import.meta as any).env?.VITE_SSG === 'true'

export const createApp = ViteSSG(
  App,
  {
    routes,
    base: import.meta.env.BASE_URL,
    scrollBehavior: (to, _from, saved) =>
      saved ?? (to.hash ? { el: to.hash, behavior: 'smooth' } : { top: 0 }),
  },
  (ctx) => {
    const { app, router, isClient, initialState } = ctx
    bindInitialState(initialState)
    if (!isClient) {
      // 服务端：每路由渲染前清暂存，渲染完成后并入真正序列化的 context.initialState
      // （vite-ssg 在 setup 之后会把它换成 route.meta.state，必须闭包取新值）
      resetCollected()
      ctx.onSSRAppRendered(() => flushCollected(() => ctx.initialState as Record<string, unknown>))
    }
    const pinia = createPinia()
    app.use(pinia)
    if (!isClient || IS_SSG) return

    // 主题初始化（深默认）
    useThemeStore().init()

    // 路由守卫：/admin 需登录；meta.perm 再按权限点放行
    router.beforeEach(async (to) => {
      if (!to.matched.some((r) => r.meta.requiresAuth)) return true
      const auth = useAuthStore()
      if (!auth.ready) await auth.restore()
      if (!auth.isAuthed()) return { name: 'admin-login', query: { redirect: to.fullPath } }
      const need = to.matched.map((r) => r.meta.perm).filter(Boolean) as string[]
      if (need.some((p) => !auth.can(p))) return { name: 'admin-dashboard' }
      return true
    })
    // 懒加载路由 chunk 拉不到（发布后旧 release 被清、网络抖动）时，Vue Router 只会静默放弃这次
    // 导航 —— 用户看到的就是「点了没反应」。这种失败在内存里重试不了（模块表记住了失败），
    // 所以直接把目标路径整页加载过去；同一地址连续失败就收手，避免重建窗口里来回刷。
    router.onError((err, to) => {
      const msg = String((err as Error)?.message ?? err)
      if (!/dynamically imported module|module script failed|Failed to fetch/i.test(msg)) return
      const key = 'pw:chunk-failed'
      if (sessionStorage.getItem(key) === to.fullPath) return
      sessionStorage.setItem(key, to.fullPath)
      const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '')
      window.location.assign(base + to.fullPath)
    })
    // 401 单飞刷新失败 → 跳登录
    window.addEventListener('pw:unauthorized', () => {
      const current = router.currentRoute.value
      if (current.path.startsWith('/admin') && current.name !== 'admin-login') {
        router.push({ name: 'admin-login', query: { redirect: current.fullPath } })
      }
    })
  },
)
