import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { SiteConfig } from '@/api/types'
import { readSeed } from '@/composables/ssgState'

export const useSiteStore = defineStore('site', () => {
  // 直接从 SSG 种子起值：客户端首帧就该拿到真实站名，不等接口回来
  const config = ref<SiteConfig | null>(readSeed<SiteConfig>('site-config') ?? null)

  async function load(fetcher: () => Promise<SiteConfig>) {
    if (config.value) return config.value
    try {
      config.value = await fetcher()
    } catch {
      config.value = config.value ?? fallback
    }
    return config.value
  }

  /** 后台保存设置后强制重取，避免同标签页前台仍显示旧值 */
  async function reload(fetcher: () => Promise<SiteConfig>) {
    config.value = null
    return load(fetcher)
  }

  return { config, load, reload }
})

/** 站点名（响应式，SSR 安全）。 */
export function useSiteTitle() {
  const site = useSiteStore()
  return computed(() => (site.config ?? fallback).site.title)
}

export const fallback: SiteConfig = {
  site: { title: 'personal-web', subtitle: '', description: '', favicon: '', icon: '' },
  nav_items: [
    { label: '首页', path: '/', visible: true, order: 1 },
    { label: '博客', path: '/blog', visible: true, order: 2 },
    { label: '模型', path: '/models', visible: true, order: 3 },
    { label: '杂谈', path: '/chats', visible: true, order: 4 },
    { label: '关于', path: '/about', visible: true, order: 5 },
  ],
  footer: { links: [], copyright: '', beian: '' },
  profile: { nickname: '', avatar: '', signature: '', social_links: [] },
}
