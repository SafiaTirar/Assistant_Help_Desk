import { ChevronLeft, ChevronRight, LogOut, MessageSquarePlus, Search, UserRound, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useChat } from '../../contexts/ChatContext'
import Brand from '../common/Brand'
import ConfirmModal from '../common/ConfirmModal'
import ConversationItem from './ConversationItem'

const renderTimestamp = Date.now()

export default function ConversationSidebar({ collapsed, onCollapse, mobileOpen, onMobileClose }) {
  const { user, logout } = useAuth(); const { conversations, create, rename, remove, refresh } = useChat(); const [search, setSearch] = useState(''); const [target, setTarget] = useState(null); const navigate = useNavigate()
  const groups = useMemo(() => { const filtered = conversations.filter((item) => item.title.toLowerCase().includes(search.toLowerCase())); const result = { 'Aujourd’hui': [], '7 derniers jours': [], 'Plus anciennes': [] }; filtered.forEach((item) => { const days = (renderTimestamp - new Date(item.updatedAt)) / 86400000; result[days < 1 ? 'Aujourd’hui' : days < 7 ? '7 derniers jours' : 'Plus anciennes'].push(item) }); return result }, [conversations, search])
  const add = async () => { const conversation = await create(); await refresh(); navigate(`/chat/${conversation.id}`); onMobileClose() }
  const doRename = async (id, title) => { await rename(id, title); refresh() }
  const doDelete = async () => { await remove(target.id); setTarget(null); await refresh(); navigate('/chat') }
  const signOut = async () => { await logout(); navigate('/login') }
  return <><aside className={`chat-sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}><div className="sidebar-top"><Brand compact={collapsed} /><button className="icon-button mobile-close" onClick={onMobileClose} aria-label="Fermer le menu"><X /></button></div><button className="new-chat" onClick={add}><MessageSquarePlus size={19} />{!collapsed && 'Nouvelle conversation'}</button>{!collapsed && <><label className="sidebar-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher" aria-label="Rechercher une conversation" /></label><nav className="conversation-list" aria-label="Conversations">{Object.entries(groups).map(([label, items]) => items.length > 0 && <section key={label}><h2>{label}</h2>{items.map((item) => <ConversationItem key={item.id} conversation={item} onRename={doRename} onDelete={setTarget} onNavigate={onMobileClose} />)}</section>)}</nav></>}<div className="sidebar-footer">{!collapsed && <Link className="profile-summary" to="/profile" onClick={onMobileClose}><span className="avatar user-avatar"><UserRound size={18} /></span><span><strong>{user?.name}</strong><small>{user?.role}</small></span></Link>}<button className="logout-button" onClick={signOut} aria-label="Se déconnecter"><LogOut size={18} />{!collapsed && 'Déconnexion'}</button><button className="collapse-button" onClick={onCollapse} aria-label={collapsed ? 'Développer la barre latérale' : 'Réduire la barre latérale'}>{collapsed ? <ChevronRight /> : <><ChevronLeft size={18} /> Réduire</>}</button></div></aside><ConfirmModal open={!!target} title="Supprimer la conversation ?" text="Cette action supprimera définitivement cette conversation et ses messages." onConfirm={doDelete} onClose={() => setTarget(null)} /></>
}
