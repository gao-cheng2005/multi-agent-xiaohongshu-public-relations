<!-- 数据分析：每个产品单独一份用户问题分析（ECharts 可视化 + Agent 优化建议）。 -->
<template>
  <div class="page">
    <!-- 产品问题分析 -->
    <a-card :bordered="false" title="产品问题分析">
      <a-space style="margin-bottom: 16px" wrap>
        <a-select v-model:value="selectedProduct" style="width: 220px" placeholder="选择产品" @change="onProductChange">
          <a-select-option v-for="k in store.keywords" :key="k.id" :value="k.keyword">{{ k.keyword }}</a-select-option>
        </a-select>
        <a-button :loading="loadingAnalysis" @click="loadAnalysis">刷新</a-button>
        <a-popconfirm title="将由 Agent 归并待确认维度到正式维度，是否继续？" ok-text="合并" cancel-text="取消" @confirm="onMerge">
          <a-button :disabled="!unconfirmedCount">合并待确认维度({{ unconfirmedCount }})</a-button>
        </a-popconfirm>
      </a-space>

      <a-empty v-if="!selectedProduct" description="请先选择产品" />

      <template v-else>
        <!-- ① 概览卡片 -->
        <a-row :gutter="16" style="margin-bottom: 16px">
          <a-col :xs="12" :lg="6"><StatCard title="爬到的笔记数" :value="analysis?.notes ?? 0" color="#1677ff" :icon="FileTextOutlined" tip="该产品下爬取到的笔记总数（标题+正文+评论都被用来分析）" /></a-col>
          <a-col :xs="12" :lg="6"><StatCard title="有问题反馈的笔记" :value="analysis?.tagged_notes ?? 0" color="#13c2c2" :icon="MessageOutlined" tip="从这些笔记中识别出了用户抱怨/问题的笔记篇数（数据样本量）" /></a-col>
          <a-col :xs="12" :lg="6"><StatCard title="问题反馈总次数" :value="analysis?.total_tags ?? 0" color="#d97706" :icon="TagsOutlined" tip="所有问题类型被多达主体提的总次数：正文/标题按作者计（最多1次），评论区按不同用户计（同一用户多次只算1次）" /></a-col>
      <a-col :xs="12" :lg="6">
        <StatCard
          title="最集中的问题"
          :value="topLabel"
          color="#dc2626"
          :icon="AlertOutlined"
          tip="被提及次数最多的那类问题（下方数字为其出现次数）"
        />
        <div v-if="analysis?.top_dimension" class="muted" style="text-align:center">出现 {{ analysis.top_dimension.count }} 次</div>
      </a-col>
        </a-row>

        <a-empty v-if="!analysis?.dimensions?.length" description="该产品暂无问题标签（采集后会自动异步分析，稍后刷新）" />

        <!-- ② ECharts 问题分布图 -->
        <a-card v-if="analysis?.dimensions?.length" size="small" style="margin-bottom: 16px">
          <template #title>
            <a-radio-group v-model:value="chartMode" size="small">
              <a-radio-button value="bar">柱状图</a-radio-button>
              <a-radio-button value="pie">饼图</a-radio-button>
            </a-radio-group>
          </template>
          <div ref="chartEl" style="width: 100%; height: 360px"></div>
        </a-card>

        <!-- ③ 问题明细表 -->
        <div class="muted" style="margin: 4px 0 8px">
          口径说明：“提及次数” = 作者（标题+正文合并，最多1次）+ 评论不同用户数（同一用户多次只算1次）；“占比” = 该类型提及次数 ÷ 问题反馈总次数；“待确认” = AI 识别的新问题类型，请确认；“用户原话”为归并进该类型的不同说法。
        </div>
        <a-table
          :columns="columns"
          :data-source="tableRows"
          row-key="dimension"
          size="middle"
          :pagination="{ pageSize: 10 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'dimension'">
              {{ record.dimension }}
              <a-tooltip v-if="record.confirmed === false" title="AI 自动识别的新问题类型，请点“确认”收录或“忽略”">
                <a-tag color="gold">待确认</a-tag>
              </a-tooltip>
            </template>
            <template v-else-if="column.key === 'labels'">{{ (record.labels || []).join(' / ') || '—' }}</template>
            <template v-else-if="column.key === 'excerpt'">
              <a-typography-text :ellipsis="true" style="max-width: 260px">{{ record.sample_excerpt || '—' }}</a-typography-text>
            </template>
            <template v-else-if="column.key === 'action'">
              <template v-if="record.confirmed === false">
                <a-button size="small" type="primary" ghost @click.stop="onConfirm(record, true)">确认</a-button>
                <a-button size="small" @click.stop="onConfirm(record, false)">忽略</a-button>
              </template>
              <span v-else class="muted">正式</span>
            </template>
          </template>
        </a-table>

        <!-- ④ 产品优化建议 -->
        <a-card size="small" style="margin-top: 16px">
          <template #title>产品优化建议</template>
          <a-button type="primary" ghost :loading="loadingReport" @click="onGenerateReport">重新生成</a-button>
          <div v-if="!report && !loadingReport" class="muted" style="margin-top:8px">采集后会自动生成；也可点“重新生成”立即生成</div>
          <template v-else>
            <a-button size="small" style="margin-bottom: 12px" @click="copyReport">复制建议</a-button>
            <p style="font-weight: 600; margin-bottom: 8px">{{ report.summary }}</p>
            <ol style="padding-left: 18px; margin-bottom: 8px">
              <li v-for="(s, i) in report.suggestions" :key="i">{{ s }}</li>
            </ol>
            <template v-if="report.new_dimensions?.length">
              <a-alert type="warning" show-icon message="新发现维度（待确认）" :description="report.new_dimensions.join('、')" />
            </template>
          </template>
        </a-card>
      </template>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { message } from 'ant-design-vue'
