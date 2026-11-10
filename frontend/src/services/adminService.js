import { apiDownload, apiRequest } from './api'

const fallbackQuery = ({ query = '', status = '' } = {}) => {
  const params = new URLSearchParams()
  if (query.trim()) params.set('query', query.trim())
  if (status && status !== 'Tous') params.set('status', status)
  const suffix = params.toString()
  return suffix ? `?${suffix}` : ''
}

export const getAdminDashboard = () => apiRequest('/admin/dashboard')
export const getAdminConversations = () => apiRequest('/admin/conversations')
export const getUnansweredQuestions = (filters) => apiRequest(`/admin/fallbacks${fallbackQuery(filters)}`)
export const updateUnansweredQuestion = (id, data) => apiRequest(`/admin/fallbacks/${id}`, {
  method: 'PATCH',
  body: JSON.stringify(data),
})
export const exportUnansweredQuestions = (filters) => apiDownload(`/admin/fallbacks/export.csv${fallbackQuery(filters)}`)
export const getUsers = () => apiRequest('/admin/users')
export const createUser = (data) => apiRequest('/admin/users', { method: 'POST', body: JSON.stringify(data) })
const updateUser = (id, data) => apiRequest(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const updateUserRole = (id, role) => updateUser(id, { role })
export const updateUserStatus = (id, status) => updateUser(id, { status })
