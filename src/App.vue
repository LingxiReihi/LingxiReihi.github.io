<template>
  <el-config-provider namespace="ep">
    <BaseHeader @navigate="handleNavigation" />
    <div class="flex main-container">
      <div w="full" py="4">
        <!-- 主页内容 -->
        <div v-if="currentPage === 'home'">
          <Logos my="4" />
          <HelloWorld
            msg="Hello, this is Reihi's personal page.
          And this page is in building."
          />
        </div>
        <!-- 信息显示页面 -->
        <div v-else-if="currentPage === 'info'">
          <InfoPage />
        </div>
      </div>
    </div>
  </el-config-provider>
</template>

<script lang="ts" setup>
import { ref } from "vue";

type Page = 'home' | 'info';
const currentPage = ref<Page>('home');

const handleNavigation = (page: Page) => {
  currentPage.value = page;
};
</script>

<style>
#app {
  text-align: center;
  color: var(--ep-text-color-primary);
}

.main-container {
  height: calc(100vh - var(--ep-menu-item-height) - 3px);
}
</style>
