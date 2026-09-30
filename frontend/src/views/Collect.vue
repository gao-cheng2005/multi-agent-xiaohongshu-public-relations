<!-- 采集控制页：产品/URL 手动采集 + 产品管理。 -->
<template>
  <div class="page">
                                         

    <a-card :bordered="false" title="手动触发采集" style="margin-bottom: 16px">
      <a-form layout="vertical">
        <a-form-item label="采集方式">
          <a-radio-group v-model:value="mode" button-style="solid">
            <a-radio-button value="keyword">按产品</a-radio-button>
            <a-radio-button value="note">按笔记 URL</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-form-item v-if="mode === 'keyword'" label="选择产品">
          <a-select v-model:value="keyword" placeholder="请选择产品" allow-clear>
            <a-select-option v-for="k in store.keywords" :key="k.id" :value="k.keyword">{{ k.keyword }}</a-select-option>
          </a-select>
          <div v-if="!store.keywords.length" style="font-size: 12px; color: #999; margin-top: 4px">暂无产品，请先在下方"产品管理"添加</div>
        </a-form-item>
        <a-form-item v-else label="笔记 URL">
          <a-input v-model:value="noteUrl" placeholder="粘贴小红书笔记链接" allow-clear />
        </a-form-item>

        <a-row :gutter="16">
          <a-col v-if="mode === 'keyword'" :span="8">
            <a-form-item label="采集数量">
              <a-input-number v-model:value="limit" :min="1" :max="50" placeholder="5" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="抓取评论">
              <a-switch v-model:checked="fetchComments" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="评论条数(上限，含回复)">
              <a-input-number v-model:value="commentDepth" :min="1" :max="20" placeholder="3" :disabled="!fetchComments" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-button type="primary" :loading="collecting" @click="onCollect">
          <template #icon><CloudDownloadOutlined /></template>开始采集
        </a-button>
      </a-form>
    </a-card>

    <a-card :bordered="false" title="产品管理">
      <a-space style="margin-bottom: 12px" wrap>
        <a-input v-model:value="newKeyword" placeholder="新增产品" style="width: 240px" allow-clear @press-enter="onAddKeyword" />
        <a-button type="primary" @click="onAddKeyword"><template #icon><PlusOutlined /></template>添加</a-button>
        <a-button @click="store.refreshKeywords()"><template #icon><ReloadOutlined /></template>刷新</a-button>
        <a-popconfirm title="确定要清空全部产品吗？此操作不可恢复" ok-text="清空" cancel-text="取消" @confirm="onClearKeywords">
          <a-button danger><template #icon><DeleteOutlined /></template>清空全部</a-button>
        </a-popconfirm>
      </a-space>
      <a-table :columns="keywordColumns" :data-source="store.keywords" row-key="id" size="middle" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <a-button type="text" danger size="small" @click="onRemoveKeyword(record)">
              <template #icon><DeleteOutlined /></template>删除
            </a-button>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { CloudDownloadOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const mode = ref('keyword')
const keyword = ref('')
const noteUrl = ref('')
const limit = ref(5)
const fetchComments = ref(true)
const commentDepth = ref(3)
const collecting = ref(false)
const newKeyword = ref('')

const keywordColumns = [
  { title: '产品', dataIndex: 'keyword', key: 'keyword' },
  { title: '平台', dataIndex: 'platform', key: 'platform' },
  { title: '上次触发', dataIndex: 'last_triggered_at', key: 'last_triggered_at' },
  { title: '操作', key: 'action', width: 100 },
]

onMounted(() => {
  store.refreshKeywords().catch(() => {})
})

// 触发采集并刷新各模块数据。
// 组装采集参数（产品/URL 模式不同）并刷新相关模块
async function onCollect() {
  if (mode.value === 'keyword' && !keyword.value) return message.warning('请选择产品')
  if (mode.value === 'note' && !noteUrl.value.trim()) return message.warning('请输入笔记 URL')
  collecting.value = true
  try {
    const payload = {
      limit: limit.value,
      fetch_comments: fetchComments.value,
      comment_depth: commentDepth.value,
    }
    if (mode.value === 'keyword') payload.keyword = keyword.value
    else payload.note_url = noteUrl.value.trim()
    const result = await store.collect(payload)
    const collected = result.collected_notes ?? 0
    const skipped = result.skipped_notes ?? 0
    const comments = result.collected_comments ?? 0
    if (collected === 0 && skipped === 0) {
      message.warning('采集完成，但未获取到任何笔记，请检查产品或登录状态')
    } else if (collected === 0) {
      message.success(`采集完成：${skipped} 条笔记已存在已跳过，无新笔记入库`)
    } else if (skipped > 0) {
      message.success(`采集完成：新增笔记 ${collected} 条，跳过已存在 ${skipped} 条，评论 ${comments} 条`)
    } else {
      message.success(`采集完成：笔记 ${collected} 条，评论 ${comments} 条`)
    }
    await Promise.allSettled([store.refreshContents(), store.refreshStats(), store.refreshAlerts(), store.refreshKeywords()])
  } catch (err) {
    message.error(err.message)
  } finally {
    collecting.value = false
  }
}

// 新增产品。
async function onAddKeyword() {
  const value = newKeyword.value.trim()
  if (!value) return
  try {
    await store.addKeyword(value)
    newKeyword.value = ''
    message.success('已添加')
  } catch (err) {
    message.error(err.message)
  }
}

async function onRemoveKeyword(record) {
  try {
    await store.removeKeyword(record.id)
    message.success('已删除')
  } catch (err) {
    message.error(err.message)
  }
}

// 清空全部产品（带二次确认）。
async function onClearKeywords() {
  try {
    const res = await store.clearKeywords()
    message.success(`已清空全部产品${res?.count ? `（${res.count} 条）` : ''}`)
  } catch (err) {
    message.error(err.message)
  }
}
</script>
