import type { RouteRecordRaw } from 'vue-router'

const SiteLayout = () => import('@/layouts/SiteLayout.vue')

// 静态构建（VITE_STATIC=true）不打包后台：登录/管理页在只读镜像上没有意义
const STATIC = import.meta.env.VITE_STATIC === 'true'

const siteRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    component: SiteLayout,
    children: [
      { path: '', name: 'home', component: () => import('@/views/site/HomeView.vue') },
      { path: 'blog', name: 'blog', component: () => import('@/views/site/BlogView.vue') },
      { path: 'blog/:slug', name: 'post', component: () => import('@/views/site/BlogPostView.vue') },
      { path: 'models', name: 'models', component: () => import('@/views/site/ModelsView.vue') },
      { path: 'models/:slug', name: 'model-detail', component: () => import('@/views/site/ModelDetailView.vue') },
      { path: 'chats', name: 'chats', component: () => import('@/views/site/ChatsView.vue') },
      { path: 'chats/:id', name: 'chat-detail', component: () => import('@/views/site/ChatDetailView.vue') },
      { path: 'about', name: 'about', component: () => import('@/views/site/AboutView.vue') },
      { path: '404', name: 'notfound', component: () => import('@/views/site/NotFoundView.vue') },
    ],
  },
]

const catchall: RouteRecordRaw = {
  path: '/:pathMatch(.*)*', name: 'catchall', redirect: { name: 'notfound' },
}

export const routes: RouteRecordRaw[] = [...siteRoutes, catchall]

if (!STATIC) {
  const AdminLayout = () => import('@/layouts/AdminLayout.vue')
  const adminRoutes: RouteRecordRaw[] = [
    {
      path: '/admin/login', name: 'admin-login',
      component: () => import('@/views/admin/LoginView.vue'),
    },
    {
      path: '/admin',
      component: AdminLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'admin-root', redirect: { name: 'admin-dashboard' } },
        { path: 'dashboard', name: 'admin-dashboard', component: () => import('@/views/admin/DashboardView.vue') },
        { path: 'profile', name: 'admin-profile', component: () => import('@/views/admin/ProfileView.vue') },
        { path: 'content', name: 'admin-content', component: () => import('@/views/admin/ContentListView.vue') },
        { path: 'content/new', name: 'admin-content-new', component: () => import('@/views/admin/ContentEditView.vue'), meta: { perm: 'content:write' } },
        { path: 'content/:id/edit', name: 'admin-content-edit', component: () => import('@/views/admin/ContentEditView.vue'), meta: { perm: 'content:write' } },
        { path: 'content/:id/dashboard', name: 'admin-content-dashboard', component: () => import('@/views/admin/ContentDashboardView.vue') },
        { path: 'media', name: 'admin-media', component: () => import('@/views/admin/MediaLibraryView.vue') },
        { path: 'tags', name: 'admin-tags', component: () => import('@/views/admin/TagsView.vue'), meta: { perm: 'tag:manage' } },
        { path: 'columns', name: 'admin-columns', component: () => import('@/views/admin/ColumnsView.vue'), meta: { perm: 'column:manage' } },
        { path: 'announcements', name: 'admin-announcements', component: () => import('@/views/admin/AnnouncementsView.vue'), meta: { perm: 'announcement:manage' } },
        { path: 'logs', name: 'admin-logs', component: () => import('@/views/admin/LogsView.vue'), meta: { perm: 'log:view' } },
        { path: 'comments', name: 'admin-comments', component: () => import('@/views/admin/CommentsView.vue'), meta: { perm: 'comment:moderate' } },
        { path: 'settings', name: 'admin-settings', component: () => import('@/views/admin/SettingsView.vue'), meta: { perm: 'setting:manage' } },
        { path: 'seo', name: 'admin-seo', component: () => import('@/views/admin/SeoPanelView.vue'), meta: { perm: 'stats:view' } },
        { path: 'admins', name: 'admin-admins', component: () => import('@/views/admin/AdminsView.vue'), meta: { perm: 'admin:manage' } },
      ],
    },
  ]
  routes.splice(routes.length - 1, 0, ...adminRoutes)
}