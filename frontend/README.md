# 前端管理台

舆情公关多 Agent 平台的第一期前端，包含 5 个页面：总览、采集控制、舆情内容、预警中心、设置。

## 技术栈

Vue 3 + Vite + Pinia + Vue Router + Axios + Ant Design Vue。

## 目录结构

```text
frontend/
  vite.config.js        开发服务器和 /api 代理配置
  package.json          npm 依赖和脚本
  src/
    api/                axios 实例和接口封装
    stores/             Pinia 状态管理
    router/             路由
    layout/             侧边栏布局
    components/         统计卡、情感标签、风险标签
    views/              5 个页面
    styles/             全局样式
```

## 运行

先确保后端已经在 8000 端口运行，然后在 `frontend` 目录执行：

```bash
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173

Vite 会把 `/api` 请求代理到 http://127.0.0.1:8000，所以前端不用改接口地址。

## 构建

```bash
npm run build
```

产物输出到 `dist` 目录。

## 页面说明

- 总览：统计卡片、情感分布、最近预警。
- 采集控制：手动触发采集（关键词 / 笔记 URL），关键词管理。
- 舆情内容：笔记列表，按情感和风险筛选，抽屉查看正文和评论。
- 预警中心：预警列表，按状态和级别筛选，标记已处理。
- 设置：运行状态展示，系统配置 key-value 编辑。

## 常用修改

| 位置 | 说明 |
|------|------|
| `vite.config.js` | 后端不是 8000 端口时修改 `proxy.target` |
| `src/styles/global.css` | `--brand` 主题强调色 |
| `src/components/SentimentTag.vue` | 情感标签颜色 |
| `src/components/RiskTag.vue` | 风险标签颜色 |

修改前端配置后需要重启 `npm run dev`。
