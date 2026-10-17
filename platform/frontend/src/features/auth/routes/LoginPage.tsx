import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { ApiClientError } from '../../../shared/api/client';
import { Button } from '../../../shared/ui/Button';
import { SkeletonBlock } from '../../../shared/ui/StateViews';
import { homeFor } from '../../../registry';
import { useMeta } from '../../system/api';
import { useDemoAccounts, useLogin, useMe } from '../api';
import type { DemoAccount } from '../model';

const INPUT =
  'min-h-11 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink';

function fromState(state: unknown): string | null {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = state.from;
    return typeof from === 'string' ? from : null;
  }
  return null;
}

function DemoAccountPicker({ onPick }: { onPick: (account: DemoAccount) => void }) {
  const { t } = useTranslation();
  const accounts = useDemoAccounts(true);

  return (
    <section
      aria-labelledby="demo-accounts-title"
      data-testid="demo-accounts"
      className="space-y-3 rounded-lg border border-border bg-sunken p-6"
    >
      <h2 id="demo-accounts-title" className="text-lg font-semibold">
        {t('auth.demo.title')}
      </h2>
      <p className="text-sm text-muted">{t('auth.demo.hint')}</p>
      {accounts.isPending ? <SkeletonBlock lines={2} /> : null}
      {accounts.isError ? (
        <div role="alert" className="space-y-2">
          <p>{t('auth.demo.loadError')}</p>
          <Button variant="secondary" onClick={() => void accounts.refetch()}>
            {t('states.retry')}
          </Button>
        </div>
      ) : null}
      {accounts.data?.length === 0 ? <p>{t('auth.demo.empty')}</p> : null}
      {accounts.data
        ? [...new Set(accounts.data.map((account) => account.role))].map((role) => {
            const group = accounts.data.filter((account) => account.role === role);
            if (group.length === 0) return null;
            return (
              <div
                key={role}
                role="group"
                aria-label={t(`roles.${role}`, { defaultValue: role })}
                className="space-y-2"
              >
                <h3 className="text-sm font-semibold text-muted">
                  {t(`roles.${role}`, { defaultValue: role })}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {group.map((account) => (
                    <Button
                      key={account.username}
                      variant="secondary"
                      onClick={() => onPick(account)}
                      data-testid={`demo-account-${account.username}`}
                    >
                      {account.label}
                    </Button>
                  ))}
                </div>
              </div>
            );
          })
        : null}
    </section>
  );
}

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const meta = useMeta();
  const me = useMe();
  const login = useLogin();
  const usernameId = useId();
  const passwordId = useId();
  const errorId = useId();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  if (me.data) return <Navigate to={homeFor(me.data.role)} replace />;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    login.mutate(
      { username: username.trim(), password },
      {
        onSuccess: (user) => {
          const from = fromState(location.state);
          const target =
            from?.startsWith('/') && !from.startsWith('//') ? from : homeFor(user.role);
          void navigate(target, { replace: true });
        },
      },
    );
  }

  const error = login.error;
  const errorText =
    error instanceof ApiClientError
      ? error.code === 'invalid_credentials'
        ? t('auth.errors.invalidCredentials')
        : error.isNetwork
          ? t('auth.errors.network')
          : t('auth.errors.generic')
      : error
        ? t('auth.errors.generic')
        : null;

  return (
    <div className="mx-auto w-full max-w-xl space-y-6">
      <header>
        <h1 className="text-3xl font-bold leading-tight">{t('auth.login.title')}</h1>
        <p className="mt-2 text-muted">{t('auth.login.intro')}</p>
      </header>

      <form
        onSubmit={onSubmit}
        noValidate
        className="space-y-4 rounded-lg border border-border bg-surface p-6 shadow-card"
        aria-describedby={errorText ? errorId : undefined}
      >
        <div className="space-y-2">
          <label htmlFor={usernameId} className="block font-semibold">
            {t('auth.login.username')}
          </label>
          <input
            id={usernameId}
            name="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className={INPUT}
          />
        </div>
        <div className="space-y-2">
          <label htmlFor={passwordId} className="block font-semibold">
            {t('auth.login.password')}
          </label>
          <input
            id={passwordId}
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={INPUT}
          />
        </div>
        {errorText ? (
          <p id={errorId} role="alert" className="font-semibold text-danger">
            <span aria-hidden="true">⚠ </span>
            {errorText}
          </p>
        ) : null}
        <Button
          type="submit"
          disabled={login.isPending || username.trim() === '' || password === ''}
        >
          {login.isPending ? t('auth.login.submitting') : t('auth.login.submit')}
        </Button>
      </form>

      {meta.data?.demo_mode ? (
        <DemoAccountPicker
          onPick={(account) => {
            setUsername(account.username);
            setPassword(account.password);
            login.reset();
          }}
        />
      ) : null}
    </div>
  );
}
