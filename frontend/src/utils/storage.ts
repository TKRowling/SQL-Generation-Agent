import type { StoredMessage } from '../types/api'

const CHAT_KEY = 'askme.messages'

export function loadMessages(): StoredMessage[] {
  try {
    const raw = localStorage.getItem(CHAT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as StoredMessage[]
    return Array.isArray(parsed) ? parsed.slice(-50) : []
  } catch {
    return []
  }
}

export function saveMessages(messages: StoredMessage[]): void {
  localStorage.setItem(CHAT_KEY, JSON.stringify(messages.slice(-50)))
}

export function clearMessages(): void {
  localStorage.removeItem(CHAT_KEY)
}
