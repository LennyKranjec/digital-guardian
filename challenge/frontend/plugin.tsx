import { RequireRole } from '../../platform/frontend/src/features/auth/RequireRole';
import type { PluginApi } from '../../platform/frontend/src/registry';
import { cs } from './waechter/i18n/cs';
import { de } from './waechter/i18n/de';
import { en } from './waechter/i18n/en';
import { ClinicLayout } from './waechter/components/ClinicLayout';
import { AlertDetailPage } from './waechter/pages/AlertDetailPage';
import { AssessmentPage } from './waechter/pages/AssessmentPage';
import { ReportPage } from './waechter/pages/ReportPage';
import { SettingsPage } from './waechter/pages/SettingsPage';
import { PatientCockpitPage } from './waechter/pages/PatientCockpitPage';
import { ClinicWorklistPage } from './waechter/pages/ClinicWorklistPage';
import { EnrollPatientPage } from './waechter/pages/EnrollPatientPage';
import { MedicationDetailPage } from './waechter/pages/MedicationDetailPage';
import { MedicationsPage } from './waechter/pages/MedicationsPage';
import { PatientCheckinPage } from './waechter/pages/PatientCheckinPage';
import { PatientSessionPage } from './waechter/pages/PatientSessionPage';

/** Rollen laut Vertrag §2: Patientin nur /patient; Ärztin und Admin die Klinikseiten. */
export const PATIENT_ROLES = ['patient'] as const;
export const CLINIC_ROLES = ['clinician', 'admin'] as const;

export function register(api: PluginApi): void {
  api.registerRoutes(
    {
      element: <RequireRole roles={PATIENT_ROLES} />,
      children: [
        // adaptiver Check-in (v2.0); der Vollfragebogen bleibt als Rückfall (Papier/Telefon, fehlende Sitzungs-API)
        { path: 'patient', element: <PatientSessionPage /> },
        { path: 'patient/full', element: <PatientCheckinPage /> },
      ],
    },
    {
      element: <RequireRole roles={CLINIC_ROLES} />,
      children: [
        {
          element: <ClinicLayout />,
          children: [
            { path: 'clinic', element: <ClinicWorklistPage /> },
            { path: 'clinic/patients/new', element: <EnrollPatientPage /> },
            { path: 'clinic/patients/:patientId', element: <PatientCockpitPage /> },
            { path: 'clinic/patients/:patientId/assess', element: <AssessmentPage /> },
            { path: 'clinic/alerts/:alertId', element: <AlertDetailPage /> },
            { path: 'clinic/patients/:patientId/report', element: <ReportPage /> },
            { path: 'clinic/settings', element: <SettingsPage /> },
            { path: 'clinic/medications', element: <MedicationsPage /> },
            { path: 'clinic/medications/:medicationId', element: <MedicationDetailPage /> },
          ],
        },
      ],
    },
  );
  // „Mein Bereich“ der Plattform führt über die Rollen-Startseite zu Check-in bzw. Arbeitsliste;
  // eigene Einträge dafür wären doppelt (A3 Low 3). Arzneimittel und Einstellungen kommen hinzu.
  // Navigation bricht seit platform-fix fix/nav-wrap (Shell.tsx flex-wrap) auch bei 375 px um
  api.registerNav({
    to: '/clinic/medications',
    labelKey: 'waechter.nav.medications',
    roles: CLINIC_ROLES,
  });
  api.registerNav({
    to: '/clinic/settings',
    labelKey: 'waechter.nav.settings',
    roles: CLINIC_ROLES,
  });
  api.registerRoleHome('patient', '/patient');
  api.registerRoleHome('clinician', '/clinic');
  api.registerRoleHome('admin', '/clinic');
  api.registerCatalog('cs', cs);
  api.registerCatalog('en', en);
  api.registerCatalog('de', de);
}
