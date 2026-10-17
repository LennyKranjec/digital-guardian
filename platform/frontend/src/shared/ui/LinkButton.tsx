import { Link, type LinkProps } from 'react-router-dom';

const BASE =
  'inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-5 py-2 text-base font-semibold transition-colors';
const VARIANT = {
  primary: 'bg-accent text-on-accent hover:bg-accent-hover',
  secondary: 'border border-border-strong bg-surface text-ink hover:bg-sunken',
} as const;

/** Link im Aussehen der `Button`-Komponente (Navigation bleibt ein Link, kein Button). */
export function LinkButton({
  variant = 'secondary',
  className = '',
  ...rest
}: LinkProps & { variant?: keyof typeof VARIANT }) {
  return <Link className={`${BASE} ${VARIANT[variant]} ${className}`} {...rest} />;
}
