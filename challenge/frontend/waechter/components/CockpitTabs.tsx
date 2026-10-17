import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

export interface CockpitTab {
  id: string;
  label: string;
  content: ReactNode;
}

const TAB =
  'inline-flex min-h-11 items-center justify-center rounded-full border px-4 py-2 text-base font-semibold';

/**
 * Segment-Wechsel für die sekundären Bereiche des Cockpits (T-32): Es ist immer genau ein Bereich sichtbar.
 * Alle Bereiche bleiben eingehängt (nur `hidden`), damit Abfragen, Zustände und Testkennungen unverändert
 * bestehen; nichts wird entfernt, nur weniger gleichzeitig gezeigt. Pfeiltasten wechseln den Bereich.
 */
export function CockpitTabs({
  label,
  tabs,
  initial,
}: {
  label: string;
  tabs: readonly CockpitTab[];
  initial?: string;
}) {
  const [active, setActive] = useState(initial ?? tabs[0]?.id ?? '');
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);

  function onKeyDown(event: KeyboardEvent, index: number) {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = (index + step + tabs.length) % tabs.length;
    const tab = tabs[next];
    if (!tab) return;
    setActive(tab.id);
    buttons.current[next]?.focus();
  }

  return (
    <div className="space-y-3" data-testid="cockpit-tabs">
      <div role="tablist" aria-label={label} className="flex flex-wrap gap-2">
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(element) => {
                buttons.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`cockpit-tab-${tab.id}`}
              data-testid={`cockpit-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`cockpit-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={`${TAB} ${
                selected
                  ? 'border-accent bg-accent text-on-accent'
                  : 'border-border-strong bg-surface text-ink hover:bg-sunken'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`cockpit-panel-${tab.id}`}
          data-testid={`cockpit-panel-${tab.id}`}
          aria-labelledby={`cockpit-tab-${tab.id}`}
          hidden={tab.id !== active}
          className="min-w-0 space-y-3"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
