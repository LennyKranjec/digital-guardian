import { useTranslation } from 'react-i18next';
import { createBrowserRouter, type RouteObject } from 'react-router-dom';

import { LoginPage } from '../features/auth/routes/LoginPage';
import { HomePage } from '../features/system/routes/HomePage';
import { challengeRoutes } from '../registry';
import { LinkButton } from '../shared/ui/LinkButton';
import { ForbiddenState, NotFoundState } from '../shared/ui/StateViews';
import { HydrateFallback } from './HydrateFallback';
import { Shell } from './Shell';

function BackHomeLink() {
  const { t } = useTranslation();
  return <LinkButton to="/">{t('states.backHome')}</LinkButton>;
}

export function NotFoundPage() {
  return <NotFoundState headingLevel={1} action={<BackHomeLink />} />;
}

export function ForbiddenPage() {
  return <ForbiddenState headingLevel={1} action={<BackHomeLink />} />;
}

/** Routentabelle der Plattform plus die vom Challenge-Paket registrierten Routen (registry.ts). */
export function buildRoutes(): RouteObject[] {
  return [
    {
      element: <Shell />,
      HydrateFallback,
      children: [
        { index: true, element: <HomePage /> },
        {
          path: 'design-system',
          lazy: async () => {
            const { DesignSystemPage } =
              await import('../features/design-system/routes/DesignSystemPage');
            return { Component: DesignSystemPage };
          },
        },
        { path: 'login', element: <LoginPage /> },
        ...challengeRoutes(),
        { path: 'forbidden', element: <ForbiddenPage /> },
        { path: '*', element: <NotFoundPage /> },
      ],
    },
  ];
}

export const createAppRouter = () => createBrowserRouter(buildRoutes());
