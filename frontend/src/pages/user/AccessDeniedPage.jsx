import { ArrowLeft, ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'
export default function AccessDeniedPage() { return <main className="centered-page"><span className="error-mark"><ShieldX /></span><span className="eyebrow">Accès protégé</span><h1>Vous n’avez pas accès à cet espace.</h1><p>Votre profil utilisateur ne permet pas de consulter les pages administratives.</p><Link className="button" to="/chat"><ArrowLeft size={17} /> Retour au chat</Link></main> }
