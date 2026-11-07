<script setup lang="ts">
import {
  NButton, NDynamicInput, NForm, NFormItem, NInput, NInputNumber, NModal, NSelect,
  useMessage,
} from 'naive-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { adminColumnsApi, adminContentsApi, adminMediaApi, adminTagsApi } from '@/api'
import type { MediaAsset } from '@/api/types'
import MediaPicker from '@/components/admin/MediaPicker.vue'
import MarkdownHelp from '@/components/admin/MarkdownHelp.vue'
import MediaViewer from '@/components/site/MediaViewer.vue'
import { assetKindLabel, extOf, isGlb, isGlbName, isImageName, isZip, isZipName } from '@/utils/media3d'
import { externalImageUrls, localImageUrls } from '@/utils/mdImages'
import { enhanceCodeBlocks } from '@/composables/useCodeEnhance'
import { renderMd } from '@/composables/useMd'
import AdminIcon from '@/components/admin/AdminIcon.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const id = ref<number | null>(route.params.id ? Number(route.params.id) : null)
const isNew = computed(() => id.value === null)
const loading = ref(!isNew.value)
/** 非本人上传（或无栏目授权不足）时服务端回报 can_edit=false → 本页进只读态 */
const readOnly = ref(false)
const ownerName = ref<string | null>(null)
const saving = ref(false)
const dirty = ref(false)
const loaded = ref(false)

const type = ref<'article' | 'model' | 'chat'>(
  (route.query.type as any) || 'article',
)

const form = reactive({
  title: '',
  slug: '',
  summary: '',
  body_md: '',
  status: 'draft',
  media_kind: null as null | '3d' | 'render' | 'animation',
  coverAsset: null as MediaAsset | null,
  tagIds: [] as (number | string)[],   // n-select tag 模式：新输入为字符串
  columnId: null as number | null,
  assetIds: [] as number[],
  extra: { software: '', faces: null as number | null, duration: '', links: [] as { label: string; url: string }[] },
})

const tagOptions = ref<{ label: string; value: number }[]>([])
const columnOptions = ref<{ label: string; value: number }[]>([])
const previewMode = ref<'split' | 'edit' | 'preview'>('split')
const helpOpen = ref(false)
const pickerOpen = ref(false)
const pickerMode = ref<'cover' | 'assets'>('cover')

/* ---------- 模型工作台：素材对象、拖拽上传、预览切换 ---------- */
const assets = ref<MediaAsset[]>([])
const uploading = ref(false)
const statusText = ref('')
const dragOver = ref(false)
const bodyOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const dirInput = ref<HTMLInputElement | null>(null)

interface NamedFile { file: File; path: string; fromDir: boolean }

function onPickFiles(e: Event) {
  const t = e.target as HTMLInputElement
  const list = Array.from(t.files ?? []).map((f) => {
    const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || ''
    return { file: f, path: rel || f.name, fromDir: !!rel }
  })
  if (list.length) ingest(list)
  t.value = ''
}

const syncAssetIds = () => { form.assetIds = assets.value.map((a) => a.id) }

/** 拖入文件夹时 dt.files 只给一个 0 字节伪文件，须走 webkitGetAsEntry 逐层展开取相对路径 */
async function collectDropped(dt: DataTransfer): Promise<NamedFile[]> {
  const entries = Array.from(dt.items ?? [])
    .filter((i) => i.kind === 'file')
    .map((i) => (i as unknown as { webkitGetAsEntry?: () => FileSystemEntry | null }).webkitGetAsEntry?.())
    .filter(Boolean) as FileSystemEntry[]
  if (!entries.length) return Array.from(dt.files ?? []).map((f) => ({ file: f, path: f.name, fromDir: false }))
  const out: NamedFile[] = []
  // readEntries 每批有上限，必须循环读到空数组才算列完
  const readAll = (dir: FileSystemDirectoryEntry) => new Promise<FileSystemEntry[]>((resolve, reject) => {
    const reader = dir.createReader()
    const all: FileSystemEntry[] = []
    const step = () => reader.readEntries(
      (batch) => { if (!batch.length) resolve(all); else { all.push(...batch); step() } },
      reject,
    )
    step()
  })
  const fileOf = (f: FileSystemFileEntry) => new Promise<File>((resolve, reject) => f.file(resolve, reject))
  const walk = async (e: FileSystemEntry, prefix: string) => {
    const path = prefix ? `${prefix}/${e.name}` : e.name
    if (e.isFile) out.push({ file: await fileOf(e as FileSystemFileEntry), path, fromDir: !!prefix })
    else if (e.isDirectory) for (const child of await readAll(e as FileSystemDirectoryEntry)) await walk(child, path)
  }
  for (const e of entries) await walk(e, e.isDirectory ? e.name : '')
  return out
}

