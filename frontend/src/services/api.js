export const API_URL = import.meta.env?.VITE_API_URL || '/api'
export const simulate = (value, delay = 250) => new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), delay))
const TOKEN_KEY = 'onboarding_access_token'

export async function apiRequest(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY)
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(!isFormData ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Erreur de communication avec le serveur')
  }

  return response.status === 204 ? null : response.json()
}

export async function apiDownload(path) {
  const token = localStorage.getItem(TOKEN_KEY)
  const response = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Erreur de communication avec le serveur')
  }

  return response.blob()
}
