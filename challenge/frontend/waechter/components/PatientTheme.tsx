import type { CSSProperties, ReactNode } from 'react';

/**
 * Warmes, flaches Farbschema nur für die Patientenseiten. Es überschreibt die Plattform-Tokens
 * (`--rk-*`, auf die die Tailwind-Utilities zeigen) lokal im Wrapper; Klinikseiten bleiben unberührt.
 *
 * Kontrast (WCAG AA): Text #2B2220 auf Cream 14,4:1, auf Sand 12,4:1, auf Blush 9,0:1;
 * Titel/Nebentext #7A5C44 auf Cream 5,7:1, auf Sand 4,9:1; Weiß auf Teal 6,4:1, auf Braun 6,1:1;
 * Teal auf Sand 5,1:1; Rahmen #8B6B52 auf Sand 3,9:1 (Nicht-Text ≥ 3:1).
 */
export const PATIENT_COLORS = {
  cream: '#FAF6F1',
  sand: '#F5E3CD',
  brown: '#7A5C44',
  secondary: '#8B6B52',
  blush: '#F0B8AE',
  teal: '#0F6B63',
  tealHover: '#0B544E',
  text: '#2B2220',
} as const;

const C = PATIENT_COLORS;

const THEME = {
  '--rk-bg': C.cream,
  '--rk-surface': C.sand,
  '--rk-surface-sunken': C.cream,
  '--rk-border': C.sand,
  '--rk-border-strong': C.secondary,
  '--rk-text': C.text,
  '--rk-text-muted': C.brown,
  '--rk-accent': C.teal,
  '--rk-accent-hover': C.tealHover,
  '--rk-on-accent': '#FFFFFF',
  '--rk-accent-subtle': C.blush,
  '--rk-accent-subtle-text': C.text,
  '--rk-radius': '24px',
  '--rk-radius-sm': '24px',
  '--rk-shadow': 'none',
  '--wp-title': C.brown,
  '--wp-track': C.sand,
  colorScheme: 'light',
  backgroundColor: C.cream,
  color: C.text,
  fontFamily: '"Nunito", "Poppins", ui-rounded, system-ui, sans-serif',
} as CSSProperties;

/** Wrapper für Patientenseiten (Check-in, adaptive Sitzung). */
export function PatientTheme({ children }: { children: ReactNode }) {
  return (
    <div
      data-testid="patient-theme"
      className="patient-theme w-full min-w-0 rounded-[32px] px-4 py-6 sm:px-8"
      style={THEME}
    >
      {children}
    </div>
  );
}
