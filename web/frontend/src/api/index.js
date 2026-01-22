import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 30000,
})

// 账号相关 API
export const accountsApi = {
  list: (params) => api.get('/accounts', { params }),
  stats: () => api.get('/accounts/stats'),
  get: (email) => api.get(`/accounts/${encodeURIComponent(email)}`),
  create: (data) => api.post('/accounts', data),
  update: (email, data) => api.put(`/accounts/${encodeURIComponent(email)}`, data),
  delete: (email) => api.delete(`/accounts/${encodeURIComponent(email)}`),
  import: (data) => api.post('/accounts/import', data),
  export: (status) => api.get('/accounts/export/all', { params: { status } }),
}

// 浏览器相关 API
export const browsersApi = {
  list: () => api.get('/browsers'),
  sync: () => api.get('/browsers/sync'),
  get: (id) => api.get(`/browsers/${id}`),
  create: (data) => api.post('/browsers', data),
  delete: (id, keepConfig = true) => api.delete(`/browsers/${id}`, { params: { keep_config: keepConfig } }),
  open: (id) => api.post(`/browsers/${id}/open`),
  restore: (email) => api.post(`/browsers/restore/${encodeURIComponent(email)}`),
  batchCreate: (emails, deviceType) => api.post('/browsers/batch/create', { emails, device_type: deviceType }),
}

// 任务相关 API
export const tasksApi = {
  list: () => api.get('/tasks'),
  get: (id) => api.get(`/tasks/${id}`),
  create: (data) => api.post('/tasks', data),
  cancel: (id) => api.delete(`/tasks/${id}`),
}

// 配置相关 API
export const configApi = {
  get: () => api.get('/config'),
  update: (data) => api.put('/config', data),
}

export default api
