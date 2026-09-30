<!-- 主布局：左侧菜单 + 顶部栏 + 内容区 -->
<template>
                                             
  <a-layout style="min-height: 100vh">
    <a-layout-sider theme="light" width="220" breakpoint="lg" collapsed-width="64">
      <div class="brand">
        <span class="brand-dot"></span>
        <span class="brand-text">舆情公关平台</span>
      </div>
      <a-menu mode="inline" :selected-keys="[activeMenu]" @click="onMenuClick">
        <a-menu-item key="dashboard"><template #icon><DashboardOutlined /></template>总览</a-menu-item>
        <a-menu-item key="collect"><template #icon><CloudDownloadOutlined /></template>采集控制</a-menu-item>
        <a-menu-item key="contents"><template #icon><ReadOutlined /></template>舆情内容</a-menu-item>
        <a-menu-item key="records"><template #icon><FileDoneOutlined /></template>处理记录</a-menu-item>
        <a-menu-item key="analytics"><template #icon><BarChartOutlined /></template>数据分析</a-menu-item>
        <a-menu-item key="settings"><template #icon><SettingOutlined /></template>设置</a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="topbar">
        <div class="topbar-title">{{ pageTitle }}</div>
        <a-space>
          <a-tag :color="store.info.collect_mode === 'opencli' ? 'green' : 'orange'">
            {{ store.info.collect_mode === 'opencli' ? '真实抓取' : '模拟数据' }}
          </a-tag>
          <a-tag :color="store.info.llm_configured ? 'blue' : 'default'">
            {{ store.info.llm_configured ? store.info.llm_model : '规则模式' }}
          </a-tag>
          <a-button size="small" @click="refreshAll">
            <template #icon><ReloadOutlined /></template>刷新
          </a-button>
        </a-space>
      </a-layout-header>
      <a-layout-content class="content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DashboardOutlined,
  CloudDownloadOutlined,
  ReadOutlined,
  FileDoneOutlined,
  BarChartOutlined,
  SettingOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { useAppStore } from '../stores/app'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const pageTitle = computed(() => route.meta.title || '')
const activeMenu = computed(() => route.name)

onMounted(() => {
  store.refreshInfo().catch(() => {})
})

function onMenuClick({ key }) {
  if (key !== route.name) router.push({ name: key })
}

async function refreshAll() {
  await Promise.allSettled([store.refreshInfo(), store.refreshStats()])
}
</script>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 20px;
  font-weight: 600;
}
.brand-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--brand);
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #eceef1;
}
.topbar-title {
  font-size: 16px;
  font-weight: 600;
}
.content {
  background: #f5f6f8;
}
</style>
