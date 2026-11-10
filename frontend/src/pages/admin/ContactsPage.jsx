import { Pencil, Plus, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import DataTable from '../../components/common/DataTable'
import PageHeader from '../../components/common/PageHeader'
import { createContact, getContacts, updateContact } from '../../services/contactService'

const blank = {
  name: '', service: '', email: '', phone: '', step: '', visible: false,
  active: true, document: '', page: '',
}

export default function ContactsPage() {
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getContacts().then(setItems).catch((err) => setError(err.message))
  }, [])

  const save = async (event) => {
    event.preventDefault()
    setError('')
    try {
      const saved = form.id
        ? await updateContact(form.id, form)
        : await createContact(form)
      setItems((current) => form.id
        ? current.map((item) => item.id === saved.id ? saved : item)
        : [...current, saved])
      setForm(null)
    } catch (err) {
      setError(err.message)
    }
  }

  const toggle = async (contact) => {
    setError('')
    try {
      const saved = await updateContact(contact.id, { active: !contact.active })
      setItems((current) => current.map((item) => item.id === saved.id ? saved : item))
    } catch (err) {
      setError(err.message)
    }
  }

  const rows = items.filter((item) =>
    `${item.name} ${item.service} ${item.step || ''}`.toLowerCase().includes(query.toLowerCase()))

  return <div className="admin-page">
    <PageHeader
      title="Contacts"
      description="Configurez les interlocuteurs pouvant accompagner les utilisateurs."
      actions={<button className="button" onClick={() => setForm({ ...blank })}><Plus size={17} /> Ajouter un contact</button>}
    />
    {error && <p className="auth-error">{error}</p>}
    <div className="toolbar">
      <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher un contact" /></label>
    </div>
    <DataTable rows={rows} columns={[
      { key: 'name', label: 'Nom', render: (item) => <span className="table-primary"><strong>{item.name}</strong><small>{item.service}</small></span> },
      { key: 'email', label: 'E-mail', render: (item) => item.email || 'Non configuré' },
      { key: 'phone', label: 'Téléphone', render: (item) => item.phone || 'Non configuré' },
      { key: 'step', label: 'Étape', render: (item) => item.step || 'Non configurée' },
      { key: 'visible', label: 'Visible utilisateur', render: (item) => item.visible ? 'Oui' : 'Non' },
      { key: 'active', label: 'Statut', render: (item) => item.active ? 'Actif' : 'Inactif' },
      { key: 'source', label: 'Origine', render: (item) => `${item.document || 'Non configuré'}${item.page ? ` · p. ${item.page}` : ''}` },
      { key: 'actions', label: 'Actions', render: (item) => <div className="table-actions"><button onClick={() => setForm({ ...item })}><Pencil size={14} /> Modifier</button><button onClick={() => toggle(item)}>{item.active ? 'Désactiver' : 'Activer'}</button></div> },
    ]} />
    {form && <div className="modal-backdrop"><form className="modal form-modal" onSubmit={save}>
      <button type="button" className="icon-button modal-close" onClick={() => setForm(null)} aria-label="Fermer"><X /></button>
      <h2>{form.id ? 'Modifier le contact' : 'Ajouter un contact'}</h2>
      {[['name', 'Nom'], ['service', 'Fonction ou service'], ['email', 'Adresse électronique'], ['phone', 'Téléphone'], ['step', 'Étape associée'], ['document', 'Document source'], ['page', 'Page source']].map(([key, label]) => <label key={key}>{label}<input type={key === 'email' ? 'email' : 'text'} value={form[key] || ''} onChange={(event) => setForm({ ...form, [key]: event.target.value })} required={['name', 'service'].includes(key)} /></label>)}
      <label className="check-label"><input type="checkbox" checked={form.visible} onChange={(event) => setForm({ ...form, visible: event.target.checked })} /> Peut être communiqué aux utilisateurs</label>
      <button className="button" type="submit">Enregistrer</button>
    </form></div>}
  </div>
}
