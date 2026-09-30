// 文件职责：全局状态（Pinia），集中管理各模块数据与操作。
                                
import { defineStore } from 'pinia'
import * as api from '../api'

export const useAppStore = defineStore('app', {
  state: () => ({
                                                                          
    info: {
      collect_mode: 'opencli',
      llm_provider: 'siliconflow',
      llm_model: '',
      llm_configured: false,
      sentiment_mode: 'auto',
      db_path: '',
    },
    stats: { notes: 0, comments: 0, open_alerts: 0, high_alerts: 0, sentiment: {}, risk: {} },
    keywords: [],
    contents: [],
    processedContents: [],
    alerts: [],
    contentFilters: [],
    plans: [],
    llmModels: [],
    llmConfig: { provider: 'siliconflow', model: '', configured: false, models: [] },
    productAnalysis: null,
    loading: false,
  }),
  actions: {
    async refreshInfo() {
      this.info = await api.infoApi()
    },
    async deleteContents(params = {}) {
      const res = await api.deleteContents(params)
      await Promise.allSettled([this.refreshContents(), this.refreshStats()])
      return res
    },
    async refreshProductAnalysis(product) {
      this.productAnalysis = await api.productAnalysis(product)
      return this.productAnalysis
    },
    async refreshStats() {
      this.stats = await api.statsApi()
    },
    async refreshKeywords() {
      this.keywords = await api.listKeywords()
    },
    // 各 refresh* 为拉取数据；generatePlan 调后端生成方案，decidePlan 提交决策，generatePlan 调后端生成方案，decidePlan 提交人工决策
    async refreshContents(limit = 100) {
      this.contents = await api.listContents(limit)
    },
    async refreshProcessed(params = {}) {
      this.processedContents = await api.listProcessedContents(params)
    },
    async refreshContentFilters() {
      this.contentFilters = await api.listContentFilters()
    },
    async refreshAlerts(status) {
      this.alerts = await api.listAlerts(status)
    },
    async refreshPlans(contentId) {
      this.plans = await api.listPlans(contentId)
    },
    async generatePlan(contentId) {
      const res = await api.createPlan(contentId)
      await this.refreshPlans()
      return res
    },
    async decidePlan(planId, status, decidedBy) {
      await api.decidePlan(planId, status, decidedBy)
      await this.refreshPlans()
    },
    async completePlan(contentId) {
      await api.completePlan(contentId)
      await Promise.allSettled([
        this.refreshContents(),
        this.refreshProcessed(),
        this.refreshStats(),
      ])
    },
    async regeneratePlan(contentId, feedback) {
      const res = await api.regeneratePlan(contentId, feedback)
      await this.refreshPlans()
      return res
    },
    async refreshLlmModels() {
      this.llmModels = await api.listLlmModels()
    },
    async refreshLlmConfig() {
      this.llmConfig = await api.getLlmConfig()
    },
    async updateLlmModel(model) {
      const res = await api.setLlmConfig(model)
      await Promise.allSettled([this.refreshLlmConfig(), this.refreshInfo()])
      return res
    },
    async collect(payload) {
      return api.collectApi(payload)
    },
    async addKeyword(keyword) {
      await api.createKeyword(keyword)
      await this.refreshKeywords()
    },
    async removeKeyword(id) {
      await api.deleteKeyword(id)
      await this.refreshKeywords()
    },
    async clearKeywords() {
      const res = await api.clearKeywords()
      await this.refreshKeywords()
      return res
    },
    async markHandled(id) {
      await api.handleAlert(id)
      await this.refreshAlerts()
    },
    async markNoteHandled(noteId) {
      await api.handleNoteAlerts(noteId)
      await this.refreshAlerts()
    },
  },
})
