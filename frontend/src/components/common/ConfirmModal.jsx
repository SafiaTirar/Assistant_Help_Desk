import { AlertTriangle, X } from 'lucide-react'
export default function ConfirmModal({ open, title, text, onConfirm, onClose }) {
  if (!open) return null
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title" onMouseDown={(e) => e.stopPropagation()}><button className="icon-button modal-close" onClick={onClose} aria-label="Fermer"><X size={18} /></button><span className="modal-icon"><AlertTriangle /></span><h2 id="confirm-title">{title}</h2><p>{text}</p><div className="modal-actions"><button className="button secondary" onClick={onClose}>Annuler</button><button className="button danger" onClick={onConfirm}>Confirmer</button></div></div></div>
}
