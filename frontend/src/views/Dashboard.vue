<!-- 总览页：统计卡片 + 产品趋势图 + 最近预警。 -->
<template>
  <div class="page">
    <!-- 第一行：4 张统计卡片 -->
    <a-row :gutter="[16, 16]">
      <a-col :xs="12" :lg="6">
        <StatCard title="笔记数" :value="store.stats.notes" color="#2563eb" :icon="FileTextOutlined" tip="数据库里当前爬取到的笔记总数" />
      </a-col>
      <a-col :xs="12" :lg="6">
        <StatCard title="评论数" :value="store.stats.comments" color="#0891b2" :icon="MessageOutlined" tip="数据库里当前爬取到的评论总数" />
      </a-col>
      <a-col :xs="12" :lg="6">
        <StatCard title="处理率" :value="handleRateText" color="#16a34a" :icon="CheckCircleOutlined" tip="已点完成处理的笔记数 ÷ 当前笔记总数（删除的笔记不计入）" />
      </a-col>
      <a-col :xs="12" :lg="6">
        <StatCard
          title="待处理预警"
          :value="store.stats.pending_notes"
          color="#d97706"
          :icon="AlertOutlined"
          :corner="`高风险 ${store.stats.high_risk_pending_notes || 0} 条`"
          tip="中风险 + 高风险、且尚未点完成处理的笔记数（按笔记去重）"
        />
      </a-col>
    </a-row>

    <!-- 第二行：趋势图 + 最近预警 -->
    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :lg="14">
        <a-card :bordered="false">
          <template #title>
            <a-space :size="12" wrap>
              <span>舆情趋势（近 7 天）</span>
              <a-select
                v-if="store.keywords.length"
                v-model:value="selectedProduct"
                style="width: 200px"
                placeholder="选择产品"
                @change="loadTrend"
              >
                <a-select-option v-for="k in store.keywords" :key="k.id" :value="k.keyword">{{ k.keyword }}</a-select-option>
                <a-select-option value="">全部产品</a-select-option>
              </a-select>
              <a-radio-group v-model:value="chartType" size="small" @change="renderTrend">
                <a-radio-button value="bar">柱状图</a-radio-button>
                <a-radio-button value="line">折线图</a-radio-button>
              </a-radio-group>
            </a-space>
          </template>
          <div v-if="!store.keywords.length" style="padding: 24px 0">
            <a-empty description="暂无产品，请先在「采集控制」里添加产品" />
          </div>
          <div v-else ref="chartEl" style="width: 100%; height: 320px"></div>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="10">
        <a-card title="最近预警" :bordered="false">
          <a-list :data-source="recentPending" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <div class="pending-item">
                  <div class="pending-tags">
                    <RiskTag :value="item.risk_level" />
                    <SentimentTag :value="item.sentiment" />
                  </div>
                  <a class="pending-title" @click="goNote(item.content_id)">{{ item.title || '—' }}</a>
                  <div class="pending-reason muted">{{ item.reason || '—' }}</div>
                  <div class="pending-meta muted">
                    {{ item.published_at || '—' }}
                    <a @click="goNote(item.content_id)">去处理</a>
                  </div>
                </div>
              </a-list-item>
            </template>
          </a-list>
          <a-empty v-if="!recentPending.length" description="当前没有待处理的中高风险笔记" />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  FileTextOutlined, MessageOutlined, CheckCircleOutlined, AlertOutlined,
} from '@ant-design/icons-vue'
import StatCard from '../components/StatCard.vue'
import RiskTag from '../components/RiskTag.vue'
import SentimentTag from '../components/SentimentTag.vue'
import { overviewTrend, recentPendingNotes } from '../api'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const router = useRouter()

const selectedProduct = ref('')
const chartType = ref('bar') // 图表类型：默认柱状图，可切换折线图
const chartEl = ref(null)
const recentPending = ref([])
const trendData = ref({ days: [], items: [] })
let chart = null

const handleRateText = computed(() => {
  const rate = store.stats.handle_rate ?? 0
  return `${Math.round(rate * 100)}%`
})

