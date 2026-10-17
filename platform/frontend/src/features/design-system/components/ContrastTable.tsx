import { evaluateContrast, parseTokenCss } from '@rakathon/design-tokens';
import tokensCss from '@rakathon/design-tokens/tokens.css?raw';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useCurrentTheme } from '../../../shared/lib/useCurrentTheme';

/** Berechnet die Kontrastwerte zur Laufzeit aus tokens.css – dieselbe Quelle wie der automatische Test. */
export function ContrastTable() {
  const { t } = useTranslation();
  const theme = useCurrentTheme();
  const rows = useMemo(
    () => evaluateContrast(parseTokenCss(tokensCss)).filter((result) => result.theme === theme),
    [theme],
  );

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
        <caption className="sr-only">{t('ds.contrast')}</caption>
        <thead>
          <tr className="border-b border-border-strong">
            <th scope="col" className="p-3">
              {t('ds.contrastPair')}
            </th>
            <th scope="col" className="p-3">
              {t('ds.contrastRatio')}
            </th>
            <th scope="col" className="p-3">
              {t('ds.contrastMin')}
            </th>
            <th scope="col" className="p-3">
              {t('ds.contrastStatus')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border last:border-b-0">
              <th scope="row" className="p-3 font-normal">
                <span
                  aria-hidden="true"
                  className="mr-2 inline-block h-7 w-10 rounded-sm border border-border-strong align-middle"
                  style={{
                    backgroundColor: `var(--rk-${row.background})`,
                    color: `var(--rk-${row.foreground})`,
                  }}
                >
                  <span className="block text-center text-base leading-6 font-bold">A</span>
                </span>
                {row.foreground} / {row.background}{' '}
                <span className="text-muted">
                  ({row.kind === 'text' ? t('ds.contrastKindText') : t('ds.contrastKindUi')})
                </span>
              </th>
              <td className="tabular p-3">{row.ratio.toFixed(2)}:1</td>
              <td className="tabular p-3">{row.minimum.toFixed(1)}:1</td>
              <td className="p-3 font-semibold">
                {row.passes ? `✓ ${t('ds.contrastPass')}` : `✗ ${t('ds.contrastFail')}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
