import {
  CheckCircle2, Download, Eye, FileUp, Pencil, Play, Plus, Trash2, X, XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import DataTable from '../../components/common/DataTable'
import PageHeader from '../../components/common/PageHeader'
import {
  createEvaluationQuestion,
  deleteEvaluationQuestion,
  exportEvaluationRun,
  getEvaluationQuestions,
  getEvaluationRun,
  getEvaluationRuns,
  importEvaluationQuestions,
  runEvaluation,
  updateEvaluationQuestion,
} from '../../services/evaluationService'

const blankQuestion = {
  code: '',
  category: 'reponse_explicite',
  datasetSplit: 'calibration',
  question: '',
  expectedStatus: 'reponse_trouvee',
  expectedAnswer: '',
  expectedPages: [],
  expectedSections: [],
  expectedDocuments: [],
  requiredTerms: [],
  history: [],
  active: true,
}

const parseList = (value) => value.split(',').map((item) => item.trim()).filter(Boolean)
const parsePages = (value) => parseList(value).map(Number).filter(Number.isInteger)
const formatDate = (value) => value ? new Date(value).toLocaleString('fr') : '—'
const formatDuration = (value) => value == null ? '—' : (value / 1000).toFixed(2) + ' s'

const normalizeImportedQuestion = (item, index) => ({
  code: item.code || item.id || 'Q' + String(index + 1).padStart(3, '0'),
  category: item.category || item.categorie || 'non_classee',
  question: item.question,
  expectedStatus: item.expectedStatus || item.expected_status || item.statut_attendu,
  expectedAnswer: item.expectedAnswer || item.expected_answer || item.reponse_reference || '',
  expectedPages: item.expectedPages || item.expected_pages || item.pages_attendues || [],
  expectedSections: item.expectedSections || item.expected_sections || item.sections_attendues || [],
  expectedDocuments: item.expectedDocuments || item.expected_documents || [],
  datasetSplit: item.datasetSplit || item.dataset_split || 'calibration',
  requiredTerms: item.requiredTerms || item.required_terms || [],
  history: item.history || [],
  active: item.active ?? true,
})

function QuestionForm({ value, onClose, onSave }) {
  const [form, setForm] = useState({
    ...value,
    pagesText: (value.expectedPages || []).join(', '),
    sectionsText: (value.expectedSections || []).join(', '),
    termsText: (value.requiredTerms || []).join(', '),
    documentsText: (value.expectedDocuments || []).join(', '),
  })
  const change = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const submit = (event) => {
    event.preventDefault()
    onSave({
      code: form.code.trim(),
      category: form.category.trim(),
      datasetSplit: form.datasetSplit,
      question: form.question.trim(),
      expectedStatus: form.expectedStatus,
      expectedAnswer: form.expectedAnswer.trim(),
      expectedPages: parsePages(form.pagesText),
      expectedSections: parseList(form.sectionsText),
      expectedDocuments: parseList(form.documentsText),
      requiredTerms: parseList(form.termsText),
      history: form.history || [],
      active: form.active,
    })
  }

  return <div className="modal-backdrop"><form className="modal form-modal evaluation-form" onSubmit={submit}>
    <button type="button" className="icon-button modal-close" onClick={onClose} aria-label="Fermer"><X /></button>
    <h2>{value.id ? 'Modifier la question' : 'Ajouter une question'}</h2>
    <div className="evaluation-form-grid">
      <label>Code<input value={form.code} onChange={change('code')} required /></label>
      <label>Catégorie<input value={form.category} onChange={change('category')} required /></label>
      <label>Jeu<select value={form.datasetSplit} onChange={change('datasetSplit')}><option value="calibration">Calibration</option><option value="validation">Validation aveugle</option></select></label>
    </div>
    <label>Question<textarea value={form.question} onChange={change('question')} required /></label>
    <label>Statut attendu<select value={form.expectedStatus} onChange={change('expectedStatus')}>
      <option value="reponse_trouvee">Réponse trouvée</option>
      <option value="reponse_non_trouvee">Information insuffisante</option>
      <option value="hors_perimetre">Hors périmètre</option>
      <option value="question_ambigue">Question ambiguë</option>
      <option value="prompt_injection">Injection refusée</option>
    </select></label>
    <label>Réponse attendue<textarea value={form.expectedAnswer} onChange={change('expectedAnswer')} /></label>
    <label>Pages attendues, séparées par des virgules<input value={form.pagesText} onChange={change('pagesText')} /></label>
    <label>Sections attendues, séparées par des virgules<input value={form.sectionsText} onChange={change('sectionsText')} /></label>
    <label>Documents attendus, séparés par des virgules<input value={form.documentsText} onChange={change('documentsText')} /></label>
    <label>Termes requis, séparés par des virgules<input value={form.termsText} onChange={change('termsText')} /></label>
    <label className="check-label"><input type="checkbox" checked={form.active} onChange={(event) => setForm({ ...form, active: event.target.checked })} /> Inclure dans les campagnes</label>
    <button className="button" type="submit">Enregistrer</button>
  </form></div>
}

export default function EvaluationsPage() {
  const [questions, setQuestions] = useState([])
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [view, setView] = useState('results')
  const [failuresOnly, setFailuresOnly] = useState(false)
  const [running, setRunning] = useState(false)
  const [runSplit, setRunSplit] = useState('calibration')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [detail, setDetail] = useState(null)
  const [form, setForm] = useState(null)
  const importRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const [questionItems, runItems] = await Promise.all([
        getEvaluationQuestions(),
        getEvaluationRuns(),
      ])
      setQuestions(questionItems)
      setRuns(runItems)
      setSelectedRun(runItems.length ? await getEvaluationRun(runItems[0].id) : null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const launch = async () => {
    setRunning(true)
    setError('')
    setNotice('Campagne en cours : les questions actives sont exécutées séquentiellement.')
    try {
      const run = await runEvaluation(runSplit)
      setSelectedRun(run)
      setRuns(await getEvaluationRuns())
      setNotice('Campagne terminée : ' + run.passed + '/' + run.total + ' cas réussis.')
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  const selectRun = async (event) => {
    try {
      setSelectedRun(await getEvaluationRun(event.target.value))
      setDetail(null)
    } catch (err) {
      setError(err.message)
    }
  }

  const saveQuestion = async (payload) => {
    try {
      if (form.id) await updateEvaluationQuestion(form.id, payload)
      else await createEvaluationQuestion(payload)
      setForm(null)
      setQuestions(await getEvaluationQuestions())
      setNotice('Référentiel mis à jour.')
    } catch (err) {
      setError(err.message)
    }
  }

  const removeQuestion = async (question) => {
    if (!window.confirm('Supprimer ' + question.code + ' ?')) return
    try {
      await deleteEvaluationQuestion(question.id)
      setQuestions(await getEvaluationQuestions())
    } catch (err) {
      setError(err.message)
    }
  }

  const importJson = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const payload = JSON.parse(await file.text())
      const items = (Array.isArray(payload) ? payload : payload.questions)
        .map(normalizeImportedQuestion)
      const result = await importEvaluationQuestions(items)
      setQuestions(await getEvaluationQuestions())
      setNotice('Import terminé : ' + result.created + ' créées, ' + result.updated + ' mises à jour.')
    } catch (err) {
      setError('Import impossible : ' + err.message)
    } finally {
      event.target.value = ''
    }
  }

  const download = async () => {
    if (!selectedRun) return
    try {
      const blob = await exportEvaluationRun(selectedRun.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'evaluation-' + selectedRun.id + '.csv'
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  const results = selectedRun?.results || []
  const rows = failuresOnly ? results.filter((item) => !item.success) : results
  const categories = [...new Set(results.map((item) => item.category))]

  return <div className="admin-page">
    <PageHeader
      title="Évaluations"
      description="Gérez le référentiel, lancez le pipeline RAG réel et comparez les campagnes."
      actions={<div className="page-actions">
        {view === 'results' && <button className="button secondary" onClick={download} disabled={!selectedRun}><Download size={17} /> Exporter CSV</button>}
        {view === 'results' && <select aria-label="Jeu de campagne" value={runSplit} onChange={(event) => setRunSplit(event.target.value)}><option value="calibration">Calibration</option><option value="validation">Validation aveugle</option><option value="all">Tous les cas</option></select>}
        {view === 'results' && <button className="button" onClick={launch} disabled={running || !questions.some((item) => item.active && (runSplit === 'all' || item.datasetSplit === runSplit))}><Play size={17} />{running ? 'Campagne en cours…' : 'Lancer la campagne'}</button>}
        {view === 'questions' && <button className="button secondary" onClick={() => importRef.current?.click()}><FileUp size={17} /> Importer JSON</button>}
        {view === 'questions' && <button className="button" onClick={() => setForm({ ...blankQuestion })}><Plus size={17} /> Ajouter</button>}
      </div>}
    />
    <div className="evaluation-tabs">
      <button className={view === 'results' ? 'active' : ''} onClick={() => setView('results')}>Campagnes</button>
      <button className={view === 'questions' ? 'active' : ''} onClick={() => setView('questions')}>Questions de référence ({questions.length})</button>
    </div>
    <input ref={importRef} type="file" accept="application/json,.json" hidden onChange={importJson} />
    {error && <p className="auth-error">{error}</p>}
    {notice && <div className="inline-notice">{notice}</div>}

    {view === 'results' ? <>
      <div className="evaluation-summary">
        <div><span>Score global</span><strong>{selectedRun?.scorePercent ?? 0}<small>/100</small></strong></div>
        <div><span>Réussite</span><strong>{selectedRun ? selectedRun.passed + '/' + selectedRun.total : '—'}</strong></div>
        <div><span>Durée</span><strong>{formatDuration(selectedRun?.durationMs)}</strong></div>
        <div><span>Jeu</span><strong>{selectedRun?.datasetSplit || '—'}</strong></div>
        <div><span>Recall@1 / @3 / @5</span><strong>{selectedRun ? [selectedRun.recallAt1, selectedRun.recallAt3, selectedRun.recallAt5].map((value) => value == null ? '—' : Math.round(value * 100) + '%').join(' / ') : '—'}</strong></div>
        <div><span>MRR</span><strong>{selectedRun?.mrr == null ? '—' : selectedRun.mrr.toFixed(3)}</strong></div>
        <div><span>Latence P50 / P95</span><strong>{selectedRun ? formatDuration(selectedRun.latencyP50Ms) + ' / ' + formatDuration(selectedRun.latencyP95Ms) : '—'}</strong></div>
        <div><span>Retrieval P50 / P95</span><strong>{selectedRun ? formatDuration(selectedRun.retrievalLatencyP50Ms) + ' / ' + formatDuration(selectedRun.retrievalLatencyP95Ms) : '—'}</strong></div>
        <div><span>Documents retrouvables</span><strong>{selectedRun ? selectedRun.coveredDocumentsTotal + '/' + selectedRun.activeDocumentsTotal + ' (' + selectedRun.documentCoveragePercent + '%)' : '—'}</strong></div>
        <label>Historique<select value={selectedRun?.id || ''} onChange={selectRun} disabled={!runs.length}>
          {!runs.length && <option value="">Aucune campagne</option>}
          {runs.map((run) => <option key={run.id} value={run.id}>{formatDate(run.startedAt)} · {run.scorePercent}%</option>)}
        </select></label>
      </div>
      <div className="toolbar">
        <label className="check-label"><input type="checkbox" checked={failuresOnly} onChange={(event) => setFailuresOnly(event.target.checked)} /> Afficher uniquement les échecs</label>
      </div>
      <div className="category-chips">{categories.map((category) => <span key={category}>{category}</span>)}</div>
      <DataTable
        rows={rows}
        empty="Aucun résultat. Lancez une campagne après avoir ajouté des questions actives."
        columns={[
          { key: 'questionCode', label: 'Code' },
          { key: 'category', label: 'Catégorie' },
          { key: 'datasetSplit', label: 'Jeu' },
          { key: 'question', label: 'Question', render: (item) => <span className="truncate">{item.question}</span> },
          { key: 'expectedStatus', label: 'Attendu' },
          { key: 'actualStatus', label: 'Obtenu' },
          { key: 'pages', label: 'Pages', render: (item) => item.actualPages.length ? item.actualPages.join(', ') : '—' },
          { key: 'latencyMs', label: 'Latence', render: (item) => item.latencyMs + ' ms' },
          { key: 'retrieval', label: 'Retrieval', render: (item) => item.retrievalRank == null ? 'N/A' : 'rang ' + item.retrievalRank },
          { key: 'success', label: 'Résultat', render: (item) => <span className={item.success ? 'result-ok' : 'result-fail'}>{item.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}{item.success ? 'Réussi' : 'Échoué'}</span> },
          { key: 'action', label: 'Détail', render: (item) => <button className="icon-button" onClick={() => setDetail(item)} aria-label={'Voir ' + item.questionCode}><Eye size={17} /></button> },
        ]}
      />
    </> : <DataTable
      rows={questions}
      empty="Aucune question de référence."
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'category', label: 'Catégorie' },
        { key: 'datasetSplit', label: 'Jeu' },
        { key: 'question', label: 'Question', render: (item) => <span className="truncate">{item.question}</span> },
        { key: 'expectedStatus', label: 'Statut attendu' },
        { key: 'expectedPages', label: 'Pages', render: (item) => item.expectedPages.length ? item.expectedPages.join(', ') : '—' },
        { key: 'active', label: 'Active', render: (item) => item.active ? 'Oui' : 'Non' },
        { key: 'actions', label: 'Actions', render: (item) => <div className="table-actions"><button onClick={() => setForm(item)}><Pencil size={14} /> Modifier</button><button onClick={() => removeQuestion(item)}><Trash2 size={14} /> Supprimer</button></div> },
      ]}
    />}

    {detail && <div className="detail-drawer" role="dialog" aria-modal="true">
      <div className="drawer-head"><div><span className="eyebrow">{detail.questionCode} · {detail.category}</span><h2>{detail.success ? 'Cas réussi' : 'Cas échoué'}</h2></div><button className="icon-button" onClick={() => setDetail(null)} aria-label="Fermer"><X /></button></div>
      <section><h3>Question</h3><p>{detail.question}</p></section>
      <section><h3>Réponse attendue</h3><p>{detail.expectedAnswer || '—'}</p></section>
      <section><h3>Réponse obtenue</h3><p>{detail.actualAnswer || '—'}</p></section>
      <section><h3>Contrôles</h3><ul className="evaluation-checks">{Object.entries(detail.checks).map(([name, passed]) => <li key={name} className={passed ? 'result-ok' : 'result-fail'}>{passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}{name}</li>)}</ul></section>
      <section><h3>Retrieval</h3><p>{detail.retrievalRank == null ? 'Non applicable' : 'Premier chunk pertinent au rang ' + detail.retrievalRank + ' · Recall@1 ' + (detail.recallAt1 ? 'oui' : 'non') + ' · Recall@3 ' + (detail.recallAt3 ? 'oui' : 'non') + ' · Recall@5 ' + (detail.recallAt5 ? 'oui' : 'non') + ' · latence ' + detail.retrievalLatencyMs + ' ms'}</p></section>
      {!!detail.failureReasons.length && <section><h3>Causes d’échec</h3><ul>{detail.failureReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></section>}
      <section><h3>Sources récupérées</h3>{detail.sources.length ? detail.sources.map((source, index) => <article className="evaluation-source" key={source.chunkId || index}><strong>{source.documentTitle || source.fileName || 'Document'}</strong><small>{source.pages?.length ? 'Pages ' + source.pages.join(', ') : 'Page absente'}{source.section ? ' · ' + source.section : ''}</small><p>{source.excerpt}</p></article>) : <p>Aucune source.</p>}</section>
    </div>}
    {form && <QuestionForm value={form} onClose={() => setForm(null)} onSave={saveQuestion} />}
  </div>
}