import {
  FileTextOutlined, MessageOutlined, TagsOutlined, AlertOutlined,
} from '@ant-design/icons-vue'
import StatCard from '../components/StatCard.vue'
import {
  productAnalysis, productReport, getProductReport, productMerge, confirmDimension,
} from '../api'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const selectedProduct = ref('')
const loadingAnalysis = ref(false)
const loadingReport = ref(false)
const chartMode = ref('bar')
const chartEl = ref(null)

const analysis = ref(null)
const report = ref(null)

let chart = null

const columns = [
  { title: '问题类型', dataIndex: 'dimension', key: 'dimension', width: 170 },
  { title: '提及次数', dataIndex: 'count', key: 'count', width: 90 },
  { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 80 },
  { title: '用户原话', key: 'labels' },
  { title: '示例原文', key: 'excerpt' },
  { title: '状态', key: 'action', width: 130 },
]

const topLabel = computed(() => analysis.value?.top_dimension?.dimension || '—')

const unconfirmedCount = computed(() => (analysis.value?.unconfirmed || []).length)

// 明细表行 = 正式维度 + 待确认维度
const tableRows = computed(() => {
  const dims = (analysis.value?.dimensions || []).map((d) => {
    const total = analysis.value?.total_tags || 0
    return {
      dimension: d.dimension,
      count: d.count,
      ratio: total ? `${Math.round((d.count / total) * 100)}%` : '0%',
      negative_ratio: d.count ? `${Math.round((d.negative / d.count) * 100)}%` : '0%',
      labels: d.labels,
      sample_excerpt: d.sample_excerpt,
      confirmed: true,
    }
  })
  const unc = (analysis.value?.unconfirmed || []).map((u) => ({
    dimension: u.dimension,
    count: u.count,
    ratio: '',
    negative_ratio: '',
    labels: [],
    sample_excerpt: '',
    confirmed: false,
  }))
  return [...dims, ...unc]
})

onMounted(() => {
  store.refreshKeywords().catch(() => {})
})

watch(chartMode, () => nextTick(renderChart))
watch(analysis, () => nextTick(renderChart))

onBeforeUnmount(() => {
  if (chart) chart.dispose()
})

async function loadAnalysis() {
  const product = selectedProduct.value
  if (!product) return
  loadingAnalysis.value = true
  try {
    analysis.value = await store.refreshProductAnalysis(product)
    // 自动读取已生成的优化建议缓存（采集后自动生成，打开即显示）
    report.value = await getProductReport(product)
  } catch (err) {
    message.error(err.message)
  } finally {
    loadingAnalysis.value = false
  }
}

function onProductChange() {
  loadAnalysis()
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  // 兜底：按 trim 后去重（防后端隐藏字符差异导致看似重复的柱）
  const seen = new Set()
  const dims = (analysis.value?.dimensions || []).slice(0, 10).filter((d) => {
    const key = String(d.dimension || '').trim()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  const names = dims.map((d) => d.dimension)
  const values = dims.map((d) => d.count)
  // 统一调色板：按维度顺序分配，保证柱状图与饼图同一维度颜色一致
  const palette = ['#1677ff', '#52c41a', '#faad14', '#f5222d', '#13c2c2', '#722ed1', '#eb2f96', '#fa8c16', '#a0d911', '#2f54eb']
  const colorMap = {}
  dims.forEach((d, i) => {
    colorMap[d.dimension] = palette[i % palette.length]
  })
  const option =
    chartMode.value === 'bar'
      ? {
          tooltip: { trigger: 'axis' },
          grid: { left: 140, right: 24, top: 16, bottom: 24 },
          xAxis: { type: 'value' },
          // 横向条形图：从上到下对应最大的维度，颜色随维度一起反转
          yAxis: { type: 'category', data: [...names].reverse() },
          series: [
            {
              type: 'bar',
              data: [...names].reverse().map((n, i) => ({
                value: [...values].reverse()[i],
                itemStyle: { color: colorMap[n], borderRadius: [0, 4, 4, 0] },
              })),
              label: { show: true, position: 'right' },
            },
          ],
        }
      : {
          tooltip: { trigger: 'item' },
          legend: { bottom: 0 },
          series: [
            {
              type: 'pie',
              radius: ['35%', '62%'],
              data: dims.map((d) => ({ name: d.dimension, value: d.count, itemStyle: { color: colorMap[d.dimension] } })),
            },
          ],
        }
  chart.setOption(option, true)
}

async function onMerge() {
  try {
    const res = await productMerge(selectedProduct.value)
    message.success(`已合并 ${res.merged?.length || 0} 个维度`)
    await loadAnalysis()
  } catch (err) {
    message.error(err.message)
  }
}

async function onConfirm(record, confirmed) {
  try {
    await confirmDimension(selectedProduct.value, record.dimension, confirmed)
    message.success(confirmed ? `已确认维度：${record.dimension}` : `已忽略维度：${record.dimension}`)
    await loadAnalysis()
  } catch (err) {
    message.error(err.message)
  }
}

async function onGenerateReport() {
  loadingReport.value = true
  try {
    report.value = await productReport(selectedProduct.value)
    message.success('优化建议已生成')
  } catch (err) {
    message.error(err.message)
  } finally {
    loadingReport.value = false
  }
}

function copyReport() {
  if (!report.value) return
  const text = `${report.value.summary}\n${(report.value.suggestions || []).map((s, i) => `${i + 1}. ${s}`).join('\n')}`
  navigator.clipboard.writeText(text).then(
    () => message.success('已复制'),
    () => message.error('复制失败，请手动选择复制'),
  )
}
</script>

<style scoped>
.muted {
  color: #999;
  font-size: 12px;
}
</style>