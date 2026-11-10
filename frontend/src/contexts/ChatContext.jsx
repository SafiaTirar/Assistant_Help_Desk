import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as chatService from '../services/chatService'
import { useAuth } from './AuthContext'

const ChatContext = createContext(null)
export function ChatProvider({ children }) {
  const { user } = useAuth()
  const [conversations, setConversations] = useState([])
  const [error, setError] = useState('')
  const refresh = useCallback(async () => setConversations(await chatService.getConversations()), [])
  useEffect(() => {
    if (user) chatService.getConversations().then((items) => { setConversations(items); setError('') }).catch(() => setError('Le serveur est indisponible.'))
  }, [user])
  const value = useMemo(() => ({ conversations: user ? conversations : [], error, refresh, create: chatService.createConversation, rename: chatService.renameConversation, remove: chatService.deleteConversation, send: chatService.sendMessage, feedback: chatService.submitFeedback }), [conversations, error, refresh, user])
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}
export const useChat = () => useContext(ChatContext)
