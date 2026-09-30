<!-- 舆情内容页：笔记列表 + 详情抽屉（正文/评论/应对方案）。 -->
<template>
  <div class="page">

    <a-card :bordered="false">
      <a-space style="margin-bottom: 16px" wrap>
        <a-input v-model:value="search" placeholder="搜索标题/作者" allow-clear style="width: 220px" />
        <a-select v-model:value="filterSource" style="width: 140px" allow-clear placeholder="采集来源">
          <a-select-option value="keyword">产品</a-select-option>
          <a-select-option value="note_url">笔记URL</a-select-option>
        </a-select>
        <a-select
          v-model:value="filterKeyword"
          style="width: 180px"
          allow-clear
          placeholder="细分产品"
          :disabled="filterSource && filterSource !== 'keyword'"
        >
          <a-select-option v-for="k in keywordOptions" :key="k" :value="k">{{ k }}</a-select-option>
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
        <a-button @click="reload"><template #icon><ReloadOutlined /></template>刷新</a-button>
        <a-popconfirm :title="deleteConfirmText" ok-text="删除" cancel-text="取消" @confirm="onDeleteFiltered">
          <a-button danger><template #icon><DeleteOutlined /></template>{{ hasFilters ? '删除筛选结果' : '清空全部' }}</a-button>
        </a-popconfirm>
      </a-space>

      <a-table
        :columns="columns"
        :data-source="filteredRows"
        row-key="id"
        size="middle"
        :pagination="{ pageSize: 10 }"
        :custom-row="customRow"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'keyword'">
            <span v-if="record.source_type === 'note_url'" class="muted">笔记URL</span>
            <span v-else>{{ record.keyword || '—' }}</span>
          </template>
          <template v-else-if="column.key === 'sentiment'"><SentimentTag :value="record.sentiment" /></template>
          <template v-else-if="column.key === 'risk_level'"><RiskTag :value="record.risk_level" /></template>
          <template v-else-if="column.key === 'open'">
            <a-popconfirm title="确定删除这条笔记吗？评论/分析/预警/方案将一并删除" ok-text="删除" cancel-text="取消" @confirm="onDeleteOne(record)">
              <a-button size="small" type="text" danger><template #icon><DeleteOutlined /></template>删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-drawer v-model:open="drawerOpen" :title="current?.title" width="560">
      <template v-if="current">
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="作者">{{ current.author }}</a-descriptions-item>
          <a-descriptions-item label="发布时间">{{ current.published_at }}</a-descriptions-item>
          <a-descriptions-item label="产品">{{ current.source_type === 'note_url' ? '笔记URL' : (current.keyword || '—') }}</a-descriptions-item>
          <a-descriptions-item label="点赞">{{ current.like_count }}</a-descriptions-item>
          <a-descriptions-item label="收藏">{{ current.collect_count }}</a-descriptions-item>
          <a-descriptions-item label="评论">{{ current.comment_count }}</a-descriptions-item>
          <a-descriptions-item label="情感"><SentimentTag :value="current.sentiment" /></a-descriptions-item>
          <a-descriptions-item label="风险"><RiskTag :value="current.risk_level" /></a-descriptions-item>
          <a-descriptions-item label="原文链接" :span="2">
            <a-space :size="8" wrap>
              <a-button size="small" type="primary" ghost :loading="openingId === current.id" @click="openFresh(current)">打开原文</a-button>
              <a-button size="small" :loading="generatingPlan" @click="onGeneratePlan">{{ current?.plan_status === 'done' ? '应对方案' : '生成应对方案' }}</a-button>
              <a-button size="small" type="primary" :disabled="!canCompleteDrawer" :loading="decidingPlan" @click="onCompleteDrawer">完成处理</a-button>
            </a-space>
          </a-descriptions-item>
        </a-descriptions>
        <p class="body-text">{{ current.body }}</p>
        <a-divider>评论</a-divider>
        <a-list :data-source="flatComments" size="small">
          <template #renderItem="{ item }">
            <a-list-item :style="{ paddingLeft: item.depth * 24 + 'px' }">
              <a-space direction="vertical" :size="2" style="width: 100%">
                <span class="comment-head">
                  <b>{{ item.author }}</b>
                  <span v-if="item.depth > 0" class="reply-marker">↳ 回复 {{ item.parentAuthor || '' }}</span>
                  <span class="muted">{{ item.published_at }}</span>
                </span>
                <span>{{ item.content }}</span>
              </a-space>
            </a-list-item>
          </template>
        </a-list>
        <a-empty v-if="!comments.length" description="暂无评论" />
      </template>
    </a-drawer>

    <PlanModal
      :open="planModalOpen"
      :plan="currentPlan"
      :rewriting="rewritingPlan"
      @close="planModalOpen = false"
      @rewrite="onRewritePlan"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import SentimentTag from '../components/SentimentTag.vue'
