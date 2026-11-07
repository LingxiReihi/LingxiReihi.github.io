<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton, NCheckbox, NDataTable, NInput, NModal, NPopconfirm, NSelect, NTag, useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import { adminAdminsApi, adminColumnsApi } from '@/api'
import type { AdminAccount, ColumnOut, ContentType, GrantOut } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const message = useMessage()
const auth = useAuthStore()

/** 权限点白名单（与后端 app/core/permissions.py 同步；栏目级只允许 SCOPED 三项） */
const PERMS: { key: string; label: string; hint: string; scoped: boolean }[] = [
  { key: 'content:write', label: '内容管理', hint: '新建/编辑自己上传的内容', scoped: true },
  { key: 'content:delete', label: '删除内容', hint: '删除自己上传的内容', scoped: true },
  { key: 'comment:moderate', label: '评论审核', hint: '全站待审队列（不按归属隔离）', scoped: false },
  { key: 'media:write', label: '素材上传', hint: '上传图片/模型/工程包', scoped: false },
  { key: 'media:delete', label: '素材删除', hint: '仅自己上传且未被引用的', scoped: false },
  { key: 'column:manage', label: '栏目管理', hint: '栏目改名/删除', scoped: true },
  { key: 'tag:manage', label: '标签管理', hint: '标签增删改', scoped: false },
  { key: 'setting:manage', label: '站点设置', hint: '站点信息/导航/页脚等全站配置', scoped: false },
  { key: 'announcement:manage', label: '更新公告', hint: '公告的新建/编辑/删除（读全员开放）', scoped: false },
  { key: 'stats:view', label: '数据看板', hint: '访问统计与 SEO 面板（只读）', scoped: false },
  { key: 'log:view', label: '运行日志', hint: '后台日志查看与导出', scoped: false },
  { key: 'admin:manage', label: '管理员账号', hint: '建号与授权（仍不能造 super）', scoped: false },
]
const TYPE_LABEL: Record<ContentType, string> = { article: '博客', model: '模型', chat: '杂谈' }

const items = ref<AdminAccount[]>([])
const loading = ref(false)
const columns = ref<ColumnOut[]>([])

