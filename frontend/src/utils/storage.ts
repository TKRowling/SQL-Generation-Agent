import type { StoredConversation, StoredMessage } from '../types/api'
import { getSessionId } from './session'

const CONVERSATIONS_KEY = 'askme.conversations.v2'
const ACTIVE_KEY = 'askme.active-conversation'
const LEGACY_CHAT_KEY = 'askme.messages'

export interface ConversationState {
  conversations: StoredConversation[]
  activeId: string
}

export function loadConversationState(welcome: StoredMessage): ConversationState {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY)
    const parsed = raw ? JSON.parse(raw) as StoredConversation[] : []
    if (Array.isArray(parsed) && parsed.length) {
      const active = localStorage.getItem(ACTIVE_KEY)
      return { conversations: parsed, activeId: parsed.some((item) => item.id === active) ? active! : parsed[0]!.id }
    }

    const legacyRaw = localStorage.getItem(LEGACY_CHAT_KEY)
    const legacy = legacyRaw ? JSON.parse(legacyRaw) as StoredMessage[] : []
    const now = new Date().toISOString()
    const conversation: StoredConversation = {
      id: getSessionId(),
      title: firstQuestion(legacy) ?? 'New conversation',
      messages: Array.isArray(legacy) && legacy.length ? legacy : [welcome],
      createdAt: now,
      updatedAt: now,
    }
    return { conversations: [conversation], activeId: conversation.id }
  } catch {
    const now = new Date().toISOString()
    const conversation = { id: crypto.randomUUID(), title: 'New conversation', messages: [welcome], createdAt: now, updatedAt: now }
    return { conversations: [conversation], activeId: conversation.id }
  }
}

export function saveConversationState(state: ConversationState): void {
  localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(state.conversations.slice(0, 30)))
  localStorage.setItem(ACTIVE_KEY, state.activeId)
}

export function conversationTitle(message: string): string {
  const compact = message.replace(/\s+/g, ' ').trim()
  return compact.length > 42 ? `${compact.slice(0, 42)}…` : compact
}

function firstQuestion(messages: StoredMessage[]): string | null {
  const question = messages.find((message) => message.role === 'user')
  return question ? conversationTitle(question.text) : null
}
