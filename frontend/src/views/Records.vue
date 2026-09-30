<!-- 处理记录：已完成处理的舆情笔记存档（方案状态为已处理，可按渠道/情感等筛选）。 -->
<template>
  <div class="page">
    <a-card :bordered="false">
      <a-space style="margin-bottom: 16px" wrap>
        <a-input v-model:value="search" placeholder="搜索标题/作者" allow-clear style="width: 220px" />
        <a-select v-model:value="filterSource" style="width: 140px" allow-clear placeholder="采集来源">
          <a-select-option value="keyword">产品</a-select-option>
          <a-select-option value="note_url">笔记URL</a-select-option>
        </a-select>
        <a-select v-model:value="filterKeyword" style="width: 180px" allow-clear placeholder="细分产品"
          :disabled="filterSource && filterSource !== 'keyword'">
          <a-select-option v-for="k in productOptions" :key="k" :value="k">{{ k }}</a-select-option>
        </a-select>
        <a-select v-model:value="filterSentiment" style="width: 120px" allow-clear placeholder="情感">
          <a-select-option value="正面">正面</a-select-option>
          <a-select-option value="中性">中性</a-select-option>
          <a-select-option value="负面">负面</a-select-option>
        </a-select>
        <a-select v-model:value="filterRisk" style="width: 120px" allow-clear placeholder="风险">
          <a-select-option value="低">低</a-select-option>
          <a-select-option value="中">中</a-select-option>
          <a-select-option value="高">高</a-select-option>
        </a-select>
        <a-select v-model:value="filterChannel" style="width: 150px" allow-clear placeholder="处理渠道">
          <a-select-option value="dm">私信</a-select-option>
          <a-select-option value="public">公开评论</a-select-option>
          <a-select-option value="skip">无需处理</a-select-option>
        </a-select>
        <a-popconfirm :title="deleteConfirmText" ok-text="删除" cancel-text="取消" @confirm="onDeleteFiltered">
          <a-button danger><template #icon><DeleteOutlined /></template>{{ hasFilters ? '删除筛选结果' : '清空全部' }}</a-button>
        </a-popconfirm>
      </a-space>
      <a-table
        :columns="columns"
        :data-source="store.processedContents"
        row-key="content_id"
        size="middle"
        :pagination="{ pageSize: 10 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'sentiment'"><SentimentTag :value="record.sentiment" /></template>
          <template v-else-if="column.key === 'risk_level'"><RiskTag :value="record.risk_level" /></template>
          <template v-else-if="column.key === 'channel'">
            <a-tag :color="channelColor(record.plan_channel)">
              {{ channelText(record.plan_channel) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space :size="8">
              <a-button size="small" type="link" :loading="openingId === record.content_id" @click="openFresh(record)">打开原文</a-button>
              <a-button size="small" type="link" :disabled="record.plan_channel === 'skip'" @click="openPlan(record)">应对方案</a-button>
              <a-popconfirm title="确定删除这条处理记录吗？笔记及评论/分析/预警/方案将一并删除，不可恢复" ok-text="删除" cancel-text="取消" @confirm="onDeleteRecord(record)">
                <a-button size="small" type="text" danger><template #icon><DeleteOutlined /></template>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <PlanModal :open="planModalOpen" :plan="currentPlan" readonly @close="planModalOpen = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import SentimentTag from '../components/SentimentTag.vue'
import RiskTag from '../components/RiskTag.vue'
import PlanModal from '../components/PlanModal.vue'
import { deleteContents, refreshNoteUrl } from '../api'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const search = ref('')
const filterSource = ref(undefined)
const filterKeyword = ref(undefined)
const filterSentiment = ref(undefined)
const filterRisk = ref(undefined)
const filterChannel = ref(undefined)
const openingId = ref(null)
const planModalOpen = ref(false)
const currentPlan = ref(null)

// 处理渠道展示：dm=私信，public=公开评论，skip=无需处理
function channelText(ch) {
  if (ch === 'dm') return '私信'
  if (ch === 'public') return '公开评论'
  if (ch === 'skip') return '无需处理'
  return '公开评论'
}
function channelColor(ch) {
  if (ch === 'dm') return 'purple'
  if (ch === 'skip') return 'default'
  return 'blue'
}

// 细分产品选项（来自舆情内容的筛选数据；为空则用记录里已有的产品）
const productOptions = computed(() => {
  const fromFilters = store.contentFilters.filter((f) => f.source_type === 'keyword').map((f) => f.keyword)
  return [...new Set([...fromFilters, ...store.processedContents.map((r) => r.keyword).filter(Boolean)])]
})

const columns = [
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true, minWidth: 200 },
  { title: '产品', dataIndex: 'keyword', key: 'keyword', width: 130 },
  { title: '作者', dataIndex: 'author', key: 'author', width: 110 },
  { title: '情感', dataIndex: 'sentiment', key: 'sentiment', width: 80 },
  { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 80 },
  { title: '处理渠道', key: 'channel', width: 100 },
  { title: '处理时间', dataIndex: 'handled_at', key: 'handled_at', width: 150 },
  { title: '操作', key: 'action', width: 230 },
]

onMounted(() => {
  store.refreshContentFilters().catch(() => {})
  reload()
})

// 筛选条件变化即自动查询（不需要点"查询"按钮）：
// 下拉选项选完立即刷新；搜索框防抖 300ms 后自动查询
let searchTimer = null
watch(
  [filterSource, filterKeyword, filterSentiment, filterRisk, filterChannel, search],
  () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(reload, 300)
  },
)

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})

