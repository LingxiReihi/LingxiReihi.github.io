<script setup lang="ts">
import type { MediaAsset, MediaCategory } from '@/api/types'
import { NGrid, NGi, NImage, NModal, NPagination, NSpin, NUpload, useMessage } from 'naive-ui'
import { ref, watch } from 'vue'

import { adminMediaApi } from '@/api'
import AdminIcon from '@/components/admin/AdminIcon.vue'

const props = defineProps<{ show: boolean; kind?: string; category?: MediaCategory; selectOnUpload?: boolean }>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'select', asset: MediaAsset): void
}>()

const items = ref<MediaAsset[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const message = useMessage()

async function load() {
  loading.value = true
  try {
    const d = await adminMediaApi.list({ kind: props.kind, page: page.value, page_size: 24 })
    items.value = d.items
    total.value = d.total
  } catch (e: any) {
    message.error(e?.message || '加载素材失败')
  } finally {
    loading.value = false
  }
}
watch(() => props.show, (v) => { if (v) load() })
watch(page, load)

function choose(a: MediaAsset) {
  emit('select', a)
  emit('update:show', false)
}

async function onUpload({ file, onFinish, onError }: any) {
  try {
    const asset = await adminMediaApi.upload(file.file as File, props.category)
    message.success('上传成功')
    onFinish()
    if (props.selectOnUpload) {
      choose(asset)
      return
    }
    page.value = 1
    load()
  } catch (e: any) {
    message.error(e?.message || '上传失败')
    onError(e)
  }
}
</script>

<template>
  <n-modal
    :show="props.show" preset="card" title="选择素材" style="width: 720px; max-width: 94vw"
    @update:show="emit('update:show', $event)"
  >
    <div class="mb-4">
      <n-upload :custom-request="onUpload" :show-file-list="false" multiple @error="() => {}">
        <button class=" border border-dashed border-line px-4 py-2 text-sm text-ink-2 hover:border-brand hover:text-brand">
          ⬆ 上传新素材（图 ≤5MB / glb·zip ≤200MB / 视频 ≤200MB；obj、fbx 等请先打包成 zip）{{ selectOnUpload ? '，上传后自动选用' : '' }}
        </button>
      </n-upload>
    </div>
    <p v-if="items.length" class="mb-2 text-xs text-ink-3">已有素材 · 点击图片或「选用」使用（共 {{ total }} 张）</p>
    <n-spin :show="loading">
      <n-grid v-if="items.length" cols="3 560:4 800:6" x-gap="10" y-gap="10">
        <n-gi v-for="a in items" :key="a.id">
          <div
            class="group relative block w-full cursor-pointer overflow-hidden  border-2 border-transparent transition-colors hover:border-brand/60"
            role="button" tabindex="0"
            @click="choose(a)" @keydown.enter="choose(a)"
          >
            <n-image
              v-if="a.kind === 'image'" :src="a.thumb || a.url" object-fit="cover"
              class="!h-24 !w-full" :img-props="{ loading: 'lazy' }" :preview-disabled="true"
            />
            <div v-else class="flex h-24 w-full flex-col items-center justify-center bg-elevated text-xs text-ink-3">
              <AdminIcon :name="a.kind === 'model3d' ? 'cube' : a.kind === 'video' ? 'video' : 'doc'" :size="22" class="text-ink-3" />
              <span class="mt-1 max-w-full truncate px-1">{{ a.filename }}</span>
            </div>
            <span
              class="absolute inset-x-0 bottom-0 hidden bg-black/60 py-0.5 text-center text-xs text-white group-hover:block"
              @click.stop="choose(a)"
            >选用</span>
          </div>
        </n-gi>
      </n-grid>
      <p v-else-if="!loading" class="py-10 text-center text-sm text-ink-3">暂无素材，先上传一张吧</p>
    </n-spin>
    <div v-if="total > 24" class="mt-4 flex justify-end">
      <n-pagination v-model:page="page" :item-count="total" :page-size="24" />
    </div>
  </n-modal>
</template>
