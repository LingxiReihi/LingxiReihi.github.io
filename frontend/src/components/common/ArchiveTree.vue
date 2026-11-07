<script setup lang="ts">
import { computed, ref } from 'vue'
import { buildTree, treeDepth, type TreeNode, type ZipEntry } from '@/utils/media3d'
import { formatSize } from '@/utils/format'

const props = defineProps<{ entries: ZipEntry[]; label?: string }>()

const tree = computed(() => buildTree(props.entries ?? []))
const collapsed = ref<Set<string>>(new Set())
const allDirs = (nodes: TreeNode[]): string[] =>
  nodes.flatMap((n) => (n.dir ? [n.path, ...allDirs(n.children)] : []))

function toggle(path: string) {
  const next = new Set(collapsed.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  collapsed.value = next
}
function setAll(open: boolean) {
  collapsed.value = open ? new Set() : new Set(allDirs(tree.value))
}

const rows = computed(() => {
  const out: { node: TreeNode; depth: number }[] = []
  const walk = (nodes: TreeNode[], depth: number) => {
    for (const n of nodes) {
      out.push({ node: n, depth })
      if (n.dir && !collapsed.value.has(n.path)) walk(n.children, depth + 1)
    }
  }
  walk(tree.value, 0)
  return out
})

const fileCount = computed(() => (props.entries ?? []).length)
const totalSize = computed(() => (props.entries ?? []).reduce((s, e) => s + (e.size || 0), 0))
const dirCount = computed(() => allDirs(tree.value).length)

const ICONS: Record<string, string> = {
  '.glb': '🧊', '.gltf': '🧊', '.fbx': '🧊', '.obj': '🧊', '.blend': '🧊', '.max': '🧊',
  '.png': '🖼', '.jpg': '🖼', '.jpeg': '🖼', '.webp': '🖼', '.tga': '🖼', '.tif': '🖼',
  '.exr': '🖼', '.hdr': '🖼', '.ktx2': '🖼', '.dds': '🖼', '.mp4': '🎞',
}
const iconOf = (name: string) => {
  const dot = name.lastIndexOf('.')
  return ICONS[name.slice(dot).toLowerCase()] ?? '📄'
}
</script>

<template>
  <div class="overflow-hidden rounded-xl border border-line bg-surface">
    <div class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 text-xs text-ink-3">
      <span>{{ label ?? '压缩包内容' }} · {{ fileCount }} 个文件<template v-if="dirCount"> · {{ dirCount }} 个目录</template> · {{ treeDepth(tree) }} 层 · 解压后 {{ formatSize(totalSize) }}</span>
      <span class="ml-auto flex gap-2">
        <button class="hover:text-brand" @click="setAll(true)">全部展开</button>
        <button class="hover:text-brand" @click="setAll(false)">全部折叠</button>
      </span>
    </div>
    <div
      v-for="{ node, depth } in rows" :key="node.path"
      class="flex items-center gap-1.5 border-b border-line/50 px-3 py-1.5 text-xs last:border-0"
      :style="{ paddingLeft: `${12 + depth * 16}px` }"
    >
      <button
        v-if="node.dir" class="w-3 shrink-0 text-ink-3 hover:text-brand"
        :aria-expanded="!collapsed.has(node.path)" :aria-label="node.name"
        @click="toggle(node.path)"
      >{{ collapsed.has(node.path) ? '▸' : '▾' }}</button>
      <span v-else class="w-3 shrink-0" />
      <span class="shrink-0">{{ node.dir ? '📁' : iconOf(node.name) }}</span>
      <span :class="node.dir ? 'font-medium text-ink-2' : 'min-w-0 truncate text-ink'">{{ node.name }}</span>
      <span v-if="!node.dir" class="ml-auto shrink-0 text-ink-3">{{ formatSize(node.size ?? 0) }}</span>
    </div>
    <p v-if="!rows.length" class="px-3 py-4 text-center text-xs text-ink-3">空压缩包</p>
  </div>
</template>
