const SESSION_KEY = 'askme.session-id'

export function getSessionId(): string {
  const existing = localStorage.getItem(SESSION_KEY)
  if (existing) return existing

  const generated = crypto.randomUUID()
  localStorage.setItem(SESSION_KEY, generated)
  return generated
}
