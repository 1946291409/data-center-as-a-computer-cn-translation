# Data Center as a Computer Translate 

这个目录承载 GitHub Pages 站点工程，正文内容来源于仓库根目录下的 `reviewed_content/`。

## 本地使用

在 `site/` 目录下运行：

```powershell
npm install
npm run docs:dev
```

常用命令：

- `npm run site:generate`：从 `reviewed_content/` 和 `build/images/` 重新生成站点内容
- `npm run docs:build`：生成静态站点
- `npm run docs:preview`：预览构建结果

## 内容来源

- 正文：`../reviewed_content/`
- 图片：`../build/images/`
- 术语：`../terminology/terms.csv`

## 发布

GitHub Pages 使用仓库根目录下的 `.github/workflows/deploy.yml` 自动构建与部署本站点。
