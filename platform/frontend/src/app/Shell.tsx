import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { useLogout, useMe } from '../features/auth/api';
import { useMeta } from '../features/system/api';
import { challengeNav, homeFor } from '../registry';
import { Button } from '../shared/ui/Button';
import { useOnlineStatus } from '../shared/lib/useOnlineStatus';
import { DemoBanner } from './DemoBanner';
import { LanguageSelect } from './LanguageSelect';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';

const NAV_LINK =
  'inline-flex min-h-11 items-center rounded-md px-3 font-semibold text-ink hover:bg-sunken aria-[current=page]:bg-accent-subtle aria-[current=page]:text-accent-subtle-ink';

export function Shell() {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const meta = useMeta();
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  // Einzige Quelle des Anzeigenamens ist /meta (config/app/challenge.yaml); kein i18n-Fallback.
  const appName = meta.data?.app_name;
  const user = me.data ?? null;

  useEffect(() => {
    document.title = appName ?? '';
  }, [appName]);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-4 focus:py-3 focus:text-on-accent"
      >
        {t('a11y.skipToContent')}
      </a>
      <DemoBanner />
      {online ? null : (
        <div
          role="status"
          data-testid="offline-banner"
          className="border-b border-border bg-status-info-bg px-4 py-2 text-center text-sm font-semibold text-status-info-fg"
        >
          {t('states.offlineTitle')}: {t('states.offlineBody')}
        </div>
      )}
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
          <span className="inline-flex items-center gap-2 text-accent">
            <Logo />
            <span className="text-lg font-bold text-ink" data-testid="app-name">
              {appName ?? ''}
            </span>
          </span>
          <nav aria-label={t('a11y.mainNavigation')} className="flex flex-wrap gap-1">
            <NavLink to="/" end className={NAV_LINK}>
              {t('nav.home')}
            </NavLink>
            {user ? (
              <NavLink to={homeFor(user.role)} className={NAV_LINK}>
                {t('nav.myArea')}
              </NavLink>
            ) : null}
            {challengeNav()
              .filter((item) => user && (!item.roles || item.roles.includes(user.role)))
              .map((item) => (
                <NavLink key={item.to} to={item.to} className={NAV_LINK}>
                  {t(item.labelKey)}
                </NavLink>
              ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {meta.data?.demo_mode ? (
              <NavLink
                to="/design-system"
                aria-label={t('nav.designSystem')}
                title={t('nav.designSystem')}
                data-testid="nav-design-system"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border-strong bg-surface text-ink hover:bg-sunken"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  width="22"
                  height="22"
                  fill="currentColor"
                >
                  <rect x="4" y="6" width="16" height="2" rx="1" />
                  <rect x="4" y="11" width="16" height="2" rx="1" />
                  <rect x="4" y="16" width="16" height="2" rx="1" />
                </svg>
              </NavLink>
            ) : null}
            <LanguageSelect />
            <ThemeToggle />
            {user ? (
              <div className="flex flex-wrap items-center gap-2" data-testid="session-info">
                <span className="text-sm">
                  <span className="font-semibold">{user.display_name}</span>{' '}
                  <span className="text-muted">
                    ({t(`roles.${user.role}`, { defaultValue: user.role })})
                  </span>
                </span>
                <Button
                  variant="secondary"
                  disabled={logout.isPending}
                  onClick={() =>
                    logout.mutate(undefined, { onSuccess: () => void navigate('/login') })
                  }
                >
                  {t('auth.logout')}
                </Button>
                {logout.isError ? (
                  <span role="alert" className="text-sm font-semibold text-danger">
                    {t('auth.errors.logout')}
                  </span>
                ) : null}
              </div>
            ) : me.isSuccess ? (
              <NavLink to="/login" className={NAV_LINK}>
                {t('auth.login.nav')}
              </NavLink>
            ) : null}
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
