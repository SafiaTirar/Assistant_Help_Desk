import { Check, MoreHorizontal, Pencil, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink } from 'react-router-dom'
export default function ConversationItem({ conversation, onRename, onDelete, onNavigate }) {
  const [menu, setMenu] = useState(false); const [editing, setEditing] = useState(false); const [title, setTitle] = useState(conversation.title)
  const save = () => { if (title.trim()) onRename(conversation.id, title.trim()); setEditing(false) }
  if (editing) return <div className="conversation-edit"><input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && save()} aria-label="Nouveau titre" /><button onClick={save} aria-label="Enregistrer"><Check size={15} /></button><button onClick={() => setEditing(false)} aria-label="Annuler"><X size={15} /></button></div>
  return <div className="conversation-item"><NavLink to={`/chat/${conversation.id}`} onClick={onNavigate}>{conversation.title}</NavLink><button className="item-menu" onClick={() => setMenu(!menu)} aria-label={`Actions pour ${conversation.title}`}><MoreHorizontal size={17} /></button>{menu && <div className="popover"><button onClick={() => { setEditing(true); setMenu(false) }}><Pencil size={14} /> Renommer</button><button className="danger-text" onClick={() => { onDelete(conversation); setMenu(false) }}><Trash2 size={14} /> Supprimer</button></div>}</div>
}
