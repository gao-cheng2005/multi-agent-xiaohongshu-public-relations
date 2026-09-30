<!-- 应对方案弹窗：展示方案、复制文案、人工审核决策。 -->
<template>
  <a-modal
    :open="open"
    :title="`应对方案`"
    width="680"
    @cancel="$emit('close')"
    :footer="null"
  >
    <template v-if="plan">
      <div v-if="rule || reason" style="margin-bottom: 12px">
        <a-tag color="volcano">{{ rule }}</a-tag>
        <span class="muted">{{ reason }}</span>
      </div>
      <a-descriptions :column="1" size="small" bordered style="margin-bottom: 12px">
        <a-descriptions-item label="推荐动作">
          <a-tag :color="actionColor">{{ actionText }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="推荐原因">
          <span>{{ plan.reason || '—' }}</span>
        </a-descriptions-item>
      </a-descriptions>

      <a-divider style="margin: 8px 0">私信文案</a-divider>
      <a-typography-paragraph class="copy-box">
        {{ plan.dm_copy || '（未生成）' }}
      </a-typography-paragraph>
      <a-button size="small" @click="copy(plan.dm_copy)"><template #icon><CopyOutlined /></template>复制私信文案</a-button>

      <a-divider style="margin: 16px 0 8px">公开评论文案</a-divider>
      <a-typography-paragraph class="copy-box">
        {{ plan.comment_copy || '（未生成）' }}
      </a-typography-paragraph>
      <a-button size="small" @click="copy(plan.comment_copy)"><template #icon><CopyOutlined /></template>复制评论文案</a-button>

      <template v-if="!readonly">
        <a-divider style="margin: 20px 0 12px">人工审核决策</a-divider>
        <a-textarea
          v-model:value="feedback"
          :rows="2"
          placeholder="如对文案有修改要求，请填写（例如：控制在50字以内、加入官方联系电话…）；填写后按 Enter 或点击按钮重新生成，无要求可留空"
          @keydown.enter.prevent="onRewrite"
        />
        <a-space style="margin-top: 8px">
          <a-button :loading="rewriting" :disabled="!feedback.trim()" @click="onRewrite">提交修改并重新生成</a-button>
        </a-space>
      </template>
    </template>
    <a-empty v-else description="暂无方案" />
  </a-modal>
</template>

<script setup>
import { ref, computed, watch, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { CopyOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  open: Boolean,
  plan: Object,
  rule: { type: String, default: '' },
  reason: { type: String, default: '' },
  rewriting: Boolean,
  // 只读模式：处理记录里只查看文案，不展示“重新生成”区
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'rewrite'])

// 人工修改要求（空=认可当前文案，不触发重新生成）
const feedback = ref('')
// 按笔记分别保存草稿（content_id -> 文本）：每个笔记的修改要求各自独立
const feedbackMap = reactive({})

// 切换笔记时，从该笔记自己的草稿里恢复（没有则是空白）
watch(
  () => props.plan?.content_id,
  (id) => {
    feedback.value = id ? feedbackMap[id] || '' : ''
  },
  { immediate: true },
)

// 输入时实时存回当前笔记的草稿，切换时互不干扰
watch(feedback, (val) => {
  const id = props.plan?.content_id
  if (id) feedbackMap[id] = val
})

// 提交修改要求并重新生成（按钮 或 Enter 触发）
function onRewrite() {
  const value = feedback.value.trim()
  if (!value) return
  emit('rewrite', value)
  // 提交后清空文本框与该笔记的草稿，避免下次误提交同样内容
  feedback.value = ''
  if (props.plan?.content_id) feedbackMap[props.plan.content_id] = ''
}

                                      
// 推荐动作文案：优先读新字段 channel，旧数据按 recommended_action 兼容
const actionText = computed(() => {
  const ch = props.plan?.channel
  if (ch === 'dm') return '私信'
  if (ch === 'public') return '公开评论'
  if (ch === 'skip') return '无需处理'
  // 兼容旧数据：recommended_action 里存的是渠道词
  const a = props.plan?.recommended_action
  if (a === '私信') return '私信'
  if (a === '私信并且公开评论') return '私信并且公开评论'
  return '公开评论'
})
const actionColor = computed(() => {
  const ch = props.plan?.channel
  if (ch === 'dm') return 'purple'
  if (ch === 'public') return 'blue'
  if (ch === 'skip') return 'default'
  const a = props.plan?.recommended_action
  if (a === '私信') return 'purple'
  if (a === '私信并且公开评论') return 'gold'
  return 'blue'
})

// 复制文案到剪贴板。
function copy(text) {
  if (!text) return message.warning('暂无内容可复制')
  navigator.clipboard.writeText(text).then(
    () => message.success('已复制'),
    () => message.error('复制失败，请手动选择复制'),
  )
}
</script>

<style scoped>
.copy-box {
  margin: 4px 0;
  padding: 10px 12px;
  background: #f6f7f9;
  border-radius: 6px;
  white-space: pre-wrap;
}
.muted {
  color: #9ca3af;
  font-size: 12px;
}
</style>
