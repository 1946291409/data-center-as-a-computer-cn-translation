# 英文技术书中文译文 GitHub Pages 文档站建设需求书

## 1. 项目目标

本项目需要将已经翻译完成的一本英文技术书中文译文整理为一个可在线浏览的 GitHub Pages 文档站点。

当前译文大体按照“每章一个文件夹、每个小节一个 Markdown 文件”的方式存储。需要在尽量保留现有 Markdown 内容的基础上，完成以下工作：

1. 建立适合 GitHub 托管和 GitHub Pages 发布的仓库结构；
2. 使用 VitePress 将 Markdown 内容构建为静态文档站点；
3. 配置章节导航、首页、搜索、主题样式和基础站点信息；
4. 配置 GitHub Actions，实现 push 到 main 分支后自动构建并部署到 GitHub Pages；
5. 保证本地可预览、线上可部署、后续可持续维护。

本项目优先考虑稳定、简洁、可维护，不追求复杂前端效果。

## 2. 技术选型

采用以下技术栈：

- 文档站点生成器：VitePress
- 包管理器：npm
- 部署平台：GitHub Pages
- 自动部署：GitHub Actions
- 内容格式：Markdown
- 主要分支：main

说明：

GitHub Pages 应通过 GitHub Actions 部署。VitePress 官方文档建议在仓库 Settings → Pages 中将 Build and deployment 的 Source 设置为 GitHub Actions，并确保 VitePress 的 base 配置与仓库名匹配。GitHub Pages 也支持自定义 workflow 进行构建与发布。

参考依据：

- VitePress 官方部署文档：https://vitepress.dev/guide/deploy
- GitHub Pages 官方文档：https://docs.github.com/en/pages
- GitHub Pages 自定义 workflow 文档：https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages

## 3. 输入材料假设

当前项目中已经存在若干 Markdown 文件，结构可能类似：

```latex
book/
├─ chapter-01/
│  ├─ 1.1.md
│  ├─ 1.2.md
│  └─ 1.3.md
├─ chapter-02/
│  ├─ 2.1.md
│  └─ 2.2.md
├─ images/
│  ├─ xxx.png
│  └─ yyy.png
└─ glossary.md
```

实际目录名称可能为中文或中英文混合，例如：

```latex
第1章/
第2章/
图片/
术语表.md
```

请在实现时自动适配当前已有目录，并在不破坏原文内容的前提下整理到新的站点目录中。

## 4. 目标目录结构

请将项目整理为如下结构：

```latex
translated-book-site/
├─ docs/
│  ├─ index.md
│  ├─ preface.md
│  ├─ glossary.md
│  ├─ chapter-01/
│  │  ├─ index.md
│  │  ├─ 01-section.md
│  │  ├─ 02-section.md
│  │  └─ 03-section.md
│  ├─ chapter-02/
│  │  ├─ index.md
│  │  ├─ 01-section.md
│  │  └─ 02-section.md
│  └─ public/
│     └─ images/
├─ .vitepress/
│  ├─ config.mts
│  └─ theme/
│     └─ custom.css
├─ .github/
│  └─ workflows/
│     └─ deploy.yml
├─ package.json
├─ package-lock.json
├─ README.md
├─ LICENSE
└─ .gitignore
```

注意：

1. 如果当前仓库根目录已经存在内容，不要强制改名为 `translated-book-site`；
2. 实际实现时可以在当前仓库根目录下创建上述结构；
3. 所有可被 VitePress 处理的 Markdown 页面放入 `docs/`；
4. 图片等静态资源放入 `docs/public/images/`；
5. VitePress 配置文件放入 `.vitepress/config.mts`；
6. GitHub Actions workflow 放入 `.github/workflows/deploy.yml`。

## 5. Markdown 内容整理要求

### 5.1 文件命名

将章节和小节文件整理为稳定的英文路径，避免中文、空格和特殊符号出现在 URL 中。

推荐命名规则：

```latex
chapter-01/
chapter-02/
chapter-03/

01-section.md
02-section.md
03-section.md
```

如果能够从原文件名中提取章节编号，则按编号排序；如果不能可靠提取，则保持原始文件排序或文件系统排序。

### 5.2 标题处理

每个 Markdown 文件顶部应有一级标题。

如果原文件已经有一级标题，则保留原标题。

如果原文件没有一级标题，则根据文件名生成一级标题，例如：

```markdown
# 1.1 数据中心作为计算机
```

不要删除正文原有标题结构。

### 5.3 章节首页

