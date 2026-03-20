<template>
  <div class="github-file-browser p-4">
    <h2 class="text-xl font-bold mb-4">GitHub 仓库文件浏览器</h2>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading text-center py-8">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p class="mt-2">正在加载文件列表...</p>
    </div>

    <!-- 错误提示 -->
    <div v-else-if="error" class="error text-center py-8 text-red-500">
      <el-icon :size="32"><Warning /></el-icon>
      <p class="mt-2">{{ error }}</p>
      <el-button type="primary" @click="fetchFiles" class="mt-4">重试</el-button>
    </div>

    <!-- 文件列表 -->
    <div v-else class="file-list">
      <!-- 返回上一级按钮 -->
      <el-button 
        v-if="currentPath" 
        @click="goUp" 
        icon="ArrowLeft"
        size="small"
        class="mb-3"
      >
        返回上一级
      </el-button>

      <!-- 当前路径面包屑 -->
      <div class="breadcrumb mb-4 text-sm text-gray-600">
        当前路径：{{ currentPath || '根目录' }}
      </div>

      <!-- 文件夹列表 -->
      <div v-if="directories.length > 0" class="directories mb-4">
        <h3 class="text-lg font-semibold mb-2">📁 文件夹</h3>
        <el-table :data="directories" style="width: 100%" size="small">
          <el-table-column prop="name" label="名称">
            <template #default="{ row }">
              <div class="flex items-center cursor-pointer hover:text-blue-500" @click="enterDirectory(row)">
                <el-icon><Folder /></el-icon>
                <span class="ml-2">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="最后更新时间" width="180">
            <template #default="{ row }">
              {{ formatDate(row.updated_at) }}
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 文件列表 -->
      <div v-if="files.length > 0">
        <h3 class="text-lg font-semibold mb-2">📄 文件</h3>
        <el-table :data="files" style="width: 100%" size="small">
          <el-table-column prop="name" label="名称">
            <template #default="{ row }">
              <div class="flex items-center">
                <el-icon v-if="isImageFile(row.name)"><Picture /></el-icon>
                <el-icon v-else><Document /></el-icon>
                <span class="ml-2">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="100">
            <template #default="{ row }">
              {{ formatSize(row.size) }}
            </template>
          </el-table-column>
          <el-table-column label="最后更新时间" width="180">
            <template #default="{ row }">
              {{ formatDate(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button 
                link 
                type="primary" 
                size="small"
                @click="viewFile(row)"
              >
                查看
              </el-button>
              <el-button 
                link 
                type="success" 
                size="small"
                @click="openInNewTab(row)"
              >
                新窗口
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 空目录提示 -->
      <div v-if="directories.length === 0 && files.length === 0" class="empty text-center py-8 text-gray-500">
        <el-icon :size="48"><FolderOpened /></el-icon>
        <p class="mt-2">此目录为空</p>
      </div>
    </div>

    <!-- 文件内容对话框 -->
    <el-dialog
      v-model="fileDialogVisible"
      :title="selectedFile?.name"
      width="80%"
      top="5vh"
    >
      <!-- 图片预览 -->
      <div v-if="isImage && fileContent" class="image-preview text-center">
        <img :src="fileContent" alt="图片预览" class="max-w-full rounded shadow-lg" />
        <p class="mt-4 text-sm text-gray-600">{{ selectedFile?.name }}</p>
      </div>
      
      <!-- 文本内容 -->
      <div v-else-if="fileContent" class="file-content">
        <pre class="bg-gray-100 p-4 rounded overflow-auto max-h-96"><code>{{ fileContent }}</code></pre>
      </div>
      
      <!-- 加载状态 -->
      <div v-else-if="fileLoading" class="text-center py-4">
        <el-icon class="is-loading"><Loading /></el-icon>
        <p>正在加载文件内容...</p>
      </div>
      
      <!-- 无法预览 -->
      <div v-else class="text-center py-4 text-gray-500">
        <p>该文件类型不支持预览</p>
      </div>
      
      <template #footer>
        <el-button @click="fileDialogVisible = false">关闭</el-button>
        <el-button 
          type="primary" 
          @click="openInNewTab(selectedFile)"
          v-if="selectedFile"
        >
          在 GitHub 中查看
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from 'vue';
import { 
  Loading, 
  Warning, 
  Folder, 
  FolderOpened, 
  Document,
  ArrowLeft,
  Picture
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

// 仓库信息
const OWNER = 'LingxiReihi';
const REPO = 'PicGo';
const BRANCH = 'master';
const BASE_PATH = 'img';

// 状态
const loading = ref(false);
const error = ref('');
const currentPath = ref('');
const directories = ref<any[]>([]);
const files = ref<any[]>([]);
const fileDialogVisible = ref(false);
const selectedFile = ref<any>(null);
const fileContent = ref('');
const fileLoading = ref(false);
const isImage = ref(false);

// 获取文件列表
const fetchFiles = async () => {
  loading.value = true;
  error.value = '';
  
  try {
    const path = currentPath.value ? `${BASE_PATH}/${currentPath.value}` : BASE_PATH;
    const url = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}?ref=${BRANCH}`;
    
    const response = await fetch(url);
    
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('路径不存在或仓库为私有');
      } else if (response.status === 403) {
        throw new Error('API 请求受限，请稍后再试');
      }
      throw new Error(`请求失败：${response.status}`);
    }
    
    const data = await response.json();
    
    // 分类文件和目录
    directories.value = data.filter((item: any) => item.type === 'dir');
    files.value = data.filter((item: any) => item.type === 'file');
    
  } catch (err: any) {
    error.value = err.message || '加载失败';
    ElMessage.error(error.value);
  } finally {
    loading.value = false;
  }
};

// 进入目录
const enterDirectory = (dir: any) => {
  currentPath.value = currentPath.value ? `${currentPath.value}/${dir.name}` : dir.name;
  fetchFiles();
};

// 返回上一级
const goUp = () => {
  const parts = currentPath.value.split('/');
  parts.pop();
  currentPath.value = parts.join('/');
  fetchFiles();
};

// 查看文件
const viewFile = async (file: any) => {
  selectedFile.value = file;
  fileDialogVisible.value = true;
  fileLoading.value = true;
  fileContent.value = '';
  isImage.value = false;
  
  try {
    // 判断是否为图片文件
    const imageExtensions = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'];
    const fileExtension = file.name.split('.').pop()?.toLowerCase() || '';
    isImage.value = imageExtensions.includes(fileExtension);
    
    if (isImage.value) {
      // 图片直接使用 download_url
      fileContent.value = file.download_url;
    } else {
      // 文本文件获取内容
      const response = await fetch(file.download_url);
      const content = await response.text();
      fileContent.value = content;
    }
  } catch (err) {
    ElMessage.error('无法加载文件内容');
  } finally {
    fileLoading.value = false;
  }
};

// 在新窗口打开
const openInNewTab = (file: any) => {
  window.open(file.html_url, '_blank');
};

// 格式化日期
const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// 格式化文件大小
const formatSize = (size: number) => {
  if (size < 1024) return size + ' B';
  if (size < 1024 * 1024) return (size / 1024).toFixed(2) + ' KB';
  return (size / (1024 * 1024)).toFixed(2) + ' MB';
};

// 判断是否为图片文件
const isImageFile = (filename: string) => {
  const imageExtensions = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'];
  const fileExtension = filename.split('.').pop()?.toLowerCase() || '';
  return imageExtensions.includes(fileExtension);
};

// 初始化
onMounted(() => {
  fetchFiles();
});
</script>

<style scoped>
.github-file-browser {
  max-width: 1200px;
  margin: 0 auto;
}

.loading, .error, .empty {
  color: var(--ep-text-color-secondary);
}

.breadcrumb {
  padding: 8px 12px;
  background-color: var(--ep-fill-color-light);
  border-radius: 4px;
}

.file-content code {
  font-family: 'Courier New', Courier, monospace;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.image-preview img {
  max-height: 70vh;
  object-fit: contain;
}
</style>
