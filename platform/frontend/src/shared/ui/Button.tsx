import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary';

const BASE =
  'inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-5 py-2 text-base font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60';
const VARIANT: Record<Variant, string> = {
  primary: 'bg-accent text-on-accent hover:bg-accent-hover',
  secondary: 'border border-border-strong bg-surface text-ink hover:bg-sunken',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({
  variant = 'primary',
  className = '',
  type = 'button',
  ...rest
}: ButtonProps) {
  return <button type={type} className={`${BASE} ${VARIANT[variant]} ${className}`} {...rest} />;
}
