import { apiRequest } from './api'

const SESSION_KEY = 'onboarding_session'
const TOKEN_KEY = 'onboarding_access_token'

const saveSession = ({ accessToken, user }) => {
  localStorage.setItem(TOKEN_KEY, accessToken)
  localStorage.setItem(SESSION_KEY, JSON.stringify(user))
  return user
}

export const login = async (email, password) => saveSession(await apiRequest('/auth/login', {
  method: 'POST',
  body: JSON.stringify({ email, password }),
}))

export const changePassword = async (currentPassword, newPassword) => {
  const user = await apiRequest('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ currentPassword, newPassword }),
  })
  localStorage.setItem(SESSION_KEY, JSON.stringify(user))
  return user
}

export const logout = async () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(SESSION_KEY)
}

export const getCurrentUser = () => {
  try {
    if (!localStorage.getItem(TOKEN_KEY)) return null
    return JSON.parse(localStorage.getItem(SESSION_KEY))
  } catch {
    return null
  }
}
