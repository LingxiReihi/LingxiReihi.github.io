# GitHub 文件浏览器功能说明

## 功能概述

本项目已成功集成了 GitHub 文件浏览器功能，可以实时访问并显示 GitHub 仓库中的文件目录。

## 已实现的功能

### 1. PicGo 图床文件浏览页面

- **访问路径**: 点击左侧菜单的 "PicGo 图床" 按钮
- **数据源**: [https://github.com/LingxiReihi/PicGo/tree/master/im](https://github.com/LingxiReihi/PicGo/tree/master/img)
- **实时更新**: 每次访问页面时都会从 GitHub API 获取最新的文件列表

### 2. 主要特性

#### ✅ 支持的功能

- 📁 **目录导航**: 可以进入子目录查看文件
- 🔙 **返回上级**: 支持返回上一级目录
- 📄 **文件预览**: 支持查看文件内容（文本文件）
- 🔍 **文件信息**: 显示文件大小、最后更新时间
- 🌐 **外部链接**: 可以在 GitHub 中打开文件
- 🔄 **实时加载**: 从 GitHub API 实时获取数据
- 📊 **分类显示**: 文件夹和文件分开显示

#### ❌ 限制说明

- 只能访问公开的 GitHub 仓库
- GitHub API 有速率限制（每小时 60 次未认证请求）
- 无法直接修改仓库文件
- 大文件可能加载较慢

## 技术实现

### 组件结构

```bash
src/
├── components/
│   ├── GithubFileBrowser.vue    # 核心文件浏览器组件
│   └── InfoPage.vue             # 信息显示页面组件
├── components/layouts/
│   └── BaseSide.vue             # 左侧导航菜单（已更新）
└── App.vue                       # 主应用（添加页面切换逻辑）
```

### API 使用

- 使用 GitHub REST API v3
- 端点：`GET /repos/{owner}/{repo}/contents/{path}`
- 参数：
  - owner: `LingxiReihi`
  - repo: `PicGo`
  - branch: `master`
  - path: `img`

### 配置修改

如需更改要浏览的仓库，请修改以下文件中的常量：

**InfoPage.vue** (第 58-62 行):

```typescript
const OWNER = 'LingxiReihi';
const REPO = 'PicGo';
const BRANCH = 'master';
const BASE_PATH = 'img';
```

**GithubFileBrowser.vue** (第 143-147 行):

```typescript
const OWNER = 'LingxiReihi';
const REPO = 'PicGo';
const BRANCH = 'master';
const BASE_PATH = 'img';
```

## 使用方法

### 本地开发

1. 确保已安装依赖：`npm install`
2. 启动开发服务器：`npm run dev`
3. 访问 [http://localhost:5173](http://localhost:5173)
4. 点击左侧菜单 "PicGo 图床" 查看文件列表

### 部署到 GitHub Pages

1. 构建项目：`npm run build`
2. 构建产物在 `docs/` 目录
3. 推送到 GitHub 仓库的 main/master 分支
4. 在 GitHub 仓库设置中启用 GitHub Pages
5. 选择 source 为 main/master 分支，folder 为 `/docs`

## 自定义配置

### 更改仓库路径

如果要显示其他仓库或其他路径的文件，只需修改两个组件中的常量即可。

### 样式定制

- 组件使用了 Element Plus 组件库
- 样式可以通过覆盖 CSS 变量或使用 UnoCSS 工具类来定制
- 主要样式文件位置：`src/styles/`

## 常见问题

### Q: 为什么显示 "API 请求受限"？

A: GitHub 对未认证的 API 请求有限制（每小时 60 次）。解决方法：

- 等待一小时后重试
- 或者创建 GitHub Token 并在代码中添加认证头

### Q: 可以显示私有仓库吗？

A: 当前实现不支持。如需支持私有仓库，需要：

1. 创建 GitHub Personal Access Token
2. 在 API 请求中添加认证头
3. 注意不要在客户端代码中暴露 Token（需要后端代理）

### Q: 如何添加更多导航菜单项？

A: 编辑 `src/components/layouts/BaseSide.vue`：

1. 在 `<template>` 中添加新的 `<el-menu-item>`
2. 在 `<script>` 中更新 `handleMenuSelect` 函数处理新页面

## 下一步优化建议

1. ✨ 添加搜索功能
2. ✨ 添加图片缩略图预览
3. ✨ 支持文件下载
4. ✨ 添加面包屑导航
5. ✨ 支持文件排序
6. ✨ 添加分页功能
7. ✨ 支持多个仓库配置
8. ✨ 添加缓存机制减少 API 调用

## 相关资源

- [GitHub REST API 文档](https://docs.github.com/en/rest)
- [Element Plus 文档](https://element-plus.org/)
- [Vue 3 文档](https://vuejs.org/)
- [Vite 文档](https://vitejs.dev/)
