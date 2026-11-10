import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
export default function ProtectedRoute({ role }) { const { user } = useAuth(); const location = useLocation(); if (!user) return <Navigate to="/login" state={{ from: location }} replace />; if (user.mustChangePassword && location.pathname !== '/profile') return <Navigate to="/profile" replace />; if (role && user.role !== role) return <Navigate to={user.role === 'USER' ? '/access-denied' : '/chat'} replace />; return <Outlet /> }
