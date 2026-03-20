<script lang="ts" setup>
import { toggleDark } from "~/composables";
import { House, Picture } from "@element-plus/icons-vue";

// 发送导航事件到父组件
const emit = defineEmits<{
  navigate: [page: 'home' | 'info'];
}>();

const handleMenuSelect = (index: string) => {
  if (index === 'home' || index === 'info') {
    emit('navigate', index);
  }
};
</script>

<template>
  <el-menu 
    class="el-menu-demo" 
    mode="horizontal"
    default-active="1"
    @select="handleMenuSelect"
  >
    <el-menu-item index="home">
      <el-icon><House /></el-icon>
      <span>主页</span>
    </el-menu-item>
    
    <el-menu-item index="info">
      <el-icon><Picture /></el-icon>
      <span>PicGo 图床</span>
    </el-menu-item>

    <!-- 主题切换按钮 -->
    <el-menu-item h="full" @click="toggleDark()" style="margin-left: auto;">
      <button
        class="border-none w-full bg-transparent cursor-pointer"
        style="height: var(--ep-menu-item-height)"
      >
        <i inline-flex i="dark:ep-moon ep-sunny" />
      </button>
    </el-menu-item>
  </el-menu>
</template>
