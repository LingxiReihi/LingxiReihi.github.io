<script setup lang="ts">
import type { MediaAsset } from '@/api/types'
import { computed, ref, watch } from 'vue'
import ArchiveTree from '@/components/common/ArchiveTree.vue'
import ClientOnly from '@/components/common/ClientOnly.vue'
import { assetKindLabel, extOf, isGlb, isZip } from '@/utils/media3d'

const props = defineProps<{ assets: MediaAsset[]; mediaKind?: string | null }>()
defineEmits<{ (e: 'preview', index: number): void }>()

const images = (kind?: string) => props.assets.filter((a) => (kind ? a.kind === kind : a.kind === 'image'))
const model3ds = computed(() => images('model3d'))
// glb 常驻渲染；工程包只展示当前选中的那一个（多个包叠加会把正文挤没）
const glb = computed(() => model3ds.value.find(isGlb) ?? null)
const packs = computed(() => model3ds.value.filter(isZip))
const activePackId = ref<number | null>(null)
const activePack = computed(() => packs.value.find((z) => z.id === activePackId.value) ?? packs.value[0] ?? null)
// 定案前遗留的散格式素材（obj/fbx 等），只能下载
const others = computed(() => model3ds.value.filter((a) => !isGlb(a) && !isZip(a)))
const renderImgs = computed(() => images('image'))
const videos = computed(() => images('video'))

/** model-viewer 加载失败降级：监听 error 事件 */
const viewerFailed = ref(false)

// 仅在客户端注入 model-viewer。用 watch 而非 onMounted：素材数据常晚于挂载到达
// （异步详情页、后台上传后），挂载时判断会把库永久漏注入，元素退化为未知标签而空白。
// immediate 会在 SSG 构建期于 Node 执行，故守卫 customElements 是否存在。
watch(() => glb.value?.url ?? '', (url) => {
  viewerFailed.value = false
  if (typeof customElements === 'undefined') return
  if (url && !customElements.get('model-viewer')) void import('@google/model-viewer')
}, { immediate: true })
</script>

<template>
  <div class="space-y-4">
    <!-- 3D：glb 交互预览在上，下方逐个列出工程包的层级目录 -->
    <template v-if="mediaKind === '3d' && model3ds.length">
      <ClientOnly v-if="glb && !viewerFailed">
        <model-viewer
          :src="glb.url"
          alt="3D 模型"
          camera-controls
          auto-rotate
          shadow-intensity="1"
          style="width: 100%; height: min(70vh, 640px); background: var(--c-elevated); border-radius: 12px"
          @error="viewerFailed = true"
        />
      </ClientOnly>
      <p v-if="viewerFailed" class="text-sm text-ink-3">⚠ 3D 查看器加载失败，已降级为渲染图</p>
      <p v-else-if="!glb" class="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-ink-3">
        本作品没有 glb，无法在线渲染（仅 .glb 可交互预览）—— 工程包内容见下，源文件请用下载按钮获取
      </p>

      <!-- 实测父级 space-y 对本行不生效：上间距=pt，下间距=pb+目录树自带 16px，
           故 pt-4 不带 pb 即上下各 16px 对齐 -->
      <div v-if="packs.length > 1" class="flex flex-wrap gap-1.5 pt-4 text-xs">
        <button
          v-for="z in packs" :key="z.id"
          class="max-w-[260px] truncate rounded-lg border px-2.5 py-1 transition-colors"
          :class="z.id === activePack?.id ? 'border-brand text-brand' : 'border-line text-ink-3 hover:text-ink'"
          @click="activePackId = z.id"
        >{{ assetKindLabel(z) }} · {{ z.filename }}</button>
      </div>
      <ArchiveTree
        v-if="activePack"
        :entries="activePack.entries ?? []"
        :label="`「${activePack.filename || '压缩包'}」· ${assetKindLabel(activePack)}`"
      />
      <p v-for="a in others" :key="'o' + a.id" class="rounded-xl border border-dashed border-line px-4 py-3 text-center text-xs text-ink-3">
        {{ a.filename }}（{{ extOf(a) }}）为旧版散格式素材，仅可下载
      </p>
    </template>

    <!-- 渲染图组 -->
    <div v-if="renderImgs.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <button
        v-for="(a, i) in renderImgs" :key="a.id"
        class="overflow-hidden rounded-xl border border-line"
        @click="$emit('preview', i)"
      >
        <img :src="a.thumb || a.url" :alt="a.filename" loading="lazy" class="aspect-square w-full object-cover transition-transform duration-300 hover:scale-[1.03]" />
      </button>
    </div>

    <!-- 动画视频 -->
    <video
      v-for="v in videos" :key="v.id"
      :src="v.url"
      controls playsinline preload="metadata"
      class="w-full rounded-xl border border-line"
    />
  </div>
</template>