每个章节文件夹下创建 `index.md`，作为章节首页。

章节首页内容可以包括：

```markdown
# 第1章 章节标题

本章包含以下小节：

- [1.1 小节标题](./01-section.md)
- [1.2 小节标题](./02-section.md)
- [1.3 小节标题](./03-section.md)
```

如果无法识别章节标题，则使用：

```markdown
# 第1章
```

### 5.4 首页

创建 `docs/index.md`，作为站点首页。

首页内容包括：

```markdown
# 中文译读笔记

本网站用于整理英文技术书的中文译文、术语表与阅读笔记。

## 阅读入口

请通过左侧目录选择章节阅读。

## 说明

本项目内容用于个人学习、翻译校对与技术阅读整理。
```

如果用户后续提供正式书名，再替换首页标题。

### 5.5 译者说明

创建 `docs/preface.md`：

```markdown
# 译者说明

本文档站用于整理英文技术书的中文译文。翻译过程中尽量保持原书技术表述、章节结构与术语一致性。

如原书涉及版权限制，本仓库内容仅用于个人学习、研究与校对，不用于商业传播。
```

### 5.6 术语表

如果原项目中已经存在术语表，将其移动或复制为：

```latex
docs/glossary.md
```

如果不存在，则创建一个空的术语表模板：

```markdown
# 术语表

| English | 中文译法 | 说明 |
|---|---|---|
|  |  |  |
```

## 6. 图片与静态资源处理要求

### 6.1 图片目录

将所有图片统一放到：

```latex
docs/public/images/
```

如图片很多，建议按章节拆分：

```latex
docs/public/images/chapter-01/
docs/public/images/chapter-02/
```

### 6.2 图片路径

Markdown 中的图片路径应统一调整为 VitePress 可识别的 public 路径。

例如，将：

```markdown
![](../images/fig1.png)
```

改为：

```markdown
![](/images/chapter-01/fig1.png)
```

或者：

```markdown
![](/images/fig1.png)
```

具体路径取决于图片实际存放位置。

### 6.3 图片文件名

如果图片文件名包含中文、空格或特殊字符，建议重命名为稳定英文名，例如：

```latex
fig-01-01.png
fig-01-02.png
```

重命名后必须同步修改 Markdown 中的引用路径。

## 7. VitePress 配置要求

创建 `.vitepress/config.mts`。

基础配置应包括：

1. 站点标题；
2. 站点描述；
3. GitHub Pages base 路径；
4. 左侧 sidebar；
5. 顶部 nav；
6. 搜索；
7. 最后更新时间；
8. 大纲层级；
9. 社交链接，可选；
10. 页脚版权说明。

示例配置：

```typescript
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: '中文译读笔记',
  description: '英文技术书中文译文整理',
  base: process.env.NODE_ENV === 'production' ? '/REPOSITORY_NAME/' : '/',

  cleanUrls: true,
  lastUpdated: true,

  themeConfig: {
    logo: undefined,

    nav: [
      { text: '首页', link: '/' },
      { text: '译者说明', link: '/preface' },
      { text: '术语表', link: '/glossary' }
    ],

    sidebar: [
      {
        text: '开始阅读',
        items: [
          { text: '首页', link: '/' },
          { text: '译者说明', link: '/preface' },
          { text: '术语表', link: '/glossary' }
        ]
      },
      {
        text: '第1章',
        collapsed: false,
        items: [
          { text: '章节首页', link: '/chapter-01/' },
          { text: '1.1 小节标题', link: '/chapter-01/01-section' },
          { text: '1.2 小节标题', link: '/chapter-01/02-section' }
        ]
      }
    ],

    search: {
      provider: 'local'
    },

    outline: {
      level: [2, 3],
      label: '本页目录'
    },

    lastUpdated: {
      text: '最后更新'
    },

    docFooter: {
      prev: '上一篇',
      next: '下一篇'
    },

    footer: {
      message: '仅用于个人学习、研究与翻译校对。',
      copyright: 'Copyright © 2026'
    }
  }
})
```

重要：

请将 `REPOSITORY_NAME` 替换为实际 GitHub 仓库名。

如果仓库未来使用自定义域名，base 可以调整为 `/`。

## 8. 侧边栏生成要求

请尽量自动生成 sidebar，避免手工维护大量章节。

如果项目较小，可以直接在 `config.mts` 中写死 sidebar。

如果章节很多，请新增脚本生成 sidebar，例如：

```latex
scripts/generate-sidebar.mjs
```

