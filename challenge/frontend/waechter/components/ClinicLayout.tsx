import { matchPath, Outlet, useLocation } from 'react-router-dom';

import '../clinic-theme.css';
import { NotificationBanner } from './NotificationBanner';

/** Das Cockpit einer Patientin: dort ist das Banner auf eine Zeile eingeklappt (Platz für die Lage). */
const COCKPIT_PATH = '/clinic/patients/:patientId';

/**
 * Rahmen aller Klinikseiten: Sofortbenachrichtigungen oben, darunter die Seite. `clinic-theme` setzt das
 * Farbschema der Klinik-Oberfläche (clinic-theme.css); `clinic-prose` begrenzt Fließtext auf ~70ch (außer im Cockpit, S5).
 */
export function ClinicLayout() {
  const { pathname } = useLocation();
  const inCockpit = matchPath({ path: COCKPIT_PATH, end: true }, pathname) !== null;
  return (
    <div className={inCockpit ? 'clinic-theme min-w-0' : 'clinic-theme clinic-prose min-w-0'}>
      <NotificationBanner collapsible={inCockpit} />
      <Outlet />
    </div>
  );
}
