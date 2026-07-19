import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

interface ComposerProps {
  disabled: boolean
  onSend: (message: string, forceData: boolean) => Promise<void>
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('')
  const [forceData, setForceData] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
  }, [value])

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    const message = value.trim()
    if (!message || disabled) return
    setValue('')
    await onSend(message, forceData)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about documents, projects, users, status, totals…"
        rows={1}
        maxLength={4000}
        disabled={disabled}
        aria-label="Message"
      />
      <div className="composer-footer">
        <label className="force-data-toggle">
          <input
            type="checkbox"
            checked={forceData}
            onChange={(event) => setForceData(event.target.checked)}
            disabled={disabled}
          />
          <span>Database only</span>
        </label>
        <span className="composer-hint">Enter to send · Shift+Enter for a new line</span>
        <button type="submit" disabled={disabled || !value.trim()}>
          {disabled ? 'Working…' : 'Send'}
        </button>
      </div>
    </form>
  )
}
