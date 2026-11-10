import { GraduationCap, Sparkles } from 'lucide-react'

export default function Brand({ compact = false }) {
  return <div className="brand"><span className="brand-mark"><GraduationCap size={22} /><Sparkles size={10} /></span>{!compact && <span><strong>Onboarding</strong><small>Assistant universitaire</small></span>}</div>
}
