import { LockKeyhole, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import Brand from '../../components/common/Brand'
import { useAuth } from '../../contexts/AuthContext'

export default function LoginPage() {
  const { user, login } = useAuth(); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [loading, setLoading] = useState(false); const [error, setError] = useState(''); const navigate = useNavigate()
  if (user) return <Navigate to={user.mustChangePassword ? '/profile' : user.role === 'ADMIN' ? '/admin/dashboard' : '/chat'} replace />
  const submit = async (event) => { event.preventDefault(); setLoading(true); setError(''); try { const next = await login(email, password); navigate(next.mustChangePassword ? '/profile' : next.role === 'ADMIN' ? '/admin/dashboard' : '/chat') } catch (err) { setError(err.message) } finally { setLoading(false) } }
  return <main className="login-page"><section className="login-intro"><Brand /><div><span className="login-orbit"><Sparkles /></span><p className="eyebrow">Une arrivée plus sereine</p><h1>Votre parcours universitaire, plus simple dès le premier jour.</h1><p>Un espace clair pour retrouver les informations utiles à l’onboarding des enseignants-chercheurs.</p></div><div className="trust-line"><ShieldCheck size={18} /> Accès sécurisé et comptes gérés par l’administrateur</div></section><section className="login-panel"><form className="login-card auth-form" onSubmit={submit}><span className="lock-mark"><LockKeyhole /></span><span className="eyebrow">Bienvenue</span><h2>Connectez-vous</h2><p>Utilisez le compte créé par votre administrateur.</p><label>Adresse e-mail<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></label><label>Mot de passe<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength="8" autoComplete="current-password" /></label>{error && <p className="auth-error">{error}</p>}<button className="button" type="submit" disabled={loading}>{loading ? 'Connexion en cours…' : 'Se connecter'}</button></form></section></main>
}
