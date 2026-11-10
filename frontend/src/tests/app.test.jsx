// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import App from '../App'
import { createConversation, deleteConversation, getConversations, sendMessage, submitFeedback } from '../services/chatService'
import {
  archiveDocument,
  deleteDocument,
  downloadDocument,
  getDocuments,
  getDocumentVersions,
  importDocument,
  restoreDocument,
  restoreDocumentVersion,
  toggleDocument,
  updateDocumentKnowledge,
  uploadDocumentVersion,
  viewDocument,
} from '../services/documentService'
import { exportUnansweredQuestions, getUnansweredQuestions, updateUnansweredQuestion } from '../services/adminService'
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
} from '../services/evaluationService'
import { MessageSources } from '../components/chat/ChatMessage'
import { createContact, getContacts, updateContact } from '../services/contactService'

const adminConversations = [{
  id: 'conversation-1',
  date: new Date().toISOString(),
  user: 'Utilisateur test',
  question: 'Quels documents dois-je préparer ?',
  status: 'Réponse trouvée',
  answer: 'Préparez les justificatifs administratifs demandés.',
  feedback: 'Utile',
  duration: '1,4 s',
  internalReferences: [{
    documentTitle: 'Guide d’onboarding de démonstration',
    fileName: 'guide_onboarding_demo.docx',
    pages: [4, 5],
    section: 'Préparation administrative',
    excerpt: 'La liste des pièces est communiquée avant la date d’arrivée.',
  }],
}]

const renderAt = (path) => {
  window.history.replaceState({}, '', path)
  return render(<BrowserRouter><App /></BrowserRouter>)
}

describe('sources documentaires utilisateur', () => {
  afterEach(cleanup)

  it('affiche le document, sa page, sa section et son extrait', () => {
    render(<MessageSources sources={[{
      documentTitle: 'Processus onboarding',
      fileName: 'processus.docx',
      pages: [4],
      section: 'Règles de gestion',
      excerpt: 'Le processus comprend trois phases.',
      chunkId: 'chunk-1',
    }]} />)

    expect(screen.getByText('1 source')).toBeTruthy()
    expect(screen.getByText('Processus onboarding')).toBeTruthy()
    expect(screen.getByText('p. 4 · Règles de gestion')).toBeTruthy()
    expect(screen.getByText('Le processus comprend trois phases.')).toBeTruthy()
  })
})

describe('authentification et routes protégées', () => {
  beforeEach(() => localStorage.clear())
  afterEach(cleanup)

  it('redirige une session absente vers la connexion', async () => {
    renderAt('/admin/dashboard')
    expect(await screen.findByText('Connectez-vous')).toBeTruthy()
    expect(window.location.pathname).toBe('/login')
  })

  it('refuse les routes admin à un utilisateur USER', async () => {
    localStorage.setItem('onboarding_session', JSON.stringify({ id: 'u', name: 'Test', email: 'test@exemple.test', role: 'USER' }))
    localStorage.setItem('onboarding_access_token', 'test-token')
    renderAt('/admin/documents')
    expect(await screen.findByText('Vous n’avez pas accès à cet espace.')).toBeTruthy()
    expect(window.location.pathname).toBe('/access-denied')
  })

  it('autorise un administrateur et rend ses références internes', async () => {
    localStorage.setItem('onboarding_session', JSON.stringify({ id: 'a', name: 'Admin', email: 'admin@exemple.test', role: 'ADMIN' }))
    localStorage.setItem('onboarding_access_token', 'test-token')
    globalThis.fetch = vi.fn(async (url) => ({ ok: true, status: 200, json: async () => new URL(url, 'http://localhost').pathname.endsWith('/admin/conversations') ? adminConversations.map((item) => ({ ...item, status: 'reponse_trouvee' })) : [] }))
    renderAt('/admin/conversations')
    fireEvent.click(await screen.findAllByText('Voir le détail').then((items) => items[0]))
    expect(await screen.findByText('Références internes · administrateur uniquement')).toBeTruthy()
    expect(screen.getByText(/guide_onboarding_demo\.docx/)).toBeTruthy()
  })
})

