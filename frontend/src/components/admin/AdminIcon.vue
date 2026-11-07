<script setup lang="ts">
/** 后台侧的图标入口：实现已统一到 `components/common/LineIcon.vue`（站点与后台同一套），
 *  这里保留薄包装以免改动各页面的 import。 */
import LineIcon from '@/components/common/LineIcon.vue'
import type { IconName } from '@/components/common/lineIcons'

withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 16 })
</script>

<template>
  <LineIcon :name="name" :size="size" />
</template>
