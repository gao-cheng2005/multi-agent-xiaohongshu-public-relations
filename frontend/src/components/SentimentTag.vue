<!-- 情感标签组件（正面/中性/负面）。 -->
<template>
  <a-tag :color="meta.color">{{ meta.text }}</a-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: String, default: '' },
})

const MAP = {
  正面: { color: 'success', text: '正面' },
  中性: { color: 'default', text: '中性' },
  负面: { color: 'error', text: '负面' },
}

const meta = computed(() => MAP[props.value] || { color: 'default', text: props.value || '未知' })
</script>
