<!-- 设置页：运行状态 + 大模型设置（硅基流动）。 -->
<template>
  <div class="page">

    <a-card :bordered="false" title="运行状态" style="margin-bottom: 16px">
      <a-descriptions :column="2" bordered size="small">
        <a-descriptions-item label="采集模式">
          {{ store.info.collect_mode === 'opencli' ? '真实抓取(OpenCLI)' : '模拟数据(mock)' }}
        </a-descriptions-item>
        <a-descriptions-item label="情感分析模式">{{ store.info.sentiment_mode }}</a-descriptions-item>
        <a-descriptions-item label="大模型提供方">硅基流动(SiliconFlow)</a-descriptions-item>
        <a-descriptions-item label="当前模型">
          {{ store.info.llm_configured ? store.info.llm_model : '规则词库(未配置密钥)' }}
        </a-descriptions-item>
        <a-descriptions-item label="数据库">{{ store.info.db_path }}</a-descriptions-item>
      </a-descriptions>
    </a-card>

    <a-card :bordered="false" title="大模型设置" style="margin-bottom: 16px">
      <a-alert type="info" show-icon style="margin-bottom: 12px"
        message="API Key 已由系统内置（公司密钥），无需也无需在此填写；切换模型即时生效、无需重启。" />
      <a-space wrap>
        <a-select
          v-model:value="selectedModel"
          style="width: 380px"
          placeholder="请选择模型"
          :options="modelOptions"
          show-search
          option-filter-prop="label"
        />
        <a-button type="primary" :loading="savingModel" @click="onSaveModel">
          <template #icon><SaveOutlined /></template>保存模型
        </a-button>
        <a-button @click="onRefreshModels">
          <template #icon><ReloadOutlined /></template>刷新模型列表
        </a-button>
      </a-space>
      <p style="margin-top: 12px; margin-bottom: 0; color: #888">
        当前生效：{{ store.llmConfig.model || '（默认）' }}
        <template v-if="store.llmConfig.configured === false"> · 状态：未配置密钥（走规则兜底）</template>
      </p>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const selectedModel = ref(null)
const savingModel = ref(false)

// 下拉选项：显示名 + 模型 id
const modelOptions = computed(() =>
  store.llmModels.map((m) => ({ value: m.id, label: `${m.name}（${m.id}）` })),
)

onMounted(() => {
  Promise.allSettled([
    store.refreshInfo(),
    store.refreshLlmModels(),
    store.refreshLlmConfig(),
  ]).then(() => {
    // 预选当前生效的模型，方便用户直接保存（或换一个）
    selectedModel.value = store.llmConfig.model || null
  })
})

// 切换大模型并保存（即时生效）。
async function onSaveModel() {
  if (!selectedModel.value) return message.warning('请先选择模型')
  savingModel.value = true
  try {
    await store.updateLlmModel(selectedModel.value)
    message.success(`已切换到大模型：${selectedModel.value}`)
  } catch (err) {
    message.error(err.message || '切换失败')
  } finally {
    savingModel.value = false
  }
}

// 刷新可选模型清单。
async function onRefreshModels() {
  try {
    await store.refreshLlmModels()
    await store.refreshLlmConfig()
    message.success('模型列表已刷新')
  } catch (err) {
    message.error(err.message || '刷新失败')
  }
}
</script>