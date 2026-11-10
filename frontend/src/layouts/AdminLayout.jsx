import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import AdminSidebar, { AdminMenuButton } from '../components/admin/AdminSidebar'
export default function AdminLayout() { const [open, setOpen] = useState(false); return <div className="admin-shell"><AdminSidebar open={open} onClose={() => setOpen(false)} />{open && <button className="drawer-overlay" onClick={() => setOpen(false)} aria-label="Fermer le menu" />}<main className="admin-main"><div className="admin-mobile-bar"><AdminMenuButton onClick={() => setOpen(true)} /><span>Espace administration</span></div><Outlet /></main></div> }