onMounted(async () => {
  await store.refreshKeywords().catch(() => {})
  // 默认选中"最近采集过的产品"（有最新数据，打开就能看到趋势）；
  // 没有任何触发记录时，退回第一个产品。
  if (!selectedProduct.value && store.keywords.length) {
    selectedProduct.value = mostRecentlyTriggered().keyword
  }
  await Promise.allSettled([store.refreshStats(), loadTrend(), loadRecent()])
  window.addEventListener('resize', handleResize)
})

// 从产品列表里挑"最近采集过的"（按 last_triggered_at 字符串比较，格式固定为 YYYY-MM-DD HH:MM）
function mostRecentlyTriggered() {
  let best = store.keywords[0]
  for (const k of store.keywords) {
    const t = k.last_triggered_at || ''
    const bt = best.last_triggered_at || ''
    if (t > bt) best = k
  }
  return best
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})

function handleResize() {
  if (chart) chart.resize()
}

async function loadTrend() {
  const params = { days: 7 }
  if (selectedProduct.value) params.product = selectedProduct.value
  try {
    trendData.value = await overviewTrend(params)
  } catch {
    trendData.value = { days: [], items: [] }
  }
  await nextTick()
  renderTrend()
}

function renderTrend() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const days = trendData.value.days || []
  const items = trendData.value.items || []
  const isLine = chartType.value === 'line'

  let option
  if (isLine) {
    // 折线图：展示每天的中风险占比、高风险占比（各除以当天笔记总数）
    const mediumRatios = items.map((i) =>
      i.notes ? Number(((i.medium / i.notes) * 100).toFixed(1)) : 0,
    )
    const highRatios = items.map((i) =>
      i.notes ? Number(((i.high / i.notes) * 100).toFixed(1)) : 0,
    )
    option = {
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const idx = params[0].dataIndex
          const it = items[idx] || {}
          return `${days[idx]}<br/>中风险占比：${mediumRatios[idx]}%（${it.medium} 条）<br/>高风险占比：${highRatios[idx]}%（${it.high} 条）`
        },
      },
      legend: { data: ['中风险占比', '高风险占比'], bottom: 0 },
      grid: { left: 48, right: 24, top: 30, bottom: 48 },
      xAxis: { type: 'category', data: days.map((d) => d.slice(5)) },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: '中风险占比',
          type: 'line',
          data: mediumRatios,
          smooth: true,
          symbol: 'circle',
          lineStyle: { width: 2 },
          itemStyle: { color: '#faad14' },
        },
        {
          name: '高风险占比',
          type: 'line',
          data: highRatios,
          smooth: true,
          symbol: 'circle',
          lineStyle: { width: 2 },
          itemStyle: { color: '#dc2626' },
        },
      ],
    }
  } else {
    option = {
      tooltip: { trigger: 'axis' },
      legend: { data: ['笔记数', '中高风险数'], bottom: 0 },
      grid: { left: 40, right: 20, top: 30, bottom: 48 },
      xAxis: { type: 'category', data: days.map((d) => d.slice(5)) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          name: '笔记数',
          type: 'bar',
          data: items.map((i) => i.notes),
          itemStyle: { color: '#1677ff', borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 20,
        },
        {
          name: '中高风险数',
          type: 'bar',
          data: items.map((i) => i.medium_high),
          itemStyle: { color: '#faad14', borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 20,
        },
      ],
    }
  }
  chart.setOption(option, true)
}

async function loadRecent() {
  try {
    recentPending.value = await recentPendingNotes(5)
  } catch {
    recentPending.value = []
  }
}

function goNote(contentId) {
  router.push({ path: '/contents', query: { content_id: contentId } })
}
</script>

<style scoped>
.pending-item {
  width: 100%;
}
.pending-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
}
.pending-title {
  display: block;
  font-weight: 500;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pending-reason {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pending-meta {
  font-size: 12px;
  margin-top: 2px;
  display: flex;
  gap: 8px;
}
.muted {
  color: #9ca3af;
}
</style>
