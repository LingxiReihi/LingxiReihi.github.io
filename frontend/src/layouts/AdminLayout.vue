<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  NConfigProvider, NDialogProvider, NLayout, NLayoutContent, NLayoutSider,
  NMessageProvider, NMenu, type MenuOption,
} from 'naive-ui'

import AdminIcon from '@/components/admin/AdminIcon.vue'
import type { IconName } from '@/components/admin/icons'
import { useAdminTheme } from '@/composables/useAdminTheme'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import AnnouncementGate from '../views/admin/AnnouncementGate.vue'

const theme = useThemeStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { naiveTheme, themeOverrides } = useAdminTheme()

const collapsed = ref(true)
const icon = (name: IconName) => () => h(AdminIcon, { name, size: 16 })
// perm 缺省 = 登录即可见；否则按服务端回报的权限集合过滤（super 隐式全有）
type MenuEntry = MenuOption & { path: string; perm?: string }
const ALL_ITEMS: MenuEntry[] = [
  { label: '仪表盘', key: 'admin-dashboard', path: '/admin/dashboard', icon: icon('dashboard') },
  { label: '我的资料', key: 'admin-profile', path: '/admin/profile', icon: icon('profile') },
  { label: '内容管理', key: 'admin-content', path: '/admin/content', icon: icon('content') },
  { label: '素材库', key: 'admin-media', path: '/admin/media', icon: icon('media') },
  { label: '标签管理', key: 'admin-tags', path: '/admin/tags', icon: icon('tag'), perm: 'tag:manage' },
  { label: '栏目管理', key: 'admin-columns', path: '/admin/columns', icon: icon('column'), perm: 'column:manage' },
  { label: '更新公告', key: 'admin-announcements', path: '/admin/announcements', icon: icon('announce'), perm: 'announcement:manage' },
  { label: '评论管理', key: 'admin-comments', path: '/admin/comments', icon: icon('comment'), perm: 'comment:moderate' },
  { label: '站点设置', key: 'admin-settings', path: '/admin/settings', icon: icon('setting'), perm: 'setting:manage' },
  { label: 'SEO 面板', key: 'admin-seo', path: '/admin/seo', icon: icon('seo'), perm: 'stats:view' },
  { label: '日志', key: 'admin-logs', path: '/admin/logs', icon: icon('log'), perm: 'log:view' },
  { label: '管理员', key: 'admin-admins', path: '/admin/admins', icon: icon('team'), perm: 'admin:manage' },
]

const menuItems = computed(() => ALL_ITEMS.filter((m) => !m.perm || auth.can(m.perm)))

const activeKey = computed(() => {
  const name = String(route.name ?? '')
  if (name.startsWith('admin-content')) return 'admin-content'
  return name
})

function onMenuSelect(key: string) {
  const item = menuItems.value.find((m) => m.key === key)
  if (item) router.push(item.path)
}

async function logout() {
  await auth.logout()
  router.push({ name: 'admin-login' })
}
</script>

<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <div class="admin-root">
          <AnnouncementGate />
          <n-layout has-sider style="height: 100vh">
            <n-layout-sider
              v-model:collapsed="collapsed"
              bordered :width="240" collapse-mode="width" :collapsed-width="64" show-trigger
              content-style="display: flex; flex-direction: column; height: 100%"
            >
              <div class="flex h-14 shrink-0 items-center gap-2 border-b border-line px-5">
                <RouterLink v-if="!collapsed" to="/admin/dashboard" class="no-underline whitespace-nowrap">
                  <span class="font-mono text-[13px] font-semibold tracking-[0.18em] text-brand">ADMIN</span>
                  <span class="ml-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">管理后台</span>
                </RouterLink>
                <RouterLink v-else to="/admin/dashboard" class="no-underline font-mono text-sm font-semibold tracking-[0.1em] text-brand">A</RouterLink>
              </div>
              <n-menu
                :value="activeKey" :options="menuItems" :collapsed="collapsed" :collapsed-width="64"
                :collapsed-icon-size="20" style="flex: 1" @update:value="onMenuSelect"
              />
              <div v-if="!collapsed" class="flex shrink-0 items-center gap-2 border-t border-line p-3">
                <span class="truncate font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">{{ auth.user?.nickname || auth.user?.username }}</span>
                <button
                  class="ml-auto grid h-7 w-7 place-items-center border border-line text-[12px] text-ink-2 transition-colors hover:border-brand hover:text-brand"
                  :title="theme.mode === 'dark' ? '切换到浅色' : '切换到深色'" @click="theme.toggle()"
                ><AdminIcon :name="theme.mode === 'dark' ? 'sun' : 'moon'" :size="14" /></button>
                <button
                  class="border border-line px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-2 transition-colors hover:border-brand hover:text-brand"
                  @click="logout">退出</button>
              </div>
              <div v-else class="flex shrink-0 flex-col items-center gap-2 border-t border-line p-2">
                <button
                  class="grid h-8 w-8 place-items-center border border-line text-base leading-none transition-colors hover:border-brand"
                  :title="theme.mode === 'dark' ? '切换到浅色' : '切换到深色'" @click="theme.toggle()"><AdminIcon :name="theme.mode === 'dark' ? 'sun' : 'moon'" :size="14" /></button>
                <button
                  class="grid h-8 w-8 place-items-center border border-line font-mono text-[10px] text-ink-2 transition-colors hover:border-brand hover:text-brand"
                  title="退出登录" @click="logout">退</button>
              </div>
            </n-layout-sider>
            <n-layout-content content-style="min-height: 100%">
              <div class="admin-view hud-grid min-h-full p-6"><RouterView /></div>
            </n-layout-content>
          </n-layout>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
/* 表格：表头等宽大写、单元格数字等宽对齐、列间加细竖线 */
.admin-view :deep(.n-data-table th) {
  font-family: var(--font-hud);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.admin-view :deep(.n-data-table td) {
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
}
.admin-view :deep(.n-data-table th),
.admin-view :deep(.n-data-table td) {
  border-right: 1px solid var(--c-border);
}
.admin-view :deep(.n-data-table th:last-child),
.admin-view :deep(.n-data-table td:last-child) {
  border-right: 0;
}

/* 页标题统一带 HUD 前缀，省得 16 个页面各写一遍 */
.admin-view :deep(h1)::before {
  content: '//';
  margin-right: 0.55em;
  font-family: var(--font-hud);
  font-size: 0.72em;
  font-weight: 500;
  color: var(--c-primary);
  vertical-align: 0.12em;
}
</style>
