import { apiDownload, apiRequest } from './api'

export const getEvaluationQuestions = () => apiRequest('/admin/evaluations/questions')
export const createEvaluationQuestion = (data) => apiRequest('/admin/evaluations/questions', {
  method: 'POST',
  body: JSON.stringify(data),
})
export const updateEvaluationQuestion = (id, data) => apiRequest('/admin/evaluations/questions/' + id, {
  method: 'PATCH',
  body: JSON.stringify(data),
})
export const deleteEvaluationQuestion = (id) => apiRequest('/admin/evaluations/questions/' + id, {
  method: 'DELETE',
})
export const importEvaluationQuestions = (questions) => apiRequest('/admin/evaluations/questions/import', {
  method: 'POST',
  body: JSON.stringify({ questions }),
})

export const getEvaluationRuns = () => apiRequest('/admin/evaluations/runs')
export const getEvaluationRun = (id) => apiRequest('/admin/evaluations/runs/' + id)
export const runEvaluation = (datasetSplit = 'calibration') => apiRequest('/admin/evaluations/runs', {
  method: 'POST',
  body: JSON.stringify({ datasetSplit }),
})
export const deleteEvaluationRun = (id) => apiRequest('/admin/evaluations/runs/' + id, {
  method: 'DELETE',
})
export const exportEvaluationRun = (id) => apiDownload('/admin/evaluations/runs/' + id + '/export.csv')
