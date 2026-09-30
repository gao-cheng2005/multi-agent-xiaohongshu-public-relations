// 文件职责：axios 实例（统一前缀与超时、错误处理拦截器）。
import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 300000,
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error?.response?.data?.detail || error?.message || '请求失败'
    return Promise.reject(new Error(message))
  },
)

export default http
