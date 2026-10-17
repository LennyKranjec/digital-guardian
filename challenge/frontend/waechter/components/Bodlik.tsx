import type { CSSProperties } from 'react';

/**
 * Igel „Bodlík“ (Begleiter im Fortschrittsbalken der Patientenseiten). Pfade unverändert aus der
 * Vorlage bodlik.svg; die CSS-Variablen der Vorlage sind als feste (helle) Farben eingesetzt.
 * Rein dekorativ: immer aria-hidden, nie Träger einer Aussage.
 */
export function Bodlik({
  size = 40,
  className = '',
  style,
}: {
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 120 120"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={className}
      style={style}
      data-testid="bodlik"
    >
      <ellipse cx="58" cy="108" rx="40" ry="4.5" fill="#221e191f" />
      <g>
        <path
          d="M14.0 75.2 L5.2 74.3 L15.0 66.4 L6.7 63.6 L18.4 58.1 L11.2 53.5 L24.1 50.7 L18.4 44.8 L31.7 44.9 L27.9 37.9 L40.8 41.0 L39.1 33.3 L50.7 39.1 L51.3 31.4 L60.8 39.5 L63.6 32.1 L70.5 42.1 L75.3 35.6 L79.1 46.8 L85.7 41.5 L86.1 53.2 L94.0 49.5 L91.1 60.9 Q 98 92 88 100 L 30 100 Q 14 96 15 80 Z"
          fill="#8a6a50"
          stroke="#8a6a50"
          strokeWidth="2.4"
          strokeLinejoin="round"
        />
        <path
          d="M21.5 69.1 L15.3 67.0 L24.2 61.9 L18.9 58.4 L29.1 55.6 L25.1 51.0 L35.9 50.6 L33.4 45.3 L43.9 47.3 L43.3 41.7 L52.7 46.0 L53.9 40.4 L61.6 46.8 L64.5 41.6 L69.9 49.5 L74.4 45.2 L77.1 54.0 L82.7 50.9 L82.6 60.0 Q 86 88 80 92 L 34 92 Q 24 88 24 80 Z"
          fill="#6e523d"
          stroke="#6e523d"
          strokeWidth="2"
          strokeLinejoin="round"
          opacity={0.55}
        />
        <g>
          <path d="M50 36 c-3 -9 2 -17 11 -20 c1 9 -3 17 -11 20 z" fill="#0e6f68" />
          <path
            d="M50 36 c3 -6 6 -11 10 -16"
            fill="none"
            stroke="#f4e4cf"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </g>
        <path d="M34 98 C 40 86 66 84 74 96 C 70 104 40 106 34 98 Z" fill="#efdcc4" />
        <ellipse cx="44" cy="103" rx="7" ry="4.5" fill="#6e523d" />
        <ellipse cx="66" cy="104" rx="7" ry="4.5" fill="#6e523d" />
        <path
          d="M70 52 C 84 44 100 56 110 72 C 116 79 113 86 105 87 C 99 98 84 104 72 100 C 62 96 60 84 62 72 C 63 62 65 56 70 52 Z"
          fill="#f4e4cf"
        />
        <circle cx="73" cy="53" r="5.5" fill="#f4e4cf" />
        <circle cx="73.5" cy="53.5" r="2.8" fill="#e9b6a4" />
        <circle cx="95" cy="78" r="4.2" fill="#eeb2a1" opacity={0.85} />
        <g>
          <ellipse cx="87" cy="66" rx="4.2" ry="4.8" fill="#2a221b" />
          <circle cx="88.6" cy="64.2" r="1.6" fill="#ffffff" />
          <circle cx="85.6" cy="68.2" r="0.8" fill="#ffffff" />
        </g>
        <ellipse cx="109.5" cy="76" rx="4.4" ry="3.8" fill="#2a221b" />
        <circle cx="110.6" cy="74.8" r="1.1" fill="#ffffff" opacity={0.8} />
        <path
          d="M97 89 q3.5 3 7 -0.5"
          fill="none"
          stroke="#2a221b"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <ellipse cx="78" cy="98" rx="5.5" ry="4" fill="#6e523d" />
      </g>
    </svg>
  );
}
