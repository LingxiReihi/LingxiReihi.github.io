<template>
  <div class="info-page min-h-screen p-6">
    <div class="max-w-6xl mx-auto">
      <!-- 页面标题 -->
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-center mb-2">
          📁 PicGo 图床文件管理
        </h1>
        <p class="text-center text-gray-600">
          实时查看 GitHub 仓库中的图片文件
        </p>
      </div>

      <!-- 仓库信息卡片 -->
      <el-card class="mb-6" shadow="hover">
        <template #header>
          <div class="flex items-center justify-between">
            <span class="font-semibold">仓库信息</span>
            <el-tag type="success">在线</el-tag>
          </div>
        </template>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p class="text-sm text-gray-500">仓库所有者</p>
            <p class="font-medium">{{ OWNER }}</p>
          </div>
          <div>
            <p class="text-sm text-gray-500">仓库名称</p>
            <p class="font-medium">{{ REPO }}</p>
          </div>
          <div>
            <p class="text-sm text-gray-500">分支</p>
            <p class="font-medium">{{ BRANCH }}</p>
          </div>
          <div>
            <p class="text-sm text-gray-500">基础路径</p>
            <p class="font-medium">{{ BASE_PATH }}</p>
          </div>
        </div>
      </el-card>

      <!-- 文件浏览器组件 -->
      <GithubFileBrowser />
    </div>
  </div>
</template>

<script lang="ts" setup>
// GithubFileBrowser 已在全局注册

// 仓库配置
const OWNER = 'LingxiReihi';
const REPO = 'PicGo';
const BRANCH = 'master';
const BASE_PATH = 'img';
</script>

<style scoped>
.info-page {
  background-color: var(--ep-bg-color);
}
</style>
