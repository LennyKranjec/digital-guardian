import type { RouteObject } from 'react-router-dom';

import i18n from './shared/i18n';

/**
 * Erweiterungspunkte des Frontends. Ein Challenge-Paket (`challenge/frontend/plugin.tsx`) stellt
 * `register(api)` bereit und trägt Routen, Navigation, Rollen-Startseiten und Übersetzungen ein
 * (docs/EXTENDING.md). Die Plattform kennt keine Fachseiten.
 */

export interface NavItem {
  to: string;
  /** i18n-Schlüssel der Beschriftung (im selben Plugin über `registerCatalog` geliefert) */
  labelKey: string;
  /** nur für diese Rollen sichtbar; ohne Angabe für alle angemeldeten Personen */
  roles?: readonly string[];
}

const routes: RouteObject[] = [];
const navItems: NavItem[] = [];
const roleHome: Record<string, string> = {};

export const challengeRoutes = (): readonly RouteObject[] => routes;
export const challengeNav = (): readonly NavItem[] => navItems;

/** Startseite einer Rolle nach der Anmeldung; ohne Eintrag gilt `/`. */
export const homeFor = (role: string): string => roleHome[role] ?? '/';

export function registerRoutes(...added: RouteObject[]): void {
  routes.push(...added);
}

export function registerNav(...added: NavItem[]): void {
  navItems.push(...added);
}

export function registerRoleHome(role: string, home: string): void {
  roleHome[role] = home;
}

export function registerCatalog(locale: string, catalog: Record<string, unknown>): void {
  i18n.addResourceBundle(locale, 'translation', catalog, true, false);
}

/** Wird dem Plugin übergeben. */
export const pluginApi = { registerRoutes, registerNav, registerRoleHome, registerCatalog };
export type PluginApi = typeof pluginApi;

/** Nur für Tests: Registrierungen zurücksetzen. */
export function resetRegistry(): void {
  routes.length = 0;
  navItems.length = 0;
  for (const key of Object.keys(roleHome)) delete roleHome[key];
}
