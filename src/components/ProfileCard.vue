<template>
  <div class="profile-container">
    <el-card class="profile-card" shadow="hover">
      <div class="profile-content">
        <!-- 头像部分 -->
        <div class="avatar-section">
          <div class="avatar-wrapper">
            <img 
              :src="profileConfig.basic.avatar" 
              alt="头像" 
              class="avatar"
            />
          </div>
        </div>

        <!-- 信息部分 -->
        <div class="info-section">
          <div class="nickname">
            <h2>{{ profileConfig.basic.nickname }}</h2>
            <el-tag type="danger" size="small" class="星座-tag">{{ profileConfig.basic.constellation }}</el-tag>
          </div>

          <p class="signature">
            {{ profileConfig.signature.icon }} {{ profileConfig.signature.text }}
          </p>

          <div class="introduction">
            <p v-for="(paragraph, index) in profileConfig.introduction.paragraphs" :key="index">
              {{ paragraph }}
            </p>
          </div>

          <!-- 社交链接 -->
          <div class="social-links">
            <el-button 
              :type="profileConfig.social.github.type" 
              circle 
              size="large"
              @click="openLink(profileConfig.social.github.url)"
            >
              <el-icon><Platform /></el-icon>
            </el-button>
            <el-button 
              :type="profileConfig.social.message.type" 
              circle 
              size="large"
              @click="openLink(profileConfig.social.message.url)"
            >
              <el-icon><Message /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { profileConfig } from '../config/profile';

const openLink = (url: string) => {
  window.open(url, '_blank');
};
</script>

<style scoped>
.profile-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 100px);
  padding: 20px;
}

.profile-card {
  width: 100%;
  max-width: 900px;
  border-radius: 20px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.profile-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
}

.profile-content {
  display: flex;
  gap: 40px;
  padding: 40px;
  align-items: center;
}

/* 头像部分 */
.avatar-section {
  flex: 0 0 300px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.avatar-wrapper {
  position: relative;
  width: 280px;
  height: 280px;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
  transition: transform 0.3s ease;
}

.avatar-wrapper:hover {
  transform: scale(1.05);
}

.avatar {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 信息部分 */
.info-section {
  flex: 1;
  text-align: left;
}

.nickname {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
}

.nickname h2 {
  font-size: 2.5rem;
  font-weight: bold;
  margin: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.星座-tag {
  font-size: 1rem;
  padding: 5px 15px;
  border-radius: 20px;
}

.signature {
  font-size: 1.1rem;
  color: #666;
  margin: 20px 0;
  font-style: italic;
  line-height: 1.6;
  padding-left: 15px;
  border-left: 4px solid #667eea;
}

.introduction {
  margin: 25px 0;
  line-height: 1.8;
  color: #444;
}

.introduction p {
  margin: 10px 0;
}

.mt-2 {
  margin-top: 0.5rem;
}

.social-links {
  display: flex;
  gap: 15px;
  margin-top: 30px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .profile-content {
    flex-direction: column;
    gap: 30px;
    padding: 25px;
  }

  .avatar-section {
    flex: 0 0 auto;
  }

  .avatar-wrapper {
    width: 200px;
    height: 200px;
  }

  .nickname h2 {
    font-size: 2rem;
  }

  .info-section {
    text-align: center;
  }

  .signature {
    border-left: none;
    border-bottom: 4px solid #667eea;
    padding-left: 0;
    padding-bottom: 10px;
  }

  .social-links {
    justify-content: center;
  }
}

@media (max-width: 480px) {
  .avatar-wrapper {
    width: 160px;
    height: 160px;
  }

  .nickname h2 {
    font-size: 1.5rem;
  }

  .signature {
    font-size: 1rem;
  }

  .introduction {
    font-size: 0.95rem;
  }
}
</style>