async function reload() {
  const params = {
    q: search.value.trim() || undefined,
    source_type: filterSource.value || undefined,
    keyword: filterKeyword.value || undefined,
    sentiment: filterSentiment.value || undefined,
    risk: filterRisk.value || undefined,
    channel: filterChannel.value || undefined,
  }
  try {
    await store.refreshProcessed(params)
  } catch (err) {
    message.error(err.message)
  }
}

// 是否处于"有筛选条件"的状态（决定删除按钮文案与确认弹窗）
const hasFilters = computed(() => {
  return Boolean(
    search.value.trim() ||
      filterSource.value ||
      filterKeyword.value ||
      filterSentiment.value ||
      filterRisk.value ||
      filterChannel.value,
  )
})

// 删除确认弹窗文案：有筛选=删筛选结果；无筛选=清空全部处理记录
const deleteConfirmText = computed(() =>
  hasFilters.value
    ? '确定删除当前筛选出的处理记录吗？笔记及评论/分析/预警/方案将一并删除，不可恢复'
    : '确定清空全部处理记录吗？笔记及评论/分析/预警/方案将一并删除，此操作【不可恢复】',
)

// 删除当前筛选结果 / 清空全部处理记录（只删已处理的记录，保护舆情内容待办）
async function onDeleteFiltered() {
  const params = {
    q: search.value.trim() || undefined,
    source_type: filterSource.value || undefined,
    keyword: filterKeyword.value || undefined,
    sentiment: filterSentiment.value || undefined,
    risk: filterRisk.value || undefined,
    channel: filterChannel.value || undefined,
    allow_handled: true,
    handled_only: true,
  }
  try {
    const res = await deleteContents(params)
    message.success(
      hasFilters.value
        ? `已删除筛选结果 ${res?.count ?? 0} 条处理记录`
        : `已清空全部处理记录，共删除 ${res?.count ?? 0} 条`,
    )
    reload()
  } catch (err) {
    message.error(err.message)
  }
}

// 删除一条处理记录（允许删除已处理笔记，级联清理关联数据）
async function onDeleteRecord(record) {
  try {
    const res = await deleteContents({ content_id: record.content_id, allow_handled: true })
    message.success(`已删除 ${res?.count ?? 1} 条`)
    reload()
  } catch (err) {
    message.error(err.message)
  }
}

// 打开原文：先开空白页（保用户手势）再跳转刷新后的签名链接。
// 刷新失败时回退到库里保存的原始链接，尽量保证能打开。
async function openFresh(record) {
  openingId.value = record.content_id
  const win = window.open('', '_blank')
  if (win && win.document) {
    win.document.write(`<!doctype html><html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;color:#888"><div>正在获取最新链接，请稍候…</div></body></html>`)
    win.document.close()
  }
  try {
    const { url } = await refreshNoteUrl(record.content_id)
    if (win) {
      win.location.href = url
    } else {
      message.warning('弹窗被拦截，请复制链接手动打开：' + url)
    }
  } catch (err) {
    const fallback = record.url
    if (win && fallback) {
      win.location.href = fallback
      message.warning('链接刷新失败，已尝试用原始链接打开')
    } else {
      if (win) win.close()
      message.error(err.message)
    }
  } finally {
    openingId.value = null
  }
}

// 查看应对方案：只读展示，不需要重新生成（处理记录是已归档数据）
function openPlan(record) {
  currentPlan.value = {
    content_id: record.content_id,
    channel: record.plan_channel,
    reason: record.plan_reason,
    dm_copy: record.dm_copy,
    comment_copy: record.comment_copy,
  }
  planModalOpen.value = true
}
</script>