import RiskTag from '../components/RiskTag.vue'
import { listComments, refreshNoteUrl } from '../api'
import { useAppStore } from '../stores/app'
import { message } from 'ant-design-vue'
import PlanModal from '../components/PlanModal.vue'

const store = useAppStore()
const search = ref('')
const filterSource = ref(undefined)
const filterKeyword = ref(undefined)
const filterSentiment = ref(undefined)
const filterRisk = ref(undefined)
const drawerOpen = ref(false)
const current = ref(null)
const comments = ref([])
const openingId = ref(null)
const planModalOpen = ref(false)
const currentPlan = ref(null)
const generatingPlan = ref(false)
const generatingId = ref(null)
const rewritingPlan = ref(false)
const decidingPlan = ref(false)

// 当前抽屉笔记的应对方案（来自 store.plans，按 content_id 匹配）
const drawerPlan = computed(() => store.plans.find((p) => p.content_id === current.value?.content_id) || null)
// 方案已生成完毕（done）可“完成处理”；
// 正面/中性 + 低风险（skipped）也可直接“完成处理”（处理渠道落为“无需处理”）
const canCompleteDrawer = computed(() => ['done', 'skipped'].includes(drawerPlan.value?.status))

// 细分产品下拉选项（来自后端筛选接口）
const keywordOptions = computed(() =>
  [...new Set(store.contentFilters.filter((f) => f.source_type === 'keyword').map((f) => f.keyword))].filter(Boolean),
)

const columns = [
  { title: '笔记标题', dataIndex: 'title', key: 'title', ellipsis: true, minWidth: 200 },
  { title: '产品', dataIndex: 'keyword', key: 'keyword', width: 130 },
  { title: '作者', dataIndex: 'author', key: 'author', width: 110 },
  { title: '情感', dataIndex: 'sentiment', key: 'sentiment', width: 80 },
  { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 80 },
  { title: '点赞', dataIndex: 'like_count', key: 'like_count', width: 70 },
  { title: '收藏', dataIndex: 'collect_count', key: 'collect_count', width: 70 },
  { title: '评论', dataIndex: 'comment_count', key: 'comment_count', width: 70 },
  { title: '发布时间', dataIndex: 'published_at', key: 'published_at', width: 110 },
  { title: '操作', key: 'open', width: 110 },
]

// 前端二次过滤：来源/产品/情感/风险 + 标题作者搜索
const filteredRows = computed(() =>
  store.contents.filter((row) => {
    if (filterSource.value && row.source_type !== filterSource.value) return false
    if (filterKeyword.value && row.keyword !== filterKeyword.value) return false
    if (filterSentiment.value && row.sentiment !== filterSentiment.value) return false
    if (filterRisk.value && row.risk_level !== filterRisk.value) return false
    const q = search.value.trim()
    if (q) {
      const hay = `${row.title || ''} ${row.author || ''}`
      if (!hay.includes(q)) return false
    }
    return true
  }),
)

function reload() {
  store.refreshContents()
  store.refreshContentFilters()
}

const route = useRoute()
const router = useRouter()

onMounted(async () => {
  await store.refreshContents().catch(() => {})
  store.refreshContentFilters().catch(() => {})
  // 启动自动轮询：每 5 秒刷新内容，让异步生成的应对方案状态自动更新
  startPolling()
  // URL 定位：从总览页"最近预警/去处理"跳转过来时，?content_id=xxx 自动打开对应笔记
  const cid = route.query.content_id
  if (cid) {
    const target = store.contents.find((c) => c.content_id === cid)
    if (target) {
      onRowClick(target)
      // 打开后清掉 query，避免刷新页面时反复自动打开
      router.replace({ path: '/contents' })
    }
  }
})

onBeforeUnmount(stopPolling)

let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await store.refreshContents().catch(() => {})
  }, 5000)
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 组装当前筛选条件（供删除接口使用；与表格展示的筛选一致）
function buildDeleteParams() {
  return {
    q: search.value.trim() || undefined,
    source_type: filterSource.value || undefined,
    keyword: filterKeyword.value || undefined,
    sentiment: filterSentiment.value || undefined,
    risk: filterRisk.value || undefined,
  }
}

// 是否处于“有筛选条件”的状态（决定按钮文案与确认弹窗）
const hasFilters = computed(() => {
  return Boolean(
    search.value.trim() ||
      filterSource.value ||
      filterKeyword.value ||
      filterSentiment.value ||
      filterRisk.value,
  )
})

// 删除确认弹窗的文案：有筛选=删筛选结果；无筛选=删全部（重点强调不可恢复）
const deleteConfirmText = computed(() =>
  hasFilters.value
    ? `确定删除当前筛选出的 ${filteredRows.value.length} 条笔记吗？评论/分析/预警/方案将一并删除，此操作不可恢复`
    : '确定清空全部笔记吗？评论/分析/预警/方案将一并删除，此操作【不可恢复】',
)