describe('persistance locale du chat', () => {
  beforeEach(() => {
    localStorage.clear()
    let conversations = []
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      const path = new URL(url, 'http://localhost').pathname
      const method = options.method || 'GET'
      let payload = null
      if (method === 'POST' && path.endsWith('/conversations')) {
        payload = { id: '00000000-0000-4000-8000-000000000001', title: 'Nouvelle conversation', updatedAt: new Date().toISOString(), messages: [] }
        conversations = [payload]
      } else if (method === 'POST' && path.endsWith('/chat')) {
        const { question, conversationId } = JSON.parse(options.body)
        payload = {
          userMessage: { id: '00000000-0000-4000-8000-000000000002', role: 'user', content: question, createdAt: new Date().toISOString() },
          response: { id: '00000000-0000-4000-8000-000000000003', role: 'assistant', content: 'Réponse issue du backend.', status: 'reponse_trouvee', confidenceScore: 0.9, sources: [], createdAt: new Date().toISOString() },
        }
        conversations = conversations.map((item) => item.id === conversationId ? { ...item, messages: [payload.userMessage, payload.response] } : item)
      } else if (method === 'POST' && path.includes('/feedback')) {
        payload = JSON.parse(options.body)
      } else if (method === 'DELETE') {
        conversations = conversations.filter((item) => !path.endsWith(item.id))
      } else if (method === 'GET' && path.endsWith('/conversations')) {
        payload = conversations
      }
      return {
        ok: true,
        status: method === 'DELETE' ? 204 : 200,
        json: async () => payload,
      }
    })
  })

  it('crée, alimente, évalue puis supprime une conversation via l’API', async () => {
    const conversation = await createConversation()
    const { response } = await sendMessage('Quels documents dois-je préparer ?', conversation.id)
    expect(response.internalReferences).toBeUndefined()
    expect((await getConversations()).find((item) => item.id === conversation.id).messages).toHaveLength(2)
    await submitFeedback(response.id, { type: 'non_utile', reason: 'réponse incomplète' })
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining(`/messages/${response.id}/feedback`), expect.objectContaining({ method: 'POST' }))
    await deleteConversation(conversation.id)
    await waitFor(async () => expect((await getConversations()).some((item) => item.id === conversation.id)).toBe(false))
  })
})

