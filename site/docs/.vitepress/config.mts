import { defineConfig } from 'vitepress'
import { chapters, sidebar } from './site-data.mjs'

const repoName = process.env.GITHUB_REPOSITORY?.split('/')[1] || 'pdf_translate'
const isCi = process.env.GITHUB_ACTIONS === 'true'

export default defineConfig({
  lang: 'zh-CN',
  title: 'DCaaC',
  description: '基于 reviewed_content 生成的中文技术书在线阅读站点。',
  base: isCi ? `/${repoName}/` : '/',
  cleanUrls: false,
  lastUpdated: true,
  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '译者说明', link: '/preface' },
      { text: '术语表', link: '/glossary' }
    ],
    search: {
      provider: 'local'
    },
    sidebar,
    outline: {
      level: [2, 3]
    },
    docFooter: {
      prev: '上一页',
      next: '下一页'
    },
    socialLinks: []
  },
  head: [
    ['meta', { name: 'viewport', content: 'width=device-width, initial-scale=1.0' }]
  ]
})
