// 文件职责：前端路由（主布局下的 5 个页面）。
import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'

const routes = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '总览' } },
      { path: 'collect', name: 'collect', component: () => import('../views/Collect.vue'), meta: { title: '采集控制' } },
      { path: 'contents', name: 'contents', component: () => import('../views/Contents.vue'), meta: { title: '舆情内容' } },
      { path: 'records', name: 'records', component: () => import('../views/Records.vue'), meta: { title: '处理记录' } },
      { path: 'analytics', name: 'analytics', component: () => import('../views/Analytics.vue'), meta: { title: '数据分析' } },
      { path: 'settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '设置' } },
    ],
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
