import { Send, Square } from 'lucide-react'
import { useRef, useState } from 'react'
export default function ChatInput({ onSend, loading, onStop, initialValue = '' }) {
  const [value, setValue] = useState(initialValue); const ref = useRef(null)
  const resize = (element) => { element.style.height = 'auto'; element.style.height = `${Math.min(element.scrollHeight, 150)}px` }
  const submit = async () => { const question = value.trim(); if (!question || loading) return; setValue(''); if (ref.current) ref.current.style.height = 'auto'; await onSend(question); ref.current?.focus() }
  return <div className="composer-shell"><div className="composer"><textarea ref={ref} rows="1" value={value} onChange={(e) => { setValue(e.target.value); resize(e.target) }} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder="Posez une question sur votre onboarding…" aria-label="Votre question" />{loading ? <button className="send-button stop" onClick={onStop} aria-label="Arrêter la réponse"><Square size={17} fill="currentColor" /></button> : <button className="send-button" onClick={submit} disabled={!value.trim()} aria-label="Envoyer"><Send size={18} /></button>}</div><p>L’assistant peut fournir une réponse incomplète. Vérifiez les informations importantes auprès du service responsable.</p></div>
}