生成逻辑：

1. 扫描 `docs/chapter-*` 文件夹；
2. 按章节编号排序；
3. 读取每个 Markdown 文件的一级标题；
4. 生成 sidebar 配置；
5. 写入 `.vitepress/sidebar.mts`；
6. 在 `config.mts` 中导入 sidebar。

可选结构：

```typescript
// .vitepress/sidebar.mts
export const sidebar = [
  {
    text: '第1章',
    collapsed: false,
    items: [
      { text: '章节首页', link: '/chapter-01/' },
      { text: '1.1 小节标题', link: '/chapter-01/01-section' }
    ]
  }
]
```

如果实现自动生成脚本，需要在 `package.json` 中增加：

```json
{
  "scripts": {
    "docs:prepare": "node scripts/generate-sidebar.mjs",
    "docs:dev": "npm run docs:prepare && vitepress dev docs",
    "docs:build": "npm run docs:prepare && vitepress build docs",
    "docs:preview": "vitepress preview docs"
  }
}
```

## 9. 样式要求

创建 `.vitepress/theme/custom.css`，进行轻量样式优化。

要求：

1. 正文字体适合中文阅读；
2. 行距适中；
3. 页面宽度适合长文阅读；
4. 表格显示清晰；
5. 代码块保持默认或轻微优化；
6. 不要引入复杂 UI 框架。

示例：

```css
:root {
  --vp-font-family-base: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  --vp-font-family-mono: "Consolas", "SFMono-Regular", monospace;
}

.vp-doc p {
  line-height: 1.9;
}

.vp-doc li {
  line-height: 1.8;
}

.vp-doc table {
  font-size: 14px;
}

.vp-doc img {
  display: block;
  margin: 1.5rem auto;
  max-width: 100%;
}
```

如果 VitePress 主题需要引入 CSS，请创建：

```latex
.vitepress/theme/index.ts
```

内容：

```typescript
import DefaultTheme from 'vitepress/theme'
import './custom.css'

export default DefaultTheme
```

## 10. package.json 要求

创建或更新 `package.json`：

```json
{
  "name": "translated-book-site",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "docs:dev": "vitepress dev docs",
    "docs:build": "vitepress build docs",
    "docs:preview": "vitepress preview docs"
  },
  "devDependencies": {
    "vitepress": "latest"
  }
}
```

如果实现 sidebar 自动生成脚本，则改为：

```json
{
  "name": "translated-book-site",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "docs:prepare": "node scripts/generate-sidebar.mjs",
    "docs:dev": "npm run docs:prepare && vitepress dev docs",
    "docs:build": "npm run docs:prepare && vitepress build docs",
    "docs:preview": "vitepress preview docs"
  },
  "devDependencies": {
    "vitepress": "latest"
  }
}
```

## 11. GitHub Actions 部署要求

创建 `.github/workflows/deploy.yml`。

要求：

1. push 到 main 分支后自动部署；
2. 支持手动触发；
3. 使用 Node.js 20 或更高版本；
4. 安装依赖；
5. 构建 VitePress；
6. 上传构建产物；
7. 部署到 GitHub Pages。

参考 workflow：

```yaml
name: Deploy VitePress site to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Setup Pages
        uses: actions/configure-pages@v5

      - name: Install dependencies
        run: npm ci

      - name: Build with VitePress
        run: npm run docs:build

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: docs/.vitepress/dist

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}

    needs: build
    runs-on: ubuntu-latest

    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

部署前需要在 GitHub 仓库中设置：

```latex
Settings → Pages → Build and deployment → Source → GitHub Actions
```

## 12. README 要求

创建或更新 `README.md`。

README 应包括：

~~~markdown
# 中文译读笔记

本仓库用于整理英文技术书的中文译文、术语表与阅读笔记。

## 本地预览

```bash
npm install
npm run docs:dev
~~~

## 构建

```bash
npm run docs:build
npm run docs:preview
```

## 部署

本项目通过 GitHub Actions 自动部署到 GitHub Pages。

推送到 main 分支后，GitHub Actions 会自动构建并发布。

## 内容说明

本项目内容用于个人学习、研究与翻译校对。如原书涉及版权限制，请勿用于商业传播或未经授权的公开发布。

~~~plain
## 13. .gitignore 要求

创建 `.gitignore`：