describe('gestion documentaire connectée au backend', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('onboarding_access_token', 'test-token')
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
      blob: async () => new Blob(['document'], { type: 'application/pdf' }),
    }))
  })

  it('utilise les routes admin réelles et un upload multipart', async () => {
    await getDocuments()
    await toggleDocument('doc-1')
    await updateDocumentKnowledge('doc-1')
    await archiveDocument('doc-1')
    await importDocument(new File(['contenu'], 'guide.pdf', { type: 'application/pdf' }))
    await restoreDocument('doc-1')
    await getDocumentVersions('doc-1')
    await uploadDocumentVersion('doc-1', new File(['version'], 'guide-v2.pdf', { type: 'application/pdf' }))
    await restoreDocumentVersion('doc-1', 'version-1')
    await viewDocument('doc-1')
    await downloadDocument('doc-1')
    await deleteDocument('doc-1')

    expect(globalThis.fetch).toHaveBeenNthCalledWith(1, expect.stringMatching(/\/admin\/documents$/), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/admin/documents/doc-1/toggle'), expect.objectContaining({ method: 'PATCH' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(3, expect.stringContaining('/admin/documents/doc-1/reindex'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(4, expect.stringContaining('/admin/documents/doc-1/archive'), expect.objectContaining({ method: 'POST' }))

    const uploadOptions = globalThis.fetch.mock.calls[4][1]
    expect(uploadOptions.method).toBe('POST')
    expect(uploadOptions.body).toBeInstanceOf(FormData)
    expect(uploadOptions.headers['Content-Type']).toBeUndefined()
    expect(globalThis.fetch).toHaveBeenNthCalledWith(6, expect.stringContaining('/admin/documents/doc-1/restore'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(7, expect.stringContaining('/admin/documents/doc-1/versions'), expect.any(Object))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(8, expect.stringContaining('/admin/documents/doc-1/versions'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(9, expect.stringContaining('/admin/documents/doc-1/versions/version-1/restore'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(12, expect.stringContaining('/admin/documents/doc-1?confirm=true'), expect.objectContaining({ method: 'DELETE' }))
  })
})

describe('contacts connectés au backend', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('onboarding_access_token', 'test-token')
    globalThis.fetch = vi.fn(async (_url, options = {}) => ({
      ok: true,
      status: options.method === 'POST' ? 201 : 200,
      json: async () => options.method
        ? { id: 'contact-1', ...JSON.parse(options.body) }
        : [],
    }))
  })

  it('charge, crée et modifie les contacts via les routes admin', async () => {
    await getContacts()
    await createContact({ name: 'RH', service: 'Ressources humaines' })
    await updateContact('contact-1', { active: false })

    expect(globalThis.fetch).toHaveBeenNthCalledWith(1, expect.stringContaining('/admin/contacts'), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/admin/contacts'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(3, expect.stringContaining('/admin/contacts/contact-1'), expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ active: false }) }))
  })
})

describe('questions sans réponse connectées au backend', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('onboarding_access_token', 'test-token')
    globalThis.fetch = vi.fn(async (url, options = {}) => ({
      ok: true,
      status: 200,
      json: async () => options.method === 'PATCH'
        ? { id: 'fallback-1', question: 'Question inconnue', occurrences: 2, first: '2026-08-01', last: '2026-08-02', status: 'Analysée', comment: 'Traité' }
        : [],
      blob: async () => new Blob(['id,question'], { type: 'text/csv' }),
    }))
  })

  it('charge, annote et exporte via les routes admin réelles', async () => {
    await getUnansweredQuestions({ query: 'visa', status: 'À analyser' })
    await updateUnansweredQuestion('fallback-1', { status: 'Analysée', comment: 'Traité' })
    const csv = await exportUnansweredQuestions({ query: 'visa' })

    expect(globalThis.fetch).toHaveBeenNthCalledWith(1, expect.stringContaining('/admin/fallbacks?query=visa&status=%C3%80+analyser'), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/admin/fallbacks/fallback-1'), expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ status: 'Analysée', comment: 'Traité' }) }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(3, expect.stringContaining('/admin/fallbacks/export.csv?query=visa'), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }))
    expect(csv.type).toBe('text/csv')
  })
})

describe('évaluations connectées au backend', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('onboarding_access_token', 'test-token')
    globalThis.fetch = vi.fn(async (url, options = {}) => ({
      ok: true,
      status: options.method === 'DELETE' ? 204 : 200,
      json: async () => [],
      blob: async () => new Blob(['question_code,success'], { type: 'text/csv' }),
    }))
  })

  it('utilise les routes CRUD, campagne, historique et export réelles', async () => {
    const question = {
      code: 'Q001',
      category: 'factuelle',
      question: 'Question ?',
      expectedStatus: 'reponse_trouvee',
    }
    await getEvaluationQuestions()
    await createEvaluationQuestion(question)
    await updateEvaluationQuestion('question-1', { active: false })
    await importEvaluationQuestions([question])
    await getEvaluationRuns()
    await getEvaluationRun('run-1')
    await runEvaluation()
    await exportEvaluationRun('run-1')
    await deleteEvaluationQuestion('question-1')

    expect(globalThis.fetch).toHaveBeenNthCalledWith(1, expect.stringContaining('/admin/evaluations/questions'), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/admin/evaluations/questions'), expect.objectContaining({ method: 'POST', body: JSON.stringify(question) }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(3, expect.stringContaining('/admin/evaluations/questions/question-1'), expect.objectContaining({ method: 'PATCH' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(4, expect.stringContaining('/admin/evaluations/questions/import'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(5, expect.stringContaining('/admin/evaluations/runs'), expect.any(Object))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(6, expect.stringContaining('/admin/evaluations/runs/run-1'), expect.any(Object))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(7, expect.stringContaining('/admin/evaluations/runs'), expect.objectContaining({ method: 'POST' }))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(8, expect.stringContaining('/admin/evaluations/runs/run-1/export.csv'), expect.any(Object))
    expect(globalThis.fetch).toHaveBeenNthCalledWith(9, expect.stringContaining('/admin/evaluations/questions/question-1'), expect.objectContaining({ method: 'DELETE' }))
  })
})
