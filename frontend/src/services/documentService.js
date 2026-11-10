import { apiDownload, apiRequest } from './api'

export const getDocuments = () => apiRequest('/admin/documents')

export const importDocument = (file) => {
  const body = new FormData()
  body.append('file', file)
  return apiRequest('/admin/documents', { method: 'POST', body })
}

export const updateDocumentKnowledge = (id) => apiRequest(`/admin/documents/${id}/reindex`, { method: 'POST' })
export const archiveDocument = (id) => apiRequest(`/admin/documents/${id}/archive`, { method: 'POST' })
export const restoreDocument = (id) => apiRequest(`/admin/documents/${id}/restore`, { method: 'POST' })
export const toggleDocument = (id) => apiRequest(`/admin/documents/${id}/toggle`, { method: 'PATCH' })
export const deleteDocument = (id) => apiRequest(`/admin/documents/${id}?confirm=true`, { method: 'DELETE' })
export const downloadDocument = (id) => apiDownload(`/admin/documents/${id}/download`)
export const viewDocument = (id) => apiDownload(`/admin/documents/${id}/view`)
export const getDocumentVersions = (id) => apiRequest(`/admin/documents/${id}/versions`)
export const restoreDocumentVersion = (documentId, versionId) => apiRequest(
  `/admin/documents/${documentId}/versions/${versionId}/restore`,
  { method: 'POST' },
)

export const uploadDocumentVersion = (id, file) => {
  const body = new FormData()
  body.append('file', file)
  return apiRequest(`/admin/documents/${id}/versions`, { method: 'POST', body })
}
