import { apiRequest } from './api'

export const getConversations = () => apiRequest('/conversations')

export const getConversation = (id) => apiRequest(`/conversations/${id}`)

export const createConversation = () => apiRequest('/conversations', {
  method: 'POST',
  body: JSON.stringify({ title: 'Nouvelle conversation' }),
})

export const renameConversation = (id, title) => apiRequest(`/conversations/${id}`, {
  method: 'PATCH',
  body: JSON.stringify({ title }),
})

export const deleteConversation = (id) => apiRequest(`/conversations/${id}`, {
  method: 'DELETE',
})

export const submitFeedback = (messageId, feedback) => apiRequest(`/messages/${messageId}/feedback`, {
  method: 'POST',
  body: JSON.stringify(feedback),
})

export const sendMessage = (question, conversationId, signal) => apiRequest('/chat', {
  method: 'POST',
  signal,
  body: JSON.stringify({ question, conversationId }),
})
