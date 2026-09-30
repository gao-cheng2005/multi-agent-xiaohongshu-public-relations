// 文件职责：后端 API 封装，按业务分组导出。
                                           
import http from './http'

             
export const healthApi = () => http.get('/health')
export const infoApi = () => http.get('/info')
export const statsApi = () => http.get('/stats')

              
export const listKeywords = () => http.get('/keywords')
export const createKeyword = (keyword, platform = 'xiaohongshu') =>
  http.post('/keywords', { keyword, platform })
export const deleteKeyword = (id) => http.delete(`/keywords/${id}`)
// 清空全部关键词
export const clearKeywords = () => http.post('/keywords/clear')

           
// 采集（关键词或 URL），耗时较长需前端耐心等待
export const collectApi = (payload) => http.post('/collect', payload)

             
export const listContents = (limit = 100) => http.get('/contents', { params: { limit } })
// 处理记录：已处理笔记列表（支持筛选，默认按处理时间排序）
export const listProcessedContents = (params = {}) => http.get('/contents/processed', { params })
// 按条件删除笔记（参数全空=清空全部；content_id=删单条）
export const deleteContents = (params = {}) => http.delete('/contents', { params })
// 筛选选项（来源/关键词），供内容页与预警页共用
export const listContentFilters = () => http.get('/contents/filters')
export const listComments = (contentId) => http.get(`/contents/${contentId}/comments`)
                                        
// 实时刷新签名链接（token 有时效，点击时现取）。
export const refreshNoteUrl = (contentId) => http.post(`/contents/${contentId}/open`)

           
export const listAlerts = (status) => http.get('/alerts', { params: status ? { status } : {} })
export const handleAlert = (id) => http.post(`/alerts/${id}/handle`)
export const handleNoteAlerts = (noteId) => http.post(`/alerts/note/${noteId}/handle`)

             
// 应对方案列表（可按笔记过滤）
export const listPlans = (contentId) => http.get('/plans', { params: contentId ? { content_id: contentId } : {} })
export const createPlan = (contentId) => http.post('/plans', { content_id: contentId, trigger: 'manual' })
// 手动触发生成应对方案（异步执行，前端轮询看结果）
export const generatePlanAsync = (contentId) => http.post('/plans/generate', { content_id: contentId })
export const decidePlan = (id, status, decidedBy) => http.post(`/plans/${id}/decide`, { status, decided_by: decidedBy })
// 完成处理：已生成方案或"无需处理"的笔记都走这里，完成后移入处理记录
export const completePlan = (contentId) => http.post('/plans/complete', { content_id: contentId })
// 按人工修改要求重新生成文案（渠道不变）
export const regeneratePlan = (contentId, feedback) => http.post('/plans/regenerate', { content_id: contentId, feedback })

             
export const getTrend = (days = 30) => http.get('/analytics/trend', { params: { days } })
// 总览趋势：近 N 天每天爬取笔记数 + 中高风险笔记数（可按产品过滤）
export const overviewTrend = (params = {}) => http.get('/analytics/overview_trend', { params })
// 最近的中高风险未处理笔记（与"待处理预警"同口径）
export const recentPendingNotes = (limit = 5) => http.get('/contents/recent-pending', { params: { limit } })
// 产品问题分析（单产品）
export const productAnalysis = (product) => http.get('/analytics/product', { params: { product } })
// 报表：产品优化建议（Agent 生成）
export const productReport = (product) => http.post('/analytics/product/report', { product })
// 读取自动生成的产品优化建议缓存
export const getProductReport = (product) => http.get('/analytics/product/report', { params: { product } })
// 归并待确认维度
export const productMerge = (product) => http.post('/analytics/product/merge', { product })
// 人工确认/忽略维度
export const confirmDimension = (product, dimension, confirmed) =>
  http.post('/analytics/dimension/confirm', { product, dimension, confirmed })
export const getHotwords = (limit = 20) => http.get('/analytics/hotwords', { params: { limit } })
export const getEffect = () => http.get('/analytics/effect')
// 导出报表（blob 流）。
export const exportReport = (format = 'markdown') =>
  http.get('/reports/export', { params: { format }, responseType: 'blob' })

             
// 大模型（硅基流动）配置：精选模型清单 / 当前模型 / 切换模型
// API Key 由系统内置（公司密钥），前端不涉及 key 的填写与读取
export const listLlmModels = () => http.get('/llm/models')
export const getLlmConfig = () => http.get('/llm/config')
export const setLlmConfig = (model) => http.post('/llm/config', { model })