import { useState, useRef, useEffect } from 'react'

export interface ModelOption {
  name: string
  provider: 'ollama' | 'anthropic'
  label: string
  desc?: string
}

interface ModelSwitcherProps {
  options: ModelOption[]
  selected: ModelOption
  onChange: (option: ModelOption) => void
}

export default function ModelSwitcher({ options, selected, onChange }: ModelSwitcherProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const localModels = options.filter(o => o.provider === 'ollama')
  const remoteModels = options.filter(o => o.provider === 'anthropic')

  const isLocal = selected.provider === 'ollama'

  const handleSelect = (option: ModelOption) => {
    onChange(option)
    setOpen(false)
  }

  return (
    <div className={`model-switcher ${open ? 'model-switcher--open' : ''}`} ref={ref}>
      <button
        className="model-switcher__trigger"
        onClick={() => setOpen(!open)}
        type="button"
      >
        <span className={`model-switcher__dot ${isLocal ? 'model-switcher__dot--local' : 'model-switcher__dot--remote'}`} />
        <span className="model-switcher__name">{selected.name}</span>
        <span className="model-switcher__badge">{selected.label}</span>
        <span className="model-switcher__chevron">
          <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
            <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {open && (
        <div className="model-switcher__menu">
          {localModels.length > 0 && (
            <div className="model-switcher__group-label">本地模型</div>
          )}
          {localModels.map((opt) => (
            <div
              key={opt.name}
              className={`model-switcher__option ${selected.name === opt.name ? 'model-switcher__option--selected' : ''}`}
              onClick={() => handleSelect(opt)}
            >
              <span className="model-switcher__dot model-switcher__dot--local" />
              <span>{opt.name}</span>
              {opt.desc && <span className="model-switcher__option-desc">{opt.desc}</span>}
              {selected.name === opt.name && (
                <span className="model-switcher__check">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </span>
              )}
            </div>
          ))}

          {remoteModels.length > 0 && (
            <div className="model-switcher__group-label">远程 API</div>
          )}
          {remoteModels.map((opt) => (
            <div
              key={opt.name}
              className={`model-switcher__option ${selected.name === opt.name ? 'model-switcher__option--selected' : ''}`}
              onClick={() => handleSelect(opt)}
            >
              <span className="model-switcher__dot model-switcher__dot--remote" />
              <span>{opt.name}</span>
              {opt.desc && <span className="model-switcher__option-desc">{opt.desc}</span>}
              {selected.name === opt.name && (
                <span className="model-switcher__check">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
