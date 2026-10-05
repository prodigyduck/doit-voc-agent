// doit-voc-agent 백엔드 API 클라이언트
// 기본은 같은 오리진 상대경로(vite가 /api를 백엔드로 프록시). VITE_API_BASE로 직접 지정도 가능
const BASE_URL = import.meta.env.VITE_API_BASE ?? ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `요청 실패 (${res.status})`)
  }
  return res.json()
}

export function chat(vocText, sessionId) {
  return request('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ voc_text: vocText, session_id: sessionId }),
  })
}

export function getVocs(params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null)
  ).toString()
  return request(`/api/vocs${qs ? '?' + qs : ''}`)
}

export function patchVocStatus(id, status) {
  return request(`/api/vocs/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export function getStats() {
  return request('/api/stats')
}

export function getSessionId() {
  let id = sessionStorage.getItem('doit_session_id')
  if (!id) {
    id = 's-' + Math.random().toString(36).slice(2, 10)
    sessionStorage.setItem('doit_session_id', id)
  }
  return id
}
