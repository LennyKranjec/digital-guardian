import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/** Erfundene Beispielwerte (ohne Bezug zu realen Personen). Ausdrücklich als synthetisch gekennzeichnet. */
export const SYNTHETIC_SERIES = [
  { day: 1, a: 2, b: 3 },
  { day: 2, a: 3, b: 3 },
  { day: 3, a: 3, b: 4 },
  { day: 4, a: 5, b: 4 },
  { day: 5, a: 4, b: 5 },
  { day: 6, a: 6, b: 5 },
  { day: 7, a: 5, b: 6 },
] as const;

const AXIS = { fill: 'var(--rk-text-muted)', fontSize: 14 };

export function ChartExample() {
  const { t } = useTranslation();
  return (
    <figure className="rounded-lg border border-border bg-surface p-4">
      <div role="img" aria-label={t('ds.chartAlt')} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={200} minHeight={200}>
          <LineChart
            data={[...SYNTHETIC_SERIES]}
            margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
          >
            <CartesianGrid stroke="var(--rk-chart-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="day"
              tick={AXIS}
              stroke="var(--rk-border-strong)"
              label={{ value: t('ds.chartDay'), position: 'insideBottom', offset: -2, ...AXIS }}
            />
            <YAxis tick={AXIS} stroke="var(--rk-border-strong)" width={32} />
            <Tooltip
              contentStyle={{
                background: 'var(--rk-surface)',
                border: '1px solid var(--rk-border-strong)',
                color: 'var(--rk-text)',
              }}
            />
            <Legend wrapperStyle={{ color: 'var(--rk-text)' }} />
            <Line
              type="monotone"
              dataKey="a"
              name={t('ds.chartSeries')}
              stroke="var(--rk-chart-1)"
              strokeWidth={3}
              dot={{ r: 4 }}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="b"
              name={t('ds.chartSeriesB')}
              stroke="var(--rk-chart-2)"
              strokeWidth={3}
              strokeDasharray="6 4"
              dot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-3 inline-block rounded-sm bg-accent-subtle px-2 py-1 text-sm font-semibold text-accent-subtle-ink">
        {t('ds.chartSynthetic')}
      </figcaption>
    </figure>
  );
}
