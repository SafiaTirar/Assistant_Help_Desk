import { createContext, useContext, useMemo, useState } from 'react'
import * as authService from '../services/authService'

const AuthContext = createContext(null)
export function AuthProvider({ children }) {
  const [user, setUser] = useState(authService.getCurrentUser)
  const value = useMemo(() => ({ user, login: async (email, password) => { const next = await authService.login(email, password); setUser(next); return next }, changePassword: async (currentPassword, newPassword) => { const next = await authService.changePassword(currentPassword, newPassword); setUser(next); return next }, logout: async () => { await authService.logout(); setUser(null) } }), [user])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export const useAuth = () => useContext(AuthContext)
