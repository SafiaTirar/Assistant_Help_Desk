import { AuthProvider } from './contexts/AuthContext'
import { ChatProvider } from './contexts/ChatContext'
import AppRoutes from './routes/AppRoutes'

export default function App() {
  return <AuthProvider><ChatProvider><AppRoutes /></ChatProvider></AuthProvider>
}
