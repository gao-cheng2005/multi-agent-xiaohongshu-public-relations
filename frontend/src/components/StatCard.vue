<!-- 统计卡片组件（图标+数值+标题）。 -->
<template>
  <a-card :bordered="false" class="stat-card">
    <span v-if="corner" class="stat-corner">{{ corner }}</span>
    <div class="stat-inner">
      <div class="stat-icon" :style="{ background: bg, color }">
        <component :is="icon" />
      </div>
      <div class="stat-meta">
        <div class="stat-value">{{ value }}</div>
        <div class="stat-title">
          {{ title }}
          <a-tooltip v-if="tip" :title="tip"><QuestionCircleOutlined class="tip-icon" /></a-tooltip>
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup>
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  title: { type: String, required: true },
  value: { type: [Number, String], default: 0 },
  color: { type: String, default: '#2563eb' },
  icon: { type: [Object, Function], required: true },
  tip: { type: String, default: '' },
  // 右上角角标（例如"高风险 3 条"），空则不显示
  corner: { type: String, default: '' },
})

const bg = computed(() => props.color + '1a')
</script>

<style scoped>
.stat-card {
  border-radius: 8px;
  position: relative;
}
.stat-corner {
  position: absolute;
  top: 8px;
  right: 12px;
  font-size: 12px;
  color: #dc2626;
  line-height: 1;
}
.stat-inner {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}
.stat-value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.1;
}
.stat-title {
  margin-top: 2px;
  color: #6b7280;
  font-size: 13px;
}
.tip-icon {
  margin-left: 4px;
  color: #9ca3af;
  cursor: help;
}
</style>
