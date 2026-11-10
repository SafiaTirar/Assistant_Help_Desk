import { useState } from 'react'
import { ThumbsDown, ThumbsUp, X } from 'lucide-react'
import { useChat } from '../../contexts/ChatContext'

export default function FeedbackButtons({ message }) {
  const { feedback } = useChat(); const [selected, setSelected] = useState(message.feedback?.type || ''); const [open, setOpen] = useState(false); const [reason, setReason] = useState('réponse incorrecte'); const [comment, setComment] = useState('')
  const useful = async () => { setSelected('utile'); setOpen(false); await feedback(message.id, { type: 'utile' }) }
  const submit = async (e) => { e.preventDefault(); setSelected('non_utile'); setOpen(false); await feedback(message.id, { type: 'non_utile', reason, comment }) }
  return <div className="feedback"><button className={`message-action ${selected === 'utile' ? 'selected' : ''}`} onClick={useful}><ThumbsUp size={15} /> Utile</button><button className={`message-action ${selected === 'non_utile' ? 'selected' : ''}`} onClick={() => setOpen(true)}><ThumbsDown size={15} /> Non utile</button>{open && <form className="feedback-form" onSubmit={submit}><button type="button" className="icon-button feedback-close" onClick={() => setOpen(false)} aria-label="Fermer"><X size={16} /></button><label>Pourquoi cette réponse n’est-elle pas utile ?<select value={reason} onChange={(e) => setReason(e.target.value)}><option>réponse incorrecte</option><option>réponse incomplète</option><option>question mal comprise</option><option>autre</option></select></label><label>Commentaire facultatif<textarea rows="2" value={comment} onChange={(e) => setComment(e.target.value)} /></label><button className="button small" type="submit">Envoyer le retour</button></form>}</div>
}
