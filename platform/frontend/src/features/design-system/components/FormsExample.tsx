import * as Checkbox from '@radix-ui/react-checkbox';
import * as RadioGroup from '@radix-ui/react-radio-group';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

const INPUT =
  'min-h-11 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink';
const CHOICE = 'inline-flex min-h-11 cursor-pointer items-center gap-1 pr-2';

export function FormsExample() {
  const { t } = useTranslation();
  const textId = useId();
  const hintId = useId();
  const invalidId = useId();
  const errorId = useId();
  const checkboxId = useId();
  const radioA = useId();
  const radioB = useId();

  return (
    <div className="grid gap-6 rounded-lg border border-border bg-surface p-6 md:grid-cols-2">
      <div className="space-y-2">
        <label htmlFor={textId} className="block font-semibold">
          {t('ds.fieldText')}
        </label>
        <input id={textId} type="text" aria-describedby={hintId} className={INPUT} />
        <p id={hintId} className="text-sm text-muted">
          {t('ds.fieldHint')}
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor={invalidId} className="block font-semibold">
          {t('ds.fieldInvalidLabel')}
        </label>
        <input
          id={invalidId}
          type="text"
          aria-invalid="true"
          aria-describedby={errorId}
          className={`${INPUT} border-danger`}
        />
        <p id={errorId} className="text-sm font-semibold text-danger">
          <span aria-hidden="true">⚠ </span>
          {t('ds.fieldError')}
        </p>
      </div>

      <fieldset className="space-y-1">
        <legend className="mb-1 font-semibold">{t('ds.radioLegend')}</legend>
        <RadioGroup.Root defaultValue="a" aria-label={t('ds.radioLegend')} className="space-y-1">
          <label htmlFor={radioA} className={CHOICE}>
            <RadioGroup.Item
              id={radioA}
              value="a"
              className="group flex size-11 shrink-0 items-center justify-center"
            >
              <span className="flex size-6 items-center justify-center rounded-full border-2 border-border-strong bg-surface group-data-[state=checked]:border-accent">
                <RadioGroup.Indicator className="size-3 rounded-full bg-accent" />
              </span>
            </RadioGroup.Item>
            <span>{t('ds.radioA')}</span>
          </label>
          <label htmlFor={radioB} className={CHOICE}>
            <RadioGroup.Item
              id={radioB}
              value="b"
              className="group flex size-11 shrink-0 items-center justify-center"
            >
              <span className="flex size-6 items-center justify-center rounded-full border-2 border-border-strong bg-surface group-data-[state=checked]:border-accent">
                <RadioGroup.Indicator className="size-3 rounded-full bg-accent" />
              </span>
            </RadioGroup.Item>
            <span>{t('ds.radioB')}</span>
          </label>
        </RadioGroup.Root>
      </fieldset>

      <label htmlFor={checkboxId} className={CHOICE}>
        <Checkbox.Root
          id={checkboxId}
          className="group flex size-11 shrink-0 items-center justify-center"
        >
          <span className="flex size-6 items-center justify-center rounded-sm border-2 border-border-strong bg-surface group-data-[state=checked]:border-accent group-data-[state=checked]:bg-accent">
            <Checkbox.Indicator className="text-on-accent">
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path
                  d="M3 8.5l3.2 3L13 4.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </Checkbox.Indicator>
          </span>
        </Checkbox.Root>
        <span>{t('ds.checkbox')}</span>
      </label>
    </div>
  );
}
