<!-- 风险级别标签组件（低/中/高）。 -->
<template>
  <a-tag :color="meta.color">{{ meta.text }}</a-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: String, default: '' },
})

const MAP = {
  高: { color: 'red', text: '高风险' },
  中: { color: 'orange', text: '中风险' },
  低: { color: 'green', text: '低风险' },
}

const meta = computed(() => MAP[props.value] || { color: 'default', text: props.value || '未知' })
</script>
