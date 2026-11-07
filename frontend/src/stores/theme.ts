import { defineStore } from 'pinia'
import { ref } from 'vue'

const KEY = 'pw-theme'

export const useThemeStore = defineStore('theme', () => {
  // 主题基调是暗色 HUD（仪器面板），亮色作为可切换的备用
  const mode = ref<'dark' | 'light'>('dark')

  function apply() {
    document.documentElement.classList.toggle('light', mode.value === 'light')
  }

  function init() {
    if (typeof window === 'undefined') return
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') mode.value = saved
    apply()
  }

  function toggle() {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem(KEY, mode.value)
    apply()
  }

  return { mode, init, toggle, apply }
})