```gitignore
node_modules
docs/.vitepress/cache
docs/.vitepress/dist
.DS_Store
*.log
~~~

## 14. LICENSE 要求

如果用户没有明确指定开源协议，不要擅自使用 MIT、Apache、GPL 等开源协议。

请创建一个保守的 `LICENSE` 或 `NOTICE` 文件，内容为：

```latex
This repository is for personal study, translation review, and technical reading notes.

The translated content may be subject to the copyright of the original book.
Do not redistribute, republish, or use it commercially without proper authorization.
```

如果用户后续确认原书允许公开翻译，再替换为合适的开源协议或内容许可。

## 15. 版权与公开性注意事项

由于本项目涉及英文书籍的完整中文译文，请不要默认假设可以公开发布。

需要在 README 和站点页脚中保留版权提醒：

```latex
仅用于个人学习、研究与翻译校对。
```

如果仓库设置为 public，GitHub Pages 内容通常也是公开可访问的。请提醒用户确认原书版权、翻译授权或开放许可情况。

如果版权不明确，建议：

1. 使用 private 仓库；
2. 暂不启用公开 GitHub Pages；
3. 或只发布目录、术语表、阅读笔记，不发布完整译文。

## 16. 本地运行命令

完成后应支持以下命令：

```bash
npm install
npm run docs:dev
npm run docs:build
npm run docs:preview
```

期望结果：

1. `npm run docs:dev` 可以启动本地预览；
2. `npm run docs:build` 可以成功生成静态文件；
3. `npm run docs:preview` 可以预览构建结果；
4. push 到 main 后，GitHub Actions 可以成功部署。

## 17. 验收标准

项目完成后，应满足以下标准：

### 17.1 文件结构

- 存在 `docs/index.md`
- 存在 `docs/preface.md`
- 存在 `docs/glossary.md`
- 存在 `.vitepress/config.mts`
- 存在 `.github/workflows/deploy.yml`
- 存在 `package.json`
- 存在 `README.md`
- 存在 `.gitignore`

### 17.2 内容展示

- 首页可以正常访问；
- 左侧目录可以按章节展开；
- 每个章节和小节可以正常跳转；
- Markdown 标题、段落、列表、表格正常渲染；
- 图片可以正常显示；
- 站内搜索可用；
- 右侧本页目录可用；
- 上一篇、下一篇导航可用。

### 17.3 构建与部署

- `npm install` 成功；
- `npm run docs:dev` 成功；
- `npm run docs:build` 成功；
- `npm run docs:preview` 成功；
- GitHub Actions workflow 运行成功；
- GitHub Pages 页面可以访问。

### 17.4 路径与兼容性

- GitHub Pages 的 base 路径正确；
- 刷新页面不会 404；
- 图片路径在线上环境正常；
- 文件名和 URL 不包含中文空格和特殊符号；
- 移动端基本可读。

## 18. 实现顺序建议

请按以下顺序执行：

1. 检查当前目录结构和 Markdown 文件数量；
2. 创建 VitePress 基础项目文件；
3. 整理 Markdown 到 `docs/`；
4. 复制或移动图片到 `docs/public/images/`；
5. 修正 Markdown 中的图片路径；
6. 创建首页、译者说明、术语表；
7. 配置 `.vitepress/config.mts`；
8. 配置样式文件；
9. 配置 `package.json`；
10. 配置 GitHub Actions；
11. 本地运行 `npm install`；
12. 本地运行 `npm run docs:build`；
13. 修复构建错误；
14. 提交代码；
15. 推送到 GitHub；
16. 在 GitHub Pages 设置中选择 GitHub Actions；
17. 检查线上页面。

## 19. 不要做的事情

请不要做以下操作：

1. 不要删除原始 Markdown 文件，除非已经确认内容成功迁移；
2. 不要擅自改写译文正文；
3. 不要把译文内容改成摘要；
4. 不要引入复杂数据库、后端服务或登录系统；
5. 不要使用大型前端框架重写页面；
6. 不要默认使用 MIT、Apache 等开源协议；
7. 不要忽略版权说明；
8. 不要把图片路径写成只能在本地生效的绝对路径；
9. 不要在 URL 中使用中文、空格或特殊符号；
10. 不要把构建产物 `dist` 提交到仓库，除非后续明确要求。

## 20. 最终交付物

最终需要交付：

1. 一个可运行的 VitePress 文档站；
2. 整理后的 Markdown 文档结构；
3. 正常显示的章节导航；
4. 正常显示的图片资源；
5. GitHub Actions 自动部署配置；
6. README 使用说明；
7. 版权与使用限制说明；
8. 本地构建通过的项目状态。