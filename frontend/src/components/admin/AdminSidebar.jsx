import { BarChart3, BookOpen, ClipboardCheck, FileQuestion, Files, LogOut, Menu, MessageSquareText, Users, UserRound, X } from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import Brand from '../common/Brand'
const links = [
  ['/admin/dashboard', BarChart3, 'Tableau de bord'], ['/admin/documents', Files, 'Documents'], ['/admin/conversations', MessageSquareText, 'Conversations'], ['/admin/unanswered', FileQuestion, 'Questions sans réponse'], ['/admin/evaluations', ClipboardCheck, 'Évaluations'], ['/admin/contacts', BookOpen, 'Contacts'], ['/admin/users', Users, 'Utilisateurs'],
]
export function AdminMenuButton({ onClick }) { return <button className="icon-button admin-menu-button" onClick={onClick} aria-label="Ouvrir le menu"><Menu /></button> }
export default function AdminSidebar({ open, onClose }) { const { user, logout } = useAuth(); const navigate = useNavigate(); const signOut = async () => { await logout(); navigate('/login') }; return <aside className={`admin-sidebar ${open ? 'mobile-open' : ''}`}><div className="sidebar-top"><Brand /><button className="icon-button mobile-close" onClick={onClose} aria-label="Fermer le menu"><X /></button></div><nav>{links.map(([href, Icon, label]) => <NavLink key={href} to={href} onClick={onClose}><Icon size={19} /><span>{label}</span></NavLink>)}</nav><div className="admin-user"><span className="avatar"><UserRound size={18} /></span><span><strong>{user?.name}</strong><small>Administration</small></span><button className="icon-button" onClick={signOut} aria-label="Se déconnecter"><LogOut size={18} /></button></div></aside> }