async function uploadOne(f: File) {
  const a = await adminMediaApi.upload(f, 'model')
  if (!assets.value.some((x) => x.id === a.id)) assets.value.push(a)
  syncAssetIds()
  return a
}

/** 后端只收 glb 与 zip：模型文件夹在浏览器内按原层级打包成 zip 再上传 */
async function packToZip(items: NamedFile[], zipName: string) {
  const { default: JSZip } = await import('jszip')
  const zip = new JSZip()
  for (const it of items) zip.file(it.path, it.file)
  return new File([await zip.generateAsync({ type: 'blob' })], zipName, { type: 'application/zip' })
}

async function ingest(list: NamedFile[]) {
  if (uploading.value || !list.length) return
  uploading.value = true
  let done = 0
  const notes: string[] = []
  // glb/zip 直传；散选的图片作渲染图；其余（obj/mtl/贴图/blend…）打包
  const direct = list.filter((f) => isGlbName(f.file.name) || isZipName(f.file.name) || (!f.fromDir && isImageName(f.file.name)))
  const pack = list.filter((f) => !direct.includes(f))
  try {
    for (const f of direct) {
      if (!f.file.size) { notes.push(`${f.file.name}（空文件）`); continue }
      try { await uploadOne(f.file); done++ } catch (e: any) { notes.push(`${f.file.name}（${e?.message || '上传失败'}）`) }
    }
    if (pack.length) {
      const tops = [...new Set(pack.map((p) => p.path.split('/')[0]))]
      const zipName = `${(tops.length === 1 ? tops[0] : pack[0].file.name).replace(/\.[^.]+$/, '')}.zip`
      try {
        statusText.value = `正在打包 ${pack.length} 个文件…`
        await uploadOne(await packToZip(pack, zipName))
        done++
      } catch (e: any) { notes.push(`${zipName}（${e?.message || '打包上传失败'}）`) }
    }
  } finally {
    uploading.value = false
    statusText.value = ''
  }
  if (done) message.success(`已上传 ${done} 个素材`)
  if (notes.length) {
    message.warning(`未上传 ${notes.length} 项：${notes.slice(0, 3).join('、')}${notes.length > 3 ? ' 等' : ''}`, { duration: 8000 })
  }
}

async function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!e.dataTransfer) return
  ingest(await collectDropped(e.dataTransfer))
}
function removeAsset(a: MediaAsset) {
  assets.value = assets.value.filter((x) => x.id !== a.id)
  syncAssetIds()
  if (form.coverAsset?.id === a.id) form.coverAsset = null
}

/** 元数据卡片弹窗：publish=发布前填写确认，settings=仅编辑元数据 */
const metaOpen = ref(false)
const metaMode = ref<'publish' | 'settings'>('publish')

const previewRef = ref<HTMLElement | null>(null)
const taRef = ref<HTMLTextAreaElement | null>(null)
const previewHtml = computed(() => renderMd(form.body_md || '*（左侧输入 Markdown，这里实时预览）*').html)

watch(previewHtml, () => nextTick(() => previewRef.value && enhanceCodeBlocks(previewRef.value)))

/**
 * 分屏同步滚动：按标题锚点对齐而非纯比例——MD 源码行与渲染块高度不成比例，
 * 纯比例会越滚越偏。做法：源码 h2/h3 行 ↔ 预览同序标题，两侧各取「像素偏移」为断点，
 * 正反向共用同一条分段线性函数（applyKnots 交换 from/to），互为精确逆 ⇒ 往返恒等。
 * 断点必须实测而非按行号推算：textarea 会把长源码行折行（源码行号与像素不成比例）；
 * 且末段跨距必须取「可达范围」scrollHeight - clientHeight 而非 scrollHeight，否则正向
 * 输出被浏览器截掉一个视口高、反向按更大的跨距反算，每轮丢一截，长文里表现为滚不到底。
 */