// 删除单条笔记
async function onDeleteOne(record) {
  try {
    const res = await store.deleteContents({ content_id: record.content_id })
    message.success(`已删除 ${res?.count ?? 1} 条`)
  } catch (err) {
    message.error(err.message)
  }
}

// 删除当前筛选结果 / 清空全部（筛选条件为空时后端按全部删除）
async function onDeleteFiltered() {
  const params = buildDeleteParams()
  try {
    const res = await store.deleteContents(params)
    message.success(
      hasFilters.value
        ? `已删除筛选结果 ${res?.count ?? 0} 条笔记`
        : `已清空全部笔记，共删除 ${res?.count ?? 0} 条`,
    )
  } catch (err) {
    message.error(err.message)
  }
}

function customRow(record) {
  return { onClick: () => onRowClick(record), style: { cursor: 'pointer' } }
}

// 点击行打开详情抽屉并加载评论（含楼中楼）
async function onRowClick(record) {
  // 用列表最新数据刷新该行的方案状态（后台自动生成可能在打开前刚完成）
  const latest = store.contents.find((c) => c.content_id === record.content_id) || record
  current.value = latest
  drawerOpen.value = true
  comments.value = []
  // 拉取该笔记的应对方案（供抽屉直接"完成处理"）
  store.refreshPlans(record.content_id).catch(() => {})
  try {
    comments.value = await listComments(record.content_id)
  } catch {
    comments.value = []
  }
}

                                           
// 评论按 parent_id 还原成层级树后压平，用于缩进展示。
const flatComments = computed(() => {
  const map = {}
  const roots = []
  for (const c of comments.value) {
    c._children = []
    map[c.comment_id] = c
  }
  for (const c of comments.value) {
    if (c.parent_id && map[c.parent_id]) map[c.parent_id]._children.push(c)
    else roots.push(c)
  }
  const out = []
  const walk = (items, depth) => {
    for (const it of items) {
      out.push({ ...it, depth, parentAuthor: it.parent_id ? (map[it.parent_id]?.author || '') : '' })
      walk(it._children, depth + 1)
    }
  }
  walk(roots, 0)
  return out
})

                                        
                                                                
                           
// 打开原文：先开空白页（保用户手势）再跳转刷新后的签名链接。
// 空白页立刻写入加载提示，避免长时间显示 about:blank；
// 刷新失败时回退到库里保存的原始链接，尽量保证能打开。
async function openFresh(record) {
  openingId.value = record.id
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

// 生成应对方案并打开弹窗（抽屉按钮）。
// 已生成的方案直接返回展示；正在生成中的提示稍后再看，不重复起任务。
async function onRowGeneratePlan(record) {
  if (!record?.content_id) return
  generatingId.value = record.id
  generatingPlan.value = true
  try {
    const res = await store.generatePlan(record.content_id)
    if (res && res.status === 'processing') {
      message.info('方案正在生成中，请稍后…')
      return
    }
    // 只有真正重新生成了方案才提示“应对方案已生成”；查看已有方案不提示
    if (res && res._regenerated) {
      message.success('应对方案已生成')
    }
    currentPlan.value = store.plans.find((p) => p.content_id === record.content_id) || null
    planModalOpen.value = true
  } catch (err) {
    message.error(err.message)
  } finally {
    generatingId.value = null
    generatingPlan.value = false
  }
}

// 抽屉里的“生成应对方案”按钮：复用同一逻辑
function onGeneratePlan() {
  if (current.value) onRowGeneratePlan(current.value)
}

// 按操作者的人工修改要求重新生成文案（渠道不变，覆盖原文案）
async function onRewritePlan(feedback) {
  if (!currentPlan.value) return
  rewritingPlan.value = true
  try {
    const res = await store.regeneratePlan(currentPlan.value.content_id, feedback)
    message.success('已按修改要求重新生成')
    currentPlan.value = { ...(currentPlan.value || {}), ...res }
  } catch (err) {
    message.error(err.message)
  } finally {
    rewritingPlan.value = false
  }
}

// 完成处理：把笔记标记为已处理（抽屉按钮）。
// 已生成方案的笔记按推荐渠道处理完点它；
// 正面/中性 + 低风险（skipped）笔记直接点它即可，渠道落为"无需处理"。
// 成功后该笔记移入"处理记录"并关闭抽屉。
async function onCompleteDrawer() {
  if (!current.value?.content_id) return
  decidingPlan.value = true
  try {
    await store.completePlan(current.value.content_id)
    message.success('已标记为已处理')
    drawerOpen.value = false
    current.value = null
  } catch (err) {
    message.error(err.message)
  } finally {
    decidingPlan.value = false
  }
}
</script>

<style scoped>
.body-text {
  white-space: pre-wrap;
  color: #374151;
}
.comment-head {
  color: #111827;
}
.muted {
  color: #9ca3af;
  font-size: 12px;
  font-weight: normal;
}
.reply-marker {
  color: #1677ff;
  font-size: 12px;
  font-weight: normal;
}
</style>
