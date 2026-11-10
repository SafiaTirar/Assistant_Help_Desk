import { Menu } from 'lucide-react'
import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import ConversationSidebar from '../components/chat/ConversationSidebar'
export default function UserLayout() { const [collapsed, setCollapsed] = useState(false); const [mobile, setMobile] = useState(false); return <div className={`user-shell ${collapsed ? 'sidebar-collapsed' : ''}`}><ConversationSidebar collapsed={collapsed} onCollapse={() => setCollapsed(!collapsed)} mobileOpen={mobile} onMobileClose={() => setMobile(false)} />{mobile && <button className="drawer-overlay" onClick={() => setMobile(false)} aria-label="Fermer le menu" />}<main className="user-main"><header className="user-header"><button className="icon-button mobile-menu" onClick={() => setMobile(true)} aria-label="Ouvrir le menu"><Menu /></button><span>Onboarding Assistant</span><span className="demo-pill">Documents importés</span></header><Outlet /></main></div> }