function sourceHeadingLines(md: string): number[] {
  const out: number[] = []
  let fence = false
  md.split('\n').forEach((l, i) => {
    if (/^```/.test(l)) fence = !fence
    else if (!fence && /^#{2,3} /.test(l)) out.push(i)
  })
  return out
}

/** 与 textarea 同宽度同样式的镜像层，逐源码行一个块，实测标题行的像素偏移 */
const MIRROR_PROPS = [
  'boxSizing', 'fontFamily', 'fontSize', 'fontStyle', 'fontVariant', 'fontWeight',
  'letterSpacing', 'lineHeight', 'textIndent', 'textTransform',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
] as const
let mirrorEl: HTMLDivElement | null = null
let mirrorKey = ''
let mirrorTops: number[] = []

function headingTops(ta: HTMLTextAreaElement, heads: number[], md: string): number[] {
  const key = `${ta.clientWidth}|${md}`
  if (key === mirrorKey) return mirrorTops
  if (!mirrorEl) {
    mirrorEl = document.createElement('div')
    mirrorEl.setAttribute('aria-hidden', 'true')
    // 换行相关三项固定为 textarea 软换行的等价物，不从计算样式复制（textarea 报 normal）
    mirrorEl.style.cssText = 'position:absolute;top:-100000px;left:0;visibility:hidden;pointer-events:none;'
      + 'white-space:pre-wrap;overflow-wrap:break-word;height:auto!important;min-height:0!important;'
    document.body.appendChild(mirrorEl)
  }
  const ms = mirrorEl.style as unknown as Record<string, string>
  const cs = getComputedStyle(ta) as unknown as Record<string, string>
  for (const p of MIRROR_PROPS) ms[p] = cs[p]
  ms.width = `${ta.clientWidth}px`
  const frag = document.createDocumentFragment()
  const rows: HTMLElement[] = []
  for (const text of md.split('\n')) {
    const row = document.createElement('div')
    if (text) row.textContent = text
    else row.appendChild(document.createElement('br'))   // 空行也要占一个行高
    frag.appendChild(row)
    rows.push(row)
  }
  mirrorEl.replaceChildren(frag)
  // 全部插完再一次性读，边插边读会退化成每行一次 reflow
  mirrorTops = heads.map((h) => rows[h]?.offsetTop ?? 0)
  mirrorKey = key
  return mirrorTops
}

/** 断点严格递增 ⇒ 分段线性函数是双射，交换 from/to 即得其逆 */
function applyKnots(x: number, from: number[], to: number[]): number {
  let k = 0
  while (k + 2 < from.length && from[k + 1] <= x) k++
  const lo = from[k]
  const frac = (Math.min(from[k + 1], Math.max(lo, x)) - lo) / (from[k + 1] - lo)
  return to[k] + (to[k + 1] - to[k]) * frac
}

/**
 * 程序化 scrollTop 的回声事件在「下一帧的 scroll steps」才派发，而 rAF 回调在「本帧末尾」
 * 就已执行，用 rAF 释放守卫必然漏挡一次、进而左右互推不止；改为记住赋值后的实际位置，
 * 回声命中即消费掉这一次。赋值前后位置相同则不会有回声，此时不留期望值以免误吞后续真实滚动。
 */
let echo: { el: HTMLElement; top: number } | null = null

function syncScroll(from: 'edit' | 'preview') {
  if (previewMode.value !== 'split') return
  const ta = taRef.value, prev = previewRef.value
  if (!ta || !prev) return
  const self = from === 'edit' ? ta : prev
  if (echo && echo.el === self && Math.abs(self.scrollTop - echo.top) < 1.5) { echo = null; return }
  echo = null
  const other = from === 'edit' ? prev : ta
  const maxEdit = Math.max(0, ta.scrollHeight - ta.clientHeight)
  const maxPrev = Math.max(0, prev.scrollHeight - prev.clientHeight)
  if (!maxEdit || !maxPrev) return
  const md = form.body_md
  const heads = sourceHeadingLines(md)
  // offsetTop 基准是最近的定位祖先而非滚动容器，须用 rect 差值换算成容器内偏移
  const pr = prev.getBoundingClientRect()
  const tops = [...prev.querySelectorAll<HTMLElement>('h2[id], h3[id]')]
    .map((e) => e.getBoundingClientRect().top - pr.top + prev.scrollTop)
  const ek = [0], pk = [0]
  if (heads.length && heads.length === tops.length) {
    const eTops = headingTops(ta, heads, md)
    heads.forEach((_, i) => {
      const ea = eTops[i], pa = tops[i]
      // 只收严格落在开区间内的锚点，保证两条断点序列同时严格递增
      if (ea > ek[ek.length - 1] && ea < maxEdit && pa > pk[pk.length - 1] && pa < maxPrev) { ek.push(ea); pk.push(pa) }
    })
  }
  // 无标题或两侧数量不一致时断点只剩端点，即退回纯比例映射
  ek.push(maxEdit); pk.push(maxPrev)
  const target = from === 'edit' ? applyKnots(self.scrollTop, ek, pk) : applyKnots(self.scrollTop, pk, ek)
  const before = other.scrollTop
  other.scrollTop = target
  echo = other.scrollTop === before ? null : { el: other, top: other.scrollTop }
}

async function loadTags(forType = type.value) {
  try {
    const d = await adminTagsApi.list(forType)
    // 异步返回时类型可能已切换，丢弃过期结果
    if (forType !== type.value) return
    tagOptions.value = d.items.map((t) => ({ label: t.name, value: t.id }))
  } catch { /* 非关键 */ }
}
watch(type, (t) => { loadTags(t); loadColumns(t); form.columnId = null })

async function loadColumns(forType = type.value) {
  try {
    const d = await adminColumnsApi.list(forType)
    // 异步返回时类型可能已切换，丢弃过期结果
    if (forType !== type.value) return
    const byId = new Map(d.items.map((c) => [c.id, c]))
    const depthOf = (c: { parent_id?: number | null }) => {
      let dep = 0, p = c.parent_id
      while (p) { dep++; p = byId.get(p)?.parent_id ?? null }
      return dep
    }
    columnOptions.value = d.items.map((c) => ({ label: `${'　'.repeat(depthOf(c))}${c.name}`, value: c.id }))
  } catch { /* 非关键 */ }
}

async function load() {
  if (id.value === null) { loaded.value = true; return }
  loading.value = true
  try {
    const c = await adminContentsApi.get(id.value)
    readOnly.value = (c as any).can_edit === false
    ownerName.value = (c as any).owner_nickname ?? null
    type.value = c.type as any
    form.title = c.title
    form.slug = c.slug ?? ''
    form.summary = c.summary
    form.body_md = (c as any).body_md ?? ''
    form.status = c.status
    form.media_kind = (c.media_kind ?? null) as any
    form.tagIds = c.tags.map((t) => t.id)
    form.columnId = (c as any).column_id ?? null
    const ex = (c.extra ?? {}) as any
    form.extra = {
      software: ex.software ?? '', faces: ex.faces ?? null, duration: ex.duration ?? '',
      links: Array.isArray(ex.links) ? ex.links : [],
    }
    assets.value = (((c as any).assets ?? []) as MediaAsset[]).filter(Boolean)
    syncAssetIds()
    form.coverAsset = c.cover
      ? { id: c.cover_asset_id ?? 0, url: c.cover, kind: 'image', mime: '', size: 0, width: null, height: null, thumb: null, storage_key: '' }
      : null
    dirty.value = false
  } catch (e: any) {
    message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
    loaded.value = true
    // 深监听回调在本次 flush 后才跑，同步置 dirty=false 会被它盖回；
    // 必须等一帧，否则一进编辑页就显示「有未保存更改」并触发 30s 冗余自动保存。
    nextTick(() => { dirty.value = false })
    nextTick(() => previewRef.value && enhanceCodeBlocks(previewRef.value))
  }
}
onMounted(() => { loadTags(); loadColumns(); load() })

function payload() {
  return {
    type: type.value,
    status: form.status === 'published' ? 'published' : 'draft',
    title: form.title || '未命名',
    slug: form.slug || undefined,
    summary: form.summary,
    body_md: form.body_md,
    cover_asset_id: form.coverAsset?.id || null,
    media_kind: type.value === 'model' ? form.media_kind : null,
    tags: form.tagIds
      .map((v) => (typeof v === 'number' ? { id: v } : { name: String(v).trim() }))
      .filter((t) => (t as { id?: number }).id !== undefined || (t as { name?: string }).name),
    column_id: form.columnId ?? null,
    asset_ids: type.value === 'model' ? form.assetIds : [],
    extra: type.value === 'model'
      ? { ...form.extra, links: form.extra.links.filter((l) => l.url) }
      : (form.extra.software ? { software: form.extra.software } : {}),
  }
}

async function save(silent = false): Promise<boolean> {
  if (readOnly.value) {
    if (!silent) message.warning(`该内容由 ${ownerName.value || '其他管理员'} 创建，你只有查看权限`)
    return false
  }
  if (saving.value) return false
  saving.value = true
  try {
    if (id.value === null) {
      const created = await adminContentsApi.create(payload())
      id.value = created.id
      form.status = created.status ?? form.status
      router.replace(`/admin/content/${created.id}/edit`)
    } else {
      const updated = await adminContentsApi.update(id.value, payload())
      form.status = updated.status ?? form.status
    }
    dirty.value = false
    if (!silent) message.success('已保存')
    return true
  } catch (e: any) {
    if (!silent) message.error(e?.message || '保存失败')
    else message.warning(`自动保存失败：${e?.message || '网络错误'}`)
    return false
  } finally {
    saving.value = false
  }
}

// 30s 防抖自动存草稿
let autoTimer: number | undefined
watch(form, () => {
  if (!loaded.value) return
  dirty.value = true
  clearTimeout(autoTimer)
  autoTimer = window.setTimeout(() => {
    if (dirty.value) save(true).then((ok) => ok && message.info('已自动保存草稿', { duration: 2000 }))
  }, 30000)
})

function beforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) { e.preventDefault(); e.returnValue = '' }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  clearTimeout(autoTimer)
  mirrorEl?.remove()
  mirrorEl = null
  mirrorKey = ''
})

function openMeta(mode: 'publish' | 'settings') {
  if (!form.title.trim()) { message.warning('请先填写标题'); return }
  metaMode.value = mode
  metaOpen.value = true
}

async function confirmMeta() {
  if (metaMode.value === 'settings') {
    if (await save()) metaOpen.value = false
    return
  }
  if (!(await save(true))) return
  try {
    const d = await adminContentsApi.setStatus(id.value!, 'published')
    form.status = 'published'
    metaOpen.value = false
    message.success('已发布 ✓ 查看前台', { duration: 6000 })
    if (d?.pipeline?.queued) {
      message.info('前端重建已排队（约 10s 合并窗口），完成后按配置推送百度；失败可在 SEO 面板重推', { duration: 8000 })
    }
  } catch (e: any) {
    message.error(e?.message || '发布失败')
  }
}

async function previewDraft() {
  if (id.value === null || type.value !== 'article') { message.info('草稿预览目前支持文章类型'); return }
  if (!(await save(true))) return
  const d = await adminContentsApi.previewToken(id.value)
  window.open(`/blog/${form.slug || 'x'}?preview=${d.token}`, '_blank')
}

/* ---------- 外链图片入库：识别 Markdown 里的外链图 → 服务端下载进素材库 ---------- */
const importingImages = ref(false)
/** 需要下载入库的外链图片（本站/本机/相对路径/data: 都算本地，不计入） */
const externalImages = computed(() => externalImageUrls(form.body_md || ''))
/** 已经是本地地址、无需入库的图片，仅用于按钮提示 */
const localImages = computed(() => localImageUrls(form.body_md || ''))

async function importExternalImages() {
  if (readOnly.value || importingImages.value || !externalImages.value.length) return
  // 命名要用内容 slug，新建内容得先落库拿到 id 与自动生成的 slug
  if (id.value === null && !(await save(true))) return
  const cid = id.value
  if (cid === null) return
  importingImages.value = true
  try {
    const r = await adminContentsApi.importImages(cid, form.body_md || '')
    if (r.body_md !== form.body_md) {
      form.body_md = r.body_md
      await save(true)                       // 立刻持久化改写结果，避免只留在本地
    }
    if (r.imported.length) {
      message.success(`已入库 ${r.imported.length} 张，正文地址已改为站点全链`, { duration: 6000 })
    }
    if (r.failed.length) {
      const head = r.failed.slice(0, 3).map((f) => f.reason).join('；')
      message.warning(`${r.failed.length} 张未入库：${head}${r.failed.length > 3 ? ' 等' : ''}`,
        { duration: 10000 })
    }
    if (!r.imported.length && !r.failed.length) {
      message.info(r.skipped.length
        ? `识别到 ${r.skipped.length} 张本地链接，无需下载`
        : '没有可处理的外链图片')
    }
  } catch (e: any) {
    message.error(e?.message || '图片入库失败')
  } finally {
    importingImages.value = false
  }
}

function onPickAsset(a: MediaAsset) {
  if (pickerMode.value === 'cover') form.coverAsset = a
  else if (!assets.value.some((x) => x.id === a.id)) {
    assets.value.push(a)
    syncAssetIds()
  }
}

function openPicker(mode: 'cover' | 'assets') {
  pickerMode.value = mode
  pickerOpen.value = true
}

const typeLabel = computed(() => ({ article: '文章', model: '模型', chat: '杂谈' })[type.value])
</script>

<template>
  <div class="flex min-h-[560px] flex-col lg:h-[calc(100vh-120px)]">
    <!-- 顶栏 -->
    <div class="mb-4 flex shrink-0 flex-wrap items-center gap-3">
      <n-button size="small" tertiary @click="router.push('/admin/content')">← 列表</n-button>
      <h1 class="text-2xl font-bold">{{ isNew ? `新建${typeLabel}` : `编辑${typeLabel}` }}</h1>
      <span v-if="dirty" class="text-xs text-warning">● 有未保存更改</span>
      <span v-else-if="!isNew" class="text-xs text-ink-3">已保存</span>
      <span
        class="rounded-full border px-2 py-0.5 text-xs"
        :class="form.status === 'published' ? 'border-success text-success' : 'border-line text-ink-3'"
      >{{ form.status === 'published' ? '已发布' : '草稿' }}</span>
      <div class="ml-auto flex gap-2">
        <n-button v-if="type === 'article' && !isNew" size="small" tertiary @click="previewDraft">预览</n-button>
        <template v-if="!readOnly">
          <n-button size="small" tertiary @click="openMeta('settings')"><AdminIcon name="setting" :size="13" class="mr-1 inline align-[-2px]" />设置</n-button>
          <n-button size="small" :loading="saving" @click="save()">保存草稿</n-button>
          <n-button size="small" type="primary" @click="openMeta('publish')">发布</n-button>
        </template>
      </div>
    </div>

    <div
      v-if="readOnly"
      class="mb-3 flex shrink-0 items-center gap-2  border border-warning/50 bg-warning/10 px-3 py-2 text-sm text-warning"
    >
      只读：该内容由 {{ ownerName || '其他管理员' }} 创建，你只能管理自己上传的内容。
    </div>

    <!-- 编辑器（占满剩余视口） -->
    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <n-input v-model:value="form.title" placeholder="标题" class="mb-3 shrink-0 !text-lg" :input-props="{ style: 'font-size:18px;font-weight:600' }" />

      <!-- 模型工作台：左=预览与素材，右=上传与字段 -->
      <div v-if="type === 'model'" class="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div class="min-h-0 space-y-4 overflow-auto pr-1">
          <MediaViewer :assets="assets" :media-kind="form.media_kind" />

          <div v-if="assets.length">
            <p class="mb-2 text-xs text-ink-3">已挂素材 {{ assets.length }} 项 · 上方固定渲染 glb，其下按选项切换查看各工程包层级目录</p>
            <div class="grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-5">
              <div
                v-for="a in assets" :key="a.id"
                class="group relative overflow-hidden  border border-line"
              >
                <div
                  v-if="a.kind === 'model3d'"
                  class="flex h-20 w-full flex-col items-center justify-center gap-1 bg-elevated text-xs"
                >
                  <span class="text-base font-bold uppercase">{{ extOf(a) }}</span>
                  <span class="max-w-full truncate px-1">{{ a.filename }}</span>
                  <span v-if="isGlb(a)" class="text-brand">预览中</span>
                  <span v-else-if="isZip(a)" class="text-ink-3">{{ assetKindLabel(a) }} · {{ a.entries?.length ?? 0 }} 个文件</span>
                </div>
                <img v-else :src="a.thumb || a.url" :alt="a.filename" loading="lazy" class="h-20 w-full object-cover" />
                <div class="absolute right-1 top-1 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    v-if="a.kind === 'image'" class="bg-surface/90 px-1.5 py-0.5 text-[10px] hover:text-brand"
                    @click="form.coverAsset = a"
                  >封面</button>
                  <button class="bg-surface/90 px-1.5 py-0.5 text-[10px] text-danger" @click="removeAsset(a)">移除</button>
                </div>
              </div>
            </div>
          </div>
          <p v-else class=" border border-dashed border-line px-4 py-10 text-center text-sm text-ink-3">
            还没有素材 —— 在右侧拖入 glb（预览用）或模型文件夹（自动打包成 zip）
          </p>

          <div class=" border border-line bg-surface">
            <button class="flex w-full items-center justify-between px-4 py-2.5 text-xs text-ink-2" @click="bodyOpen = !bodyOpen">
              <span>作品说明（Markdown，前台详情页渲染）</span>
              <span class="text-ink-3">{{ bodyOpen ? '收起 ▲' : '展开 ▼' }}</span>
            </button>
            <textarea
              v-if="bodyOpen"
              v-model="form.body_md"
              class="h-[40vh] w-full resize-y border-t border-line bg-transparent p-4 font-mono text-sm leading-relaxed outline-none focus:border-brand"
              placeholder="# 作品说明…"
              spellcheck="false"
            />
          </div>
        </div>

        <aside class="min-h-0 space-y-4 overflow-auto  border border-line bg-surface p-4">
          <div
            class=" border-2 border-dashed px-4 py-6 text-center transition-colors"
            :class="dragOver ? 'border-brand bg-elevated' : 'border-line'"
            role="button" tabindex="0"
            @click="fileInput?.click()"
            @keydown.enter="fileInput?.click()"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <p class="text-sm" :class="uploading ? 'text-brand' : 'text-ink-2'">
              {{ uploading ? (statusText || '上传中…') : '拖入 glb / 模型文件夹 / zip · 点击选择文件' }}
            </p>
            <p class="mt-1 text-xs text-ink-3">
              glb ≤200MB（在线预览）· obj/fbx/blend/max 等文件夹自动打包成 zip ≤200MB
            </p>
          </div>
          <!-- 隐藏 input 放在触发区外：区内再放按钮会冒泡回父级导致重复弹框 -->
          <input ref="fileInput" type="file" multiple class="hidden" @change="onPickFiles">
          <input ref="dirInput" v-bind="{ webkitdirectory: '', directory: '' }" type="file" multiple class="hidden" @change="onPickFiles">
          <div class="flex gap-2">
            <n-button size="small" block secondary @click="dirInput?.click()">选择文件夹</n-button>
            <n-button size="small" block secondary @click="openPicker('assets')">从素材库选择</n-button>
          </div>

          <n-form label-placement="top" size="small" class="space-y-0">
            <n-form-item label="作品类型">
              <n-select
                v-model:value="form.media_kind"
                :options="[
                  { label: '3D 模型（glb 预览 + zip 工程包）', value: '3d' },
                  { label: '渲染图', value: 'render' },
                  { label: '动画（视频）', value: 'animation' },
                ]"
              />
            </n-form-item>
            <n-form-item label="封面（列表与分享图）">
              <div class="flex w-full items-center gap-2">
                <img v-if="form.coverAsset" :src="form.coverAsset.thumb || form.coverAsset.url" alt="封面" class="h-14 w-24  border border-line object-cover" />
                <n-button size="small" @click="openPicker('cover')">{{ form.coverAsset ? '更换' : '选择' }}</n-button>
                <n-button v-if="form.coverAsset" size="small" quaternary @click="form.coverAsset = null">清除</n-button>
              </div>
            </n-form-item>
            <n-form-item label="摘要（≤80 字，兼作 SEO 描述）">
              <n-input v-model:value="form.summary" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" maxlength="200" show-count />
            </n-form-item>
            <n-form-item label="标签（可输入新名称后回车创建）">
              <n-select v-model:value="form.tagIds" multiple filterable tag placeholder="选择或输入新标签" :options="tagOptions" />
            </n-form-item>
            <n-form-item label="所属栏目（可留空）">
              <n-select v-model:value="form.columnId" clearable filterable placeholder="选择栏目" :options="columnOptions" />
            </n-form-item>
            <div class="grid grid-cols-2 gap-2">
              <n-form-item label="软件版本"><n-input v-model:value="form.extra.software" placeholder="Blender 4.2" /></n-form-item>
              <n-form-item label="面数"><n-input-number v-model:value="form.extra.faces" :show-arrow="false" class="!w-full" /></n-form-item>
              <n-form-item label="时长"><n-input v-model:value="form.extra.duration" placeholder="00:42" /></n-form-item>
            </div>
            <n-form-item label="外部链接">
              <n-dynamic-input v-model:value="form.extra.links" :on-create="() => ({ label: '', url: '' })">
                <template #default="{ value }: any">
                  <div class="grid w-full grid-cols-2 gap-2">
                    <n-input v-model:value="value.label" placeholder="ArtStation" size="small" />
                    <n-input v-model:value="value.url" placeholder="https://…" size="small" />
                  </div>
                </template>
              </n-dynamic-input>
            </n-form-item>
          </n-form>
        </aside>
      </div>

      <!-- 文章 / 杂谈：Markdown 编辑器 -->
      <template v-else>
      <div class="relative flex min-h-0 flex-1 flex-col">
      <div class="mb-1 flex shrink-0 gap-2 text-xs">
        <button
          v-for="m in (['edit', 'split', 'preview'] as const)" :key="m"
          class="px-2 py-1" :class="previewMode === m ? 'bg-elevated text-brand' : 'text-ink-3 hover:text-ink'"
          @click="previewMode = m"
        >{{ { edit: '编辑', split: '分屏', preview: '预览' }[m] }}</button>
        <button
          class="ml-auto flex items-center gap-1 px-2 py-1 disabled:cursor-not-allowed disabled:opacity-40"
          :class="externalImages.length ? 'text-brand hover:underline' : 'text-ink-3'"
          :disabled="!externalImages.length || importingImages || readOnly"
          :title="externalImages.length
            ? `把正文里 ${externalImages.length} 张外链图片下载进素材库，命名为「slug-图片名」并回写站点全链${localImages.length ? `（另有 ${localImages.length} 张本地链接会跳过）` : ''}`
            : (localImages.length ? `正文里 ${localImages.length} 张图片都是本地链接，无需下载` : '正文里没有图片链接')"
          @click="importExternalImages"
        >
          <AdminIcon name="media" :size="13" />
          {{ importingImages ? '入库中…' : `外链图片 ${externalImages.length}` }}
        </button>
        <button
          class="px-2 py-1" :class="helpOpen ? 'bg-elevated text-brand' : 'text-ink-3 hover:text-ink'"
          :aria-expanded="helpOpen"
          @click="helpOpen = !helpOpen"
        >{{ helpOpen ? '收起语法' : '语法 ?' }}</button>
      </div>
      <div class="grid min-h-0 flex-1 gap-3" :class="previewMode === 'split' ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'">
        <textarea
          v-if="previewMode !== 'preview'"
          ref="taRef"
          v-model="form.body_md"
          class="h-[50vh] min-h-0 w-full resize-y  border border-line bg-surface p-4 font-mono text-sm leading-relaxed outline-none focus:border-brand lg:h-full lg:resize-none"
          placeholder="# 用 Markdown 写作…"
          spellcheck="false"
          @scroll="syncScroll('edit')"
        />
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-if="previewMode !== 'edit'" ref="previewRef" class="prose max-w-none min-h-0 h-[50vh] overflow-auto  border border-line bg-surface p-4 lg:h-full" @scroll="syncScroll('preview')">
          <div v-html="previewHtml" />
        </div>
      </div>
      <MarkdownHelp :show="helpOpen" @close="helpOpen = false" />
      </div>
      </template>
    </div>

    <!-- 发布/设置 元数据卡片 -->
    <n-modal
      v-model:show="metaOpen" preset="card" :mask-closable="false"
      :title="metaMode === 'publish' ? '发布内容' : '内容设置'"
      style="width: 480px; max-width: 94vw; border-radius: 16px"
    >
      <n-form label-placement="top" size="small">
        <n-form-item v-if="type !== 'chat'" label="Slug（发布后不可改；留空自动生成）">
          <n-input v-model:value="form.slug" :disabled="form.status === 'published'" placeholder="my-post-title" />
        </n-form-item>
        <!-- 模型类型的摘要/标签/栏目/封面已在右侧工作台常驻，弹窗不重复展示 -->
        <template v-if="type !== 'model'">
        <n-form-item label="摘要（≤80 字，兼作 SEO 描述）">
          <n-input v-model:value="form.summary" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" maxlength="200" show-count />
        </n-form-item>
        <n-form-item label="标签（可输入新名称后回车创建）">
          <n-select
            v-model:value="form.tagIds" multiple filterable tag
            placeholder="选择或输入新标签" :options="tagOptions"
          />
        </n-form-item>
        <n-form-item label="所属栏目（可留空，按内容类型隔离）">
          <n-select
            v-model:value="form.columnId" clearable filterable
            placeholder="选择栏目" :options="columnOptions"
          />
        </n-form-item>
        <n-form-item label="封面">
          <div class="flex w-full items-center gap-2">
            <img v-if="form.coverAsset" :src="form.coverAsset.thumb || form.coverAsset.url" alt="封面" class="h-14 w-24  border border-line object-cover" />
            <n-button size="small" @click="openPicker('cover')">{{ form.coverAsset ? '更换' : '选择素材' }}</n-button>
            <n-button v-if="form.coverAsset" size="small" quaternary @click="form.coverAsset = null">清除</n-button>
          </div>
        </n-form-item>
        </template>
      </n-form>
      <div class="flex justify-end gap-2">
        <n-button size="small" @click="metaOpen = false">取消</n-button>
        <n-button size="small" type="primary" :loading="saving" @click="confirmMeta">
          {{ metaMode === 'publish' ? '确定发布' : '保存设置' }}
        </n-button>
      </div>
    </n-modal>

    <MediaPicker :show="pickerOpen" :kind="pickerMode === 'assets' ? undefined : 'image'"
                 :category="pickerMode === 'assets' ? 'model' : (type === 'model' ? 'render' : 'blog')"
                 @update:show="pickerOpen = $event" @select="onPickAsset" />
  </div>
</template>
