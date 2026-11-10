import { Download, MessageSquareMore, Save, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DataTable from '../../components/common/DataTable'
import PageHeader from '../../components/common/PageHeader'
import {
  exportUnansweredQuestions,
  getUnansweredQuestions,
  updateUnansweredQuestion,
} from '../../services/adminService'

const formatDate = (value) => new Date(value).toLocaleDateString('fr')

export default function UnansweredPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [comments, setComments] = useState({})
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Tous')
  const [loading, setLoading] = useState(true)
  const [pendingAction, setPendingAction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    getUnansweredQuestions()
      .then((fallbackItems) => {
        setItems(fallbackItems)
        setComments(Object.fromEntries(fallbackItems.map((item) => [item.id, item.comment || ''])))
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const update = async (id, data) => {
    try {
      setPendingAction(id)
      setError('')
      setNotice('')
      const updated = await updateUnansweredQuestion(id, data)
      setItems((current) => current.map((item) => item.id === id ? updated : item))
      if (Object.hasOwn(data, 'comment')) {
        setComments((current) => ({ ...current, [id]: updated.comment || '' }))
      }
      setNotice('Analyse enregistrée dans PostgreSQL.')
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
    }
  }

  const exportCsv = async () => {
    try {
      setPendingAction('export')
      setError('')
      const blob = await exportUnansweredQuestions({ query, status })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'questions-sans-reponse.csv'
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
    }
  }

  const rows = items.filter((item) => (
    (status === 'Tous' || item.status === status)
    && item.question.toLowerCase().includes(query.toLowerCase())
  ))

  return <div className="admin-page">
    <PageHeader
      title="Questions sans réponse"
      description="Identifiez les lacunes et suivez leur analyse."
      actions={<button className="button secondary" disabled={Boolean(pendingAction)} onClick={exportCsv}><Download size={17} /> Exporter CSV</button>}
    />
    {notice && <div className="inline-notice">{notice}</div>}
    {error && <p className="auth-error">{error}</p>}
    <div className="toolbar">
      <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher une question" /></label>
      <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filtrer par analyse"><option>Tous</option><option>À analyser</option><option>Analysée</option><option>Information manquante</option><option>Hors périmètre</option></select>
    </div>
    <DataTable
      rows={rows}
      empty={loading ? 'Chargement des questions…' : 'Aucune question sans réponse à afficher.'}
      columns={[
        { key: 'question', label: 'Question', render: (row) => <strong>{row.question}</strong> },
        { key: 'occurrences', label: 'Occurrences' },
        { key: 'first', label: 'Première', render: (row) => formatDate(row.first) },
        { key: 'last', label: 'Dernière', render: (row) => formatDate(row.last) },
        { key: 'status', label: 'Analyse', render: (row) => <select disabled={pendingAction === row.id} value={row.status} onChange={(event) => update(row.id, { status: event.target.value })}><option>À analyser</option><option>Analysée</option><option>Information manquante</option><option>Hors périmètre</option></select> },
        { key: 'comment', label: 'Remarque', render: (row) => <input className="table-input" value={comments[row.id] ?? ''} placeholder="Ajouter une remarque" onChange={(event) => setComments((current) => ({ ...current, [row.id]: event.target.value }))} /> },
        { key: 'actions', label: 'Actions', render: (row) => <div className="table-actions"><button disabled={pendingAction === row.id} onClick={() => update(row.id, { comment: comments[row.id] || '' })}><Save size={14} /> {pendingAction === row.id ? 'Enregistrement…' : 'Enregistrer'}</button><button onClick={() => navigate(`/admin/conversations?query=${encodeURIComponent(row.question)}`)} title={`${row.occurrences} conversation(s) associée(s)`}><MessageSquareMore size={14} /> Conversations</button></div> },
      ]}
    />
  </div>
}
