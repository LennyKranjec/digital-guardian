import type { AlertLevel } from '../api/client';

/**
 * Marker und Linienarten des Verlaufs. Die Bedeutung steckt nie nur in der Farbe: Meldungen haben
 * je Stufe eine eigene Form (rot = Raute, gelb = Dreieck, grau = Kreis mit Strich), Termine und
 * Aufnahmen eigene Linien- bzw. Symbolformen. Dieselben Formen zeichnet die Legende.
 */

export type MarkerKind =
  | { type: 'alert'; level: AlertLevel }
  | { type: 'visit'; planned: boolean }
  | { type: 'assessment' };

const ALERT_COLOR: Record<AlertLevel, string> = {
  red: 'text-status-critical-fg',
  yellow: 'text-status-caution-fg',
  grey: 'text-status-neutral-fg',
};

export function Marker({ kind, x, y }: { kind: MarkerKind; x: number; y: number }) {
  switch (kind.type) {
    case 'alert':
      return (
        <g
          className={`${ALERT_COLOR[kind.level]} stroke-current`}
          strokeWidth={2}
          data-marker={kind.level}
        >
          {kind.level === 'red' ? (
            <polygon
              points={`${x},${y - 9} ${x + 9},${y} ${x},${y + 9} ${x - 9},${y}`}
              className="fill-current"
            />
          ) : null}
          {kind.level === 'yellow' ? (
            <polygon
              points={`${x},${y - 9} ${x + 9},${y + 8} ${x - 9},${y + 8}`}
              className="fill-current"
            />
          ) : null}
          {kind.level === 'grey' ? (
            <>
              <circle cx={x} cy={y} r={7} className="fill-surface" />
              <line x1={x - 4} y1={y} x2={x + 4} y2={y} />
            </>
          ) : null}
        </g>
      );
    case 'visit':
      return (
        <rect
          x={x - 6}
          y={y - 6}
          width={12}
          height={12}
          strokeWidth={2}
          className={`stroke-current text-ink ${kind.planned ? 'fill-surface' : 'fill-current'}`}
          data-marker={kind.planned ? 'visit-planned' : 'visit-past'}
        />
      );
    case 'assessment':
      return (
        <g className="stroke-current text-accent" strokeWidth={3} data-marker="assessment">
          <line x1={x - 7} y1={y} x2={x + 7} y2={y} />
          <line x1={x} y1={y - 7} x2={x} y2={y + 7} />
        </g>
      );
  }
}

/** Senkrechte Linie für Termine (durchgezogen = vergangen, gestrichelt = geplant) und Aufnahmen (gepunktet, kräftig). */
export function VerticalLine({
  x,
  top,
  bottom,
  style,
}: {
  x: number;
  top: number;
  bottom: number;
  style: 'visit-past' | 'visit-planned' | 'assessment';
}) {
  const dash = style === 'visit-planned' ? '5 4' : style === 'assessment' ? '1 4' : undefined;
  return (
    <line
      x1={x}
      x2={x}
      y1={top}
      y2={bottom}
      strokeDasharray={dash}
      strokeLinecap={style === 'assessment' ? 'round' : undefined}
      strokeWidth={style === 'assessment' ? 3 : 1.5}
      className={
        style === 'assessment' ? 'stroke-current text-accent' : 'stroke-current text-muted'
      }
      data-line={style}
    />
  );
}

/** Schraffur für Tage ohne Eingabe. */
export function HatchPattern({ id }: { id: string }) {
  return (
    <pattern
      id={id}
      width={7}
      height={7}
      patternUnits="userSpaceOnUse"
      patternTransform="rotate(45)"
    >
      <line x1={0} y1={0} x2={0} y2={7} strokeWidth={2} className="stroke-current text-muted" />
    </pattern>
  );
}
