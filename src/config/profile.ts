// 个人资料卡片配置信息
export interface ProfileConfig {
    // 基本信息
    basic: {
        nickname: string
        constellation: string
        avatar: string
    }

    // 个性签名
    signature: {
        text: string
        icon?: string
    }

    // 个人简介
    introduction: {
        paragraphs: string[]
    }

    // 技能标签
    skills: {
        items: string[]
        icon?: string
    }

    // 社交链接
    social: {
        github: {
            url: string
            icon: string
            type: 'primary' | 'success' | 'warning' | 'danger' | 'info'
        }
        message: {
            url: string
            icon: string
            type: 'primary' | 'success' | 'warning' | 'danger' | 'info'
        }
    }
}

// 个人资料配置
export const profileConfig: ProfileConfig = {
    basic: {
        nickname: '泠曦れいひ',
        constellation: '天秤座',
        avatar: '/images/avatar.jpg'
    },

    signature: {
        text: '生活不止眼前的苟且，还有诗和远方的田野',
        icon: '✨'
    },

    introduction: {
        paragraphs: [
            '你好呀！我是一名热爱技术和创造的开发者。喜欢探索新鲜事物，对世界充满好奇。',
            '🎨 热爱设计 | 💻 专注开发 | 📸 喜欢摄影',
            '相信技术可以改变生活，用代码创造美好。'
        ]
    },

    skills: {
        items: [
            '🎨 热爱设计',
            '💻 专注开发',
            '📸 喜欢摄影'
        ]
    },

    social: {
        github: {
            url: 'https://github.com/LingxiReihi',
            icon: 'Platform',
            type: 'primary'
        },
        message: {
            url: '#',
            icon: 'Message',
            type: 'success'
        }
    }
}
