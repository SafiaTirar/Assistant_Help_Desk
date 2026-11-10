import { Bot, Check, ChevronDown, Copy, FileText } from 'lucide-react'
import { useState } from 'react'
import StatusBadge from '../common/StatusBadge'
import FeedbackButtons from './FeedbackButtons'

export function MessageSources({ sources = [] }) {
  if (!sources.length) return null
  return <details className="message-sources">
    <summary>
      <span><FileText size={15} /> {sources.length > 1 ? `${sources.length} sources` : '1 source'}</span>
      <ChevronDown className="sources-chevron" size={16} />
    </summary>
    <ol>
      {sources.map((source, index) => {
        const title = source.documentTitle || source.fileName || `Document ${index + 1}`
        const location = [
          source.pages?.length ? `p. ${source.pages.join(', ')}` : null,
          source.section || null,
        ].filter(Boolean).join(' · ')
        return <li key={source.chunkId || `${title}-${index}`}>
          <strong>{title}</strong>
          {location && <span>{location}</span>}
          {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
        </li>
      })}
    </ol>
  </details>
}

export default function ChatMessage({ message }) {
  const [copied, setCopied] = useState(false); const copy = async () => { await navigator.clipboard.writeText(message.content); setCopied(true); setTimeout(() => setCopied(false), 1200) }
  const time = new Intl.DateTimeFormat('fr', { hour: '2-digit', minute: '2-digit' }).format(new Date(message.createdAt))
  if (message.role === 'user') return <article className="message user-message"><div className="avatar user-avatar">UD</div><div><div className="message-head"><strong>Vous</strong><time>{time}</time></div><div className="message-content">{message.content}</div></div></article>
  return <article className="message assistant-message"><div className="avatar assistant-avatar"><Bot size={18} /></div><div><div className="message-head"><strong>Assistant</strong><time>{time}</time></div><div className="message-content">{message.content}</div>{message.status === 'reponse_trouvee' && <p className="generated-note"><Check size={14} /> Réponse générée à partir des informations internes disponibles.</p>}<MessageSources sources={message.sources} /><div className="message-tools"><StatusBadge status={message.status} /><button className="message-action" onClick={copy}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? 'Copié' : 'Copier'}</button><FeedbackButtons message={message} /></div></div></article>
}
