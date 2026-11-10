import { apiRequest } from './api'

export const getContacts = () => apiRequest('/admin/contacts')
export const createContact = (data) => apiRequest('/admin/contacts', {
  method: 'POST',
  body: JSON.stringify(data),
})
export const updateContact = (id, data) => apiRequest(`/admin/contacts/${id}`, {
  method: 'PATCH',
  body: JSON.stringify(data),
})
