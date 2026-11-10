import {
  Archive, Download, Eye, FileClock, FilePlus2, FileUp,
  RefreshCw, RotateCcw, Search, Trash2, X,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import DataTable from '../../components/common/DataTable'
import PageHeader from '../../components/common/PageHeader'
import {
  archiveDocument, deleteDocument, downloadDocument, getDocuments,
  getDocumentVersions, importDocument, restoreDocument, toggleDocument,
  restoreDocumentVersion, updateDocumentKnowledge, uploadDocumentVersion, viewDocument,
} from '../../services/documentService'

export default function DocumentsPage() {
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Tous')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [pendingAction, setPendingAction] = useState('')
  const [versionHistory, setVersionHistory] = useState(null)
  const input = useRef()
  const versionInput = useRef()
  const versionDocumentId = useRef('')

  const load = useCallback(async () => {
    try {
      setItems(await getDocuments())
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  useEffect(() => {
    if (!items.some((item) => item.status === 'Traitement en cours')) return undefined
    const timer = window.setInterval(load, 1200)
    return () => window.clearInterval(timer)
  }, [items, load])

  const action = async (fn, id, message) => {
    try {
      setPendingAction(id)
      setError('')
      setNotice('')
      await fn(id)
      await load()
      setNotice(message)
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
    }
  }

  const upload = async (event) => {
    const file = event.target.files[0]
    if (!file) return
    try {
      setPendingAction('upload')
      setError('')
      setNotice('')
      await importDocument(file)
      await load()
      setNotice('Import accepté. Le traitement continue en arrière-plan.')
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
      event.target.value = ''
    }
  }

  const uploadVersion = async (event) => {
    const file = event.target.files[0]
    const id = versionDocumentId.current
    if (!file || !id) return
    try {
      setPendingAction(id)
      setError('')
      setNotice('')
      await uploadDocumentVersion(id, file)
      await load()
      setNotice('Nouvelle version acceptée. L’ancienne reste active jusqu’à validation du nouvel index.')
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
      versionDocumentId.current = ''
      event.target.value = ''
    }
  }

  const openFile = async (row, download = false) => {
    try {
      setPendingAction(row.id)
      setError('')
      const blob = await (download ? downloadDocument(row.id) : viewDocument(row.id))
      const url = URL.createObjectURL(blob)
      if (download) {
        const link = document.createElement('a')
        link.href = url
        link.download = row.fileName
        link.click()
      } else {
        window.open(url, '_blank', 'noopener,noreferrer')
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
    }
  }

  const showVersions = async (row) => {
    try {
      setPendingAction(row.id)
      const versions = await getDocumentVersions(row.id)
      setVersionHistory({ document: row, versions })
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
    }
  }

  const remove = async (row) => {
    if (!window.confirm(`Supprimer définitivement « ${row.title} » et toutes ses versions ?`)) return
    await action(deleteDocument, row.id, 'Document et index supprimés définitivement.')
  }

  const restoreVersion = async (version) => {
    try {
      setPendingAction(version.id)
      await restoreDocumentVersion(versionHistory.document.id, version.id)
      setVersionHistory(null)
      await load()
      setNotice(`Restauration de la version ${version.version} lancée.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction('')
    }
  }

  const rows = items.filter((item) => (
    (status === 'Tous' || item.status === status)
    && `${item.title} ${item.fileName}`.toLowerCase().includes(query.toLowerCase())
  ))

  return <div className="admin-page">
    <PageHeader title="Documents" description="Gérez les documents internes disponibles pour l’assistant." actions={<>
      <input ref={input} type="file" accept=".docx,.pdf" hidden onChange={upload} />
      <input ref={versionInput} type="file" accept=".docx,.pdf" hidden onChange={uploadVersion} />
      <button className="button" disabled={Boolean(pendingAction)} onClick={() => input.current.click()}>
        <FileUp size={17} /> {pendingAction === 'upload' ? 'Import en cours…' : 'Importer un document'}
      </button>
    </>} />
    {notice && <div className="inline-notice">{notice}</div>}
    {error && <p className="auth-error">{error}</p>}
    <div className="toolbar">
      <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher un document" /></label>
      <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filtrer par statut">
        <option>Tous</option><option>Prêt</option><option>Traitement en cours</option><option>Désactivé</option><option>Archivé</option><option>Erreur</option>
      </select>
    </div>
    <DataTable rows={rows} empty={loading ? 'Chargement des documents…' : 'Aucun document à afficher.'} columns={[
      { key: 'title', label: 'Document', render: (row) => <span className="table-primary"><strong>{row.title}</strong><small>{row.fileName}</small>{row.errorMessage && <small className="document-error">{row.errorMessage}</small>}</span> },
      { key: 'format', label: 'Format' },
      { key: 'version', label: 'Version', render: (row) => <button className="text-button" title={`Versions : ${row.versions.join(', ')}`} onClick={() => showVersions(row)}><FileClock size={14} /> {row.version}</button> },
      { key: 'pages', label: 'Pages' },
      { key: 'addedAt', label: 'Ajouté le' },
      { key: 'status', label: 'Statut', render: (row) => <span className="document-status"><span className="business-status">{row.status}</span>{row.status === 'Traitement en cours' && <span className="document-progress"><span><i style={{ width: `${row.progress || 0}%` }} /></span>{row.progress || 0} %</span>}</span> },
      { key: 'actions', label: 'Actions', render: (row) => <div className="table-actions">
        <button disabled={Boolean(pendingAction)} onClick={() => openFile(row)}><Eye size={14} /> Consulter</button>
        <button disabled={Boolean(pendingAction)} onClick={() => openFile(row, true)}><Download size={14} /> Télécharger</button>
        {row.status === 'Archivé' ? <>
          <button disabled={Boolean(pendingAction)} onClick={() => action(restoreDocument, row.id, 'Document restauré.')}><RotateCcw size={14} /> Restaurer</button>
          <button className="danger-text" disabled={Boolean(pendingAction)} onClick={() => remove(row)}><Trash2 size={14} /> Supprimer</button>
        </> : <>
          <button disabled={Boolean(pendingAction) || row.status === 'Traitement en cours'} onClick={() => action(toggleDocument, row.id, `Document ${row.active ? 'désactivé' : 'activé'}.`)}>{row.active ? 'Désactiver' : 'Activer'}</button>
          <button disabled={Boolean(pendingAction) || row.status === 'Traitement en cours'} onClick={() => action(updateDocumentKnowledge, row.id, 'Réindexation lancée.')}><RefreshCw size={14} /> Réindexer</button>
          <button disabled={Boolean(pendingAction) || row.status === 'Traitement en cours'} onClick={() => { versionDocumentId.current = row.id; versionInput.current.click() }}><FilePlus2 size={14} /> Nouvelle version</button>
          <button disabled={Boolean(pendingAction) || row.status === 'Traitement en cours'} onClick={() => action(archiveDocument, row.id, 'Document archivé.')}><Archive size={14} /> Archiver</button>
        </>}
      </div> },
    ]} />
    {versionHistory && <div className="modal-backdrop"><section className="modal version-modal"><button className="icon-button modal-close" onClick={() => setVersionHistory(null)}><X size={18} /></button><h2>Versions de {versionHistory.document.title}</h2><div className="version-list">{versionHistory.versions.map((version) => <article key={version.id}><strong>Version {version.version}{version.isCurrent ? ' · active' : ''}</strong><span>{version.fileName}</span><small>{version.status} · {version.pages ?? '—'} page(s) · {version.chunks ?? '—'} chunk(s)</small>{version.errorMessage && <small className="document-error">{version.errorMessage}</small>}{!version.isCurrent && version.status !== 'Erreur' && <button className="text-button" disabled={Boolean(pendingAction)} onClick={() => restoreVersion(version)}><RotateCcw size={14} /> Restaurer cette version</button>}</article>)}</div></section></div>}
  </div>
}