async function load() {
  loading.value = true
  try {
    const [a, ...cols] = await Promise.all([
      adminAdminsApi.list(),
      ...(['article', 'model', 'chat'] as ContentType[]).map((t) => adminColumnsApi.list(t)),
    ])
    items.value = a.items
    columns.value = cols.flatMap((c) => c.items)
  } catch (e: any) {
    message.error(e?.message || '账号加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const canOffer = (perm: string) => auth.isSuper || (perm !== 'admin:manage' && auth.can(perm))

const columnOptions = computed<SelectOption[]>(() =>
  columns.value.map((c) => ({ label: `[${TYPE_LABEL[c.type]}] ${c.name}`, value: c.id })))

// ── 新建账号 ──
type PermRow = { permission: string; label: string; scoped: boolean; global: boolean; columnIds: number[] }
const blankRows = (): PermRow[] => PERMS.map((p) => ({
  permission: p.key, label: p.label, scoped: p.scoped, global: false, columnIds: [],
}))
const rowsToGrants = (rows: PermRow[]): GrantOut[] => rows.flatMap<GrantOut>((r) =>
  r.global ? [{ permission: r.permission, column_id: null }]
    : r.columnIds.map((id) => ({ permission: r.permission, column_id: id })))
const grantsToRows = (grants: GrantOut[], base = blankRows()): PermRow[] => {
  for (const g of grants) {
    const row = base.find((r) => r.permission === g.permission)
    if (!row) continue
    if (g.column_id === null) row.global = true
    else if (!row.columnIds.includes(g.column_id)) row.columnIds.push(g.column_id)
  }
  return base
}

// 「全局」与「指定栏目」是二选一，且以后一次操作为准：勾全局即清空该行已选栏目（留着也只会
// 被 rowsToGrants 静默丢掉），选了栏目即取消全局。新建与改权限两个弹窗共用这一对处理函数。
function setGlobal(r: PermRow, v: boolean) {
  r.global = v
  if (v) r.columnIds = []
}
function setColumns(r: PermRow, ids: number[]) {
  r.columnIds = ids
  if (ids.length) r.global = false
}
const scopeOf = (r: PermRow) =>
  r.global ? '全局' : r.columnIds.length ? `指定 ${r.columnIds.length} 个栏目` : '未授'

const createOpen = ref(false)
const createForm = ref({ username: '', nickname: '', email: '', password: '', note: '' })
const createRows = ref<PermRow[]>(blankRows())
const submitting = ref(false)

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function openCreate() {
  createForm.value = { username: '', nickname: '', email: '', password: '', note: '' }
  createRows.value = blankRows()
  createOpen.value = true
}

async function submitCreate() {
  const f = createForm.value
  if (!f.username.trim()) { message.warning('请输入登录名'); return }
  if (!EMAIL_RE.test(f.email.trim())) { message.warning('邮箱格式不对（如 name@example.com）'); return }
  if (f.password.length < 10 || !/[a-zA-Z]/.test(f.password) || !/\d/.test(f.password)) {
    message.warning('口令至少 10 位，且需同时含字母与数字'); return
  }
  submitting.value = true
  try {
    const row = await adminAdminsApi.create({
      username: f.username.trim(), password: f.password, email: f.email.trim(),
      nickname: f.nickname.trim(), note: f.note.trim(),
      grants: rowsToGrants(createRows.value),
    })
    message.success(`已创建「${row.username}」，请把口令私下交给对方（服务端不留明文）`)
    createOpen.value = false
    load()
  } catch (e: any) {
    message.error(e?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}

// ── 账号资料 + 权限编辑 ──
const grantTarget = ref<AdminAccount | null>(null)
const grantRows = ref<PermRow[]>([])
const grantForm = ref({ nickname: '', email: '', note: '' })

// 权限区只对「既不是自己、也不是顶级管理员」的目标开放：set_grants 对自己 403（防自改越权）、
// 对 super 409（隐式全有）。捆在同一次保存里硬提交会让整笔失败，所以这两类目标只改账号信息。
function grantsLocked(row: AdminAccount | null) {
  return !!row && (row.is_super || row.id === auth.user?.id)
}

function openGrants(row: AdminAccount) {
  grantTarget.value = row
  grantRows.value = grantsToRows(row.grants)
  grantForm.value = { nickname: row.nickname, email: row.email ?? '', note: row.note }
}

async function saveGrants() {
  const t = grantTarget.value
  if (!t) return
  const email = grantForm.value.email.trim()
  if (!EMAIL_RE.test(email)) { message.warning('邮箱格式不对（如 name@example.com）'); return }
  submitting.value = true
  const locked = grantsLocked(t)
  try {
    const profile = { nickname: grantForm.value.nickname.trim(), email, note: grantForm.value.note.trim() }
    const changed = profile.nickname !== t.nickname || profile.email !== t.email || profile.note !== t.note
    if (!changed && locked) {
      message.info('没有需要保存的变更')
    } else {
      if (changed) await adminAdminsApi.update(t.id, profile)   // 邮箱重复会在此处 409
      if (!locked) await adminAdminsApi.setGrants(t.id, rowsToGrants(grantRows.value))
      message.success(locked ? `已更新「${t.username}」的账号信息`
                             : `已更新「${t.username}」（权限变更对对方下一次请求即生效）`)
    }
    grantTarget.value = null
    load()
  } catch (e: any) {
    message.error(e?.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

// ── 启停 / 重置口令 / 删除 ──
async function toggleActive(row: AdminAccount) {
  try {
    await adminAdminsApi.update(row.id, { is_active: !row.is_active })
    message.success(row.is_active ? `已停用「${row.username}」（其会话立即失效）` : `已启用「${row.username}」`)
    load()
  } catch (e: any) {
    message.error(e?.message || '操作失败')
  }
}

const newPassword = ref<{ username: string; password: string } | null>(null)

function copyPassword() {
  const pw = newPassword.value?.password ?? ''
  navigator.clipboard?.writeText(pw)
  message.success('已复制到剪贴板')
}

async function resetPassword(row: AdminAccount) {
  try {
    const d = await adminAdminsApi.resetPassword(row.id)
    newPassword.value = { username: d.username, password: d.password }
    load()
  } catch (e: any) {
    message.error(e?.message || '重置失败')
  }
}

async function remove(row: AdminAccount) {
  try {
    await adminAdminsApi.remove(row.id)
    message.success(`已删除「${row.username}」`)
    load()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

const grantSummary = (row: AdminAccount) => row.is_super
  ? '全部权限（顶级）'
  : row.permissions.length
    ? row.grants.map((g) => g.column_id === null
      ? PERMS.find((p) => p.key === g.permission)?.label ?? g.permission
      : `${PERMS.find((p) => p.key === g.permission)?.label ?? g.permission}·${columns.value.find((c) => c.id === g.column_id)?.name ?? `栏目${g.column_id}`}`,
    ).join('、')
    : '（只读）'

const tableColumns: DataTableColumns<AdminAccount> = [
  {
    title: '账号', key: 'username', minWidth: 180,
    render: (row) => h('div', { class: 'flex flex-col gap-0.5' }, [
      h('div', { class: 'flex items-center gap-1.5' }, [
        h('span', { class: 'font-medium' }, row.username),
        row.is_super ? h(NTag, { size: 'tiny', type: 'success', bordered: false }, () => '顶级') : null,
        !row.is_active ? h(NTag, { size: 'tiny', type: 'warning', bordered: false }, () => '已停用') : null,
      ]),
      h('span', { class: 'text-xs text-ink-3' }, `${row.nickname || '—'} · ${row.email || '未填邮箱'}`),
    ]),
  },
  {
    title: '权限', key: 'grants', minWidth: 260, ellipsis: { tooltip: true },
    render: (row) => h('span', { class: 'text-xs text-ink-2' }, grantSummary(row)),
  },
  {
    title: '内容/素材', key: 'count', width: 100,
    render: (row) => h('span', { class: 'text-xs tabular-nums text-ink-3' }, `${row.content_count} / ${row.media_count}`),
  },
  {
    title: '最近登录', key: 'last_login_at', width: 150,
    render: (row) => h('span', { class: 'text-xs text-ink-3' }, row.last_login_at ? row.last_login_at.slice(0, 16).replace('T', ' ') : '从未'),
  },
  {
    title: '操作', key: 'actions', width: 210,
    render: (row) => {
      const self = row.id === auth.user?.id
      return h('div', { class: 'flex items-center gap-1' }, [
        // 自己那行也可编辑：邮箱只能从这里填（「我的资料」不含邮箱），
        // 而忘记密码只往 users.email 投递；非顶级管理员碰 super 一律 403，故仍禁。
        h(NButton, {
          size: 'tiny', quaternary: true, disabled: row.is_super && !auth.user?.is_super,
          onClick: () => openGrants(row),
        }, () => '编辑'),
        h(NButton, { size: 'tiny', quaternary: true, disabled: self, onClick: () => resetPassword(row) }, () => '重置口令'),
        h(NButton, {
          size: 'tiny', quaternary: true, disabled: self,
          onClick: () => toggleActive(row),
        }, () => (row.is_active ? '停用' : '启用')),
        h(NPopconfirm, { onPositiveClick: () => remove(row) }, {
          trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error', disabled: self || row.is_super }, () => '删除'),
          default: () => '仅可删除名下没有内容与素材的账号，确定删除？',
        }),
      ])
    },
  },
]
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">管理员账号</h1>
      <p class="text-xs text-ink-3">每个管理员只能管理自己上传的内容；权限可按全局或按栏目授予 · 在职管理员的昵称/头像/签名/社交链会出现在前台关于页，停用即下架</p>
      <n-button class="ml-auto" size="small" type="primary" @click="openCreate">＋ 新建管理员</n-button>
    </div>

    <div class=" border border-line bg-surface p-4">
      <n-data-table
        :columns="tableColumns" :data="items" :loading="loading" size="small"
        :row-key="(r: AdminAccount) => r.id" :scroll-x="880"
      />
      <p class="mt-3 text-xs text-ink-3">
        共 {{ items.length }} 个账号 · 停用会立即踢掉其全部会话 · 撤权无需对方重新登录（服务端每次请求实时读权限）
      </p>
    </div>

    <!-- 新建 -->
    <n-modal
      :show="createOpen" preset="card" title="新建管理员"
      style="width: 640px; max-width: 94vw; border-radius: 16px"
      @update:show="(v: boolean) => { if (!v) createOpen = false }"
    >
      <div class="grid grid-cols-2 gap-3">
        <div>
          <p class="mb-1 text-xs text-ink-3">登录名</p>
          <n-input v-model:value="createForm.username" placeholder="如 editor_blog" :disabled="submitting" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">昵称（列表与操作日志里显示）</p>
          <n-input v-model:value="createForm.nickname" placeholder="留空同登录名" :disabled="submitting" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">邮箱（必填，全站唯一）</p>
          <n-input v-model:value="createForm.email" placeholder="name@example.com" :disabled="submitting" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">初始口令（≥10 位，含字母与数字）</p>
          <n-input v-model:value="createForm.password" placeholder="自己拟一条交给对方" :disabled="submitting" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">备注</p>
          <n-input v-model:value="createForm.note" placeholder="如：负责博客栏目" :disabled="submitting" />
        </div>
      </div>

      <p class="mb-2 mt-4 text-xs font-medium text-ink-2">
        权限（不勾则该账号只能查看，不能任何写入）· 支持栏目范围的权限：勾名称=全站，只在右侧选栏目=仅这些栏目
      </p>
      <div class="max-h-72 space-y-1.5 overflow-y-auto pr-1">
        <div
          v-for="r in createRows" :key="r.permission"
          class="flex flex-wrap items-center gap-2  border border-line bg-elevated px-3 py-2"
        >
          <n-checkbox :checked="r.global" :disabled="!canOffer(r.permission) || submitting"
                      :title="canOffer(r.permission) ? '' : '只能授出自己已具备的权限点；「管理员账号」仅顶级可授'"
                      @update:checked="(v: boolean) => setGlobal(r, v)">
            <span class="text-sm">{{ r.label }}</span>
          </n-checkbox>
          <span class="text-xs text-ink-3">{{ PERMS.find((p) => p.key === r.permission)?.hint }}</span>
          <n-select
            v-if="r.scoped" :value="r.columnIds" multiple size="tiny" class="ml-auto !w-56"
            :options="columnOptions" placeholder="或仅指定栏目（可多选）" :max-tag-count="2"
            :disabled="!canOffer(r.permission) || submitting"
            @update:value="(v: number[]) => setColumns(r, v)"
          />
          <span v-if="r.scoped" class="shrink-0 text-xs text-ink-3">{{ scopeOf(r) }}</span>
        </div>
      </div>

      <div class="mt-4 flex justify-end gap-2">
        <n-button size="small" @click="createOpen = false">取消</n-button>
        <n-button size="small" type="primary" :loading="submitting" @click="submitCreate">创建</n-button>
      </div>
    </n-modal>

    <!-- 改权限 -->
    <n-modal
      :show="!!grantTarget" preset="card" :title="`编辑账号 · ${grantTarget?.username ?? ''}`"
      style="width: 640px; max-width: 94vw; border-radius: 16px"
      @update:show="(v: boolean) => { if (!v) grantTarget = null }"
    >
      <div class="grid grid-cols-3 gap-3">
        <div>
          <p class="mb-1 text-xs text-ink-3">昵称</p>
          <n-input v-model:value="grantForm.nickname" size="small" :disabled="submitting" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">邮箱（必填，全站唯一）</p>
          <n-input v-model:value="grantForm.email" size="small" :disabled="submitting" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">备注</p>
          <n-input v-model:value="grantForm.note" size="small" :disabled="submitting" />
        </div>
      </div>
      <template v-if="!grantsLocked(grantTarget)">
        <p class="mb-3 mt-4 text-xs text-ink-3">
          下方权限为整体覆盖：未勾选项即撤销。支持栏目范围的权限，勾名称=全站，只在右侧选栏目=仅这些栏目（两者取后一次操作）。顶级管理员隐式拥有全部权限，无需在此设置。
        </p>
        <div class="max-h-72 space-y-1.5 overflow-y-auto pr-1">
          <div
            v-for="r in grantRows" :key="r.permission"
            class="flex flex-wrap items-center gap-2  border border-line bg-elevated px-3 py-2"
          >
            <n-checkbox :checked="r.global" :disabled="!canOffer(r.permission) || submitting"
                        :title="canOffer(r.permission) ? '' : '只能授出自己已具备的权限点；「管理员账号」仅顶级可授'"
                        @update:checked="(v: boolean) => setGlobal(r, v)">
              <span class="text-sm">{{ r.label }}</span>
            </n-checkbox>
            <span class="text-xs text-ink-3">{{ PERMS.find((p) => p.key === r.permission)?.hint }}</span>
            <n-select
              v-if="r.scoped" :value="r.columnIds" multiple size="tiny" class="ml-auto !w-56"
              :options="columnOptions" placeholder="或仅指定栏目（可多选）" :max-tag-count="2"
              :disabled="!canOffer(r.permission) || submitting"
              @update:value="(v: number[]) => setColumns(r, v)"
            />
            <span v-if="r.scoped" class="shrink-0 text-xs text-ink-3">{{ scopeOf(r) }}</span>
          </div>
        </div>
      </template>
      <p v-else class="mt-4  border border-line bg-elevated px-3 py-2 text-xs leading-relaxed text-ink-3">
        {{ grantTarget?.is_super
          ? '顶级管理员隐式拥有全部权限，无需授权，因此这里只改昵称 / 邮箱 / 备注。'
          : '不能修改自己的权限（防自改越权），因此这里只改昵称 / 邮箱 / 备注；头像与签名等资料请到「我的资料」。' }}
      </p>
      <div class="mt-4 flex justify-end gap-2">
        <n-button size="small" @click="grantTarget = null">取消</n-button>
        <n-button size="small" type="primary" :loading="submitting" @click="saveGrants">保存</n-button>
      </div>
    </n-modal>

    <!-- 一次性口令 -->
    <n-modal
      :show="!!newPassword" preset="card" title="新口令已生成（只显示这一次）"
      style="width: 420px; max-width: 94vw; border-radius: 16px"
      @update:show="(v: boolean) => { if (!v) newPassword = null }"
    >
      <p class="text-sm">账号 <b>{{ newPassword?.username }}</b></p>
      <div class="mt-2 flex items-center gap-2  border border-line bg-elevated px-3 py-2">
        <code class="flex-1 break-all text-sm">{{ newPassword?.password }}</code>
        <n-button size="tiny" quaternary @click="copyPassword">复制</n-button>
      </div>
      <p class="mt-2 text-xs text-ink-3">该账号的旧会话已全部下线，需用新口令重新登录。</p>
      <div class="mt-4 flex justify-end">
        <n-button size="small" type="primary" @click="newPassword = null">我已保存</n-button>
      </div>
    </n-modal>
  </div>
</template>
