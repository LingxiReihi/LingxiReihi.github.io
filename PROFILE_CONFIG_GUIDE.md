# 个人资料卡片配置指南

## 📖 配置文件位置

配置文件位于：`src/config/profile.ts`

## 🔧 修改内容

### 1. 基本信息 (basic)

```typescript
basic: {
  nickname: 'Reihi',        // 昵称
  constellation: '天蝎座',   // 星座
  avatar: '/images/avatar.jpg'  // 头像图片路径
}
```

**修改说明：**
- `nickname`: 修改为你的昵称
- `constellation`: 修改为你的星座
- `avatar`: 头像图片路径，需要将图片放在 `public/images/` 目录下

### 2. 个性签名 (signature)

```typescript
signature: {
  text: '生活不止眼前的苟且，还有诗和远方的田野',
  icon: '✨'  // 可选，签名前的图标
}
```

**修改说明：**
- `text`: 修改为你的个性签名
- `icon`: 可选，签名前显示的 emoji 或图标

### 3. 个人简介 (introduction)

```typescript
introduction: {
  paragraphs: [
    '你好呀！我是一名热爱技术和创造的开发者。喜欢探索新鲜事物，对世界充满好奇。',
    '🎨 热爱设计 | 💻 专注开发 | 📸 喜欢摄影',
    '相信技术可以改变生活，用代码创造美好。'
  ]
}
```

**修改说明：**
- `paragraphs`: 字符串数组，每段文字会单独成行
- 可以添加或删除段落
- 支持使用 emoji

### 4. 技能标签 (skills)

```typescript
skills: {
  items: [
    '🎨 热爱设计',
    '💻 专注开发',
    '📸 喜欢摄影'
  ]
}
```

**修改说明：**
- `items`: 技能标签数组
- 每个标签可以包含 emoji
- 可以根据需要添加或删除

### 5. 社交链接 (social)

```typescript
social: {
  github: {
    url: 'https://github.com/LingxiReihi',
    icon: 'Platform',
    type: 'primary'  // 按钮类型：primary | success | warning | danger | info
  },
  message: {
    url: '#',
    icon: 'Message',
    type: 'success'
  }
}
```

**修改说明：**
- `url`: 社交链接地址
- `icon`: Element Plus 图标名称（参考 Element Plus 文档）
- `type`: 按钮样式类型
  - `primary`: 主要（蓝色）
  - `success`: 成功（绿色）
  - `warning`: 警告（橙色）
  - `danger`: 危险（红色）
  - `info`: 信息（灰色）

## 🎨 可用图标

Element Plus 提供了丰富的图标，常用的有：
- `Platform` - 平台（用于 GitHub）
- `Message` - 消息
- `User` - 用户
- `Star` - 星星
- `ChatDotRound` - 聊天
- `Camera` - 相机
- `VideoCamera` - 摄像机

查看完整图标列表：https://element-plus.org/zh-CN/component/icon.html

## 💡 修改示例

### 示例 1：修改 GitHub 链接

```typescript
social: {
  github: {
    url: 'https://github.com/你的用户名',  // 修改这里
    icon: 'Platform',
    type: 'primary'
  }
}
```

### 示例 2：添加新的简介段落

```typescript
introduction: {
  paragraphs: [
    '第一段简介',
    '第二段简介',
    '第三段简介'  // 添加新段落
  ]
}
```

### 示例 3：更换头像

1. 将新头像图片放到 `public/images/` 目录
2. 修改配置文件：

```typescript
basic: {
  avatar: '/images/你的新头像.jpg'  // 修改路径
}
```

## 🚀 实时预览

修改配置文件后，Vite 会自动热更新，无需刷新页面即可查看效果。

开发服务器地址：http://localhost:5173

## 📝 注意事项

1. 图片文件需要放在 `public/images/` 目录下
2. 配置文件修改后会自动保存并更新
3. 确保 TypeScript 类型正确，不要修改类型定义
4. 社交链接的 `type` 只能是：'primary' | 'success' | 'warning' | 'danger' | 'info'

## 🎯 快速开始

1. 打开 `src/config/profile.ts`
2. 修改对应的配置项
3. 保存文件
4. 在浏览器中查看效果

祝你使用愉快！🎉
