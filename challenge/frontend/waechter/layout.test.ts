import { describe, expect, it } from 'vitest';

/** Quelltexte per Vite-Rohimport (kein Node-Dateizugriff nötig): Komponenten, Seiten und Plugin. */
const RAW: Record<string, string> = {
  ...import.meta.glob<string>('./{components,pages}/*.tsx', {
    query: '?raw',
    import: 'default',
    eager: true,
  }),
  ...import.meta.glob<string>('../plugin.tsx', { query: '?raw', import: 'default', eager: true }),
};
const BUTTON = Object.values(
  import.meta.glob<string>('../../../platform/frontend/src/shared/ui/Button.tsx', {
    query: '?raw',
    import: 'default',
    eager: true,
  }),
).join('');

const FILES = Object.entries(RAW).filter(([name]) => !/\.test\./.test(name));
const sourceOf = (suffix: string): string =>
  FILES.find(([name]) => name.endsWith(suffix))?.[1] ?? '';

/**
 * Statische Layoutprüfung (das echte 375-px-Rendering prüft A3 per E2E): Quelltext darf nichts
 * enthalten, das auf schmalen Bildschirmen horizontales Scrollen oder zu kleine Ziele/Schrift erzeugt.
 */
describe('Layout- und Barrierefreiheitsvorgaben im Challenge-Frontend (Quelltext)', () => {
  it('findet die erwarteten Quelldateien', () => {
    const names = FILES.map(([name]) => name);
    expect(names).toEqual(
      expect.arrayContaining([
        '../plugin.tsx',
        './pages/PatientCheckinPage.tsx',
        './components/QuestionGroup.tsx',
      ]),
    );
    expect(BUTTON).toContain('min-h-11');
  });

  it('verwendet keine festen Breiten ≥ 375 px, kein nowrap und kein horizontales Scrollen', () => {
    const offenders = FILES.flatMap(([name, text]) => {
      const hits: string[] = [];
      for (const match of text.matchAll(/\b(?:min-w|w)-\[(\d+(?:\.\d+)?)(px|rem)\]/g)) {
        const px = match[2] === 'rem' ? Number(match[1]) * 16 : Number(match[1]);
        if (px >= 375) hits.push(match[0]);
      }
      for (const pattern of [/whitespace-nowrap/, /overflow-x-(?:scroll|auto)/, /\bw-screen\b/]) {
        if (pattern.test(text)) hits.push(String(pattern));
      }
      return hits.map((hit) => `${name}: ${hit}`);
    });
    expect(offenders).toEqual([]);
  });

  it('verwendet keine Schrift unter 16 px (text-xs, text-sm, feste Größen)', () => {
    const offenders = FILES.flatMap(([name, text]) => {
      const hits: string[] = [];
      if (/\btext-(?:xs|sm)\b/.test(text)) hits.push('text-xs/text-sm');
      for (const match of text.matchAll(/text-\[(\d+(?:\.\d+)?)(px|rem)\]/g)) {
        const px = match[2] === 'rem' ? Number(match[1]) * 16 : Number(match[1]);
        if (px < 16) hits.push(match[0]);
      }
      return hits.map((hit) => `${name}: ${hit}`);
    });
    expect(offenders).toEqual([]);
  });

  it('zeichnet SVG-Beschriftung in mindestens 16 px (fontSize in echten Pixeln, nicht skaliert)', () => {
    const offenders = FILES.flatMap(([name, text]) =>
      Array.from(text.matchAll(/fontSize=\{(\d+(?:\.\d+)?)\}/g))
        .filter((match) => Number(match[1]) < 16)
        .map((match) => `${name}: ${match[0]}`),
    );
    expect(offenders).toEqual([]);
    expect(FILES.some(([, text]) => /fontSize=\{16\}/.test(text))).toBe(true);
  });

  it('gibt den Antwortkacheln eine Mindesthöhe von 44 px (min-h-11) und 16-px-Schrift', () => {
    const tiles = sourceOf('/QuestionGroup.tsx');
    expect(tiles).toMatch(/const TILE =[\s\S]*?\bmin-h-11\b/);
    expect(tiles).toMatch(/const TILE =[\s\S]*?\btext-base\b/);
  });

  it('hält die Belegschublade auf 375 px innerhalb des Bildschirms (volle Breite bis max-w-md, vertikal scrollbar)', () => {
    const drawer = sourceOf('/FactDrawer.tsx');
    expect(drawer).toMatch(/w-full[^"]*max-w-md/);
    expect(drawer).toMatch(/overflow-y-auto/);
    expect(drawer).toMatch(/role="dialog"/);
  });

  it('hält Quittieren-Dialog und Aufnahmekarten auf 375 px innerhalb der Breite und mit 44-px-Zielen', () => {
    const dialog = sourceOf('/AcknowledgeDialog.tsx');
    expect(dialog).toMatch(/w-full[^"]*max-w-lg/);
    expect(dialog).toMatch(/overflow-y-auto/);
    expect(dialog).toMatch(/role="dialog"/);
    expect(dialog).toMatch(/min-h-11/);
    const card = sourceOf('/AssessmentTermCard.tsx');
    expect(card).toMatch(/const TILE =[\s\S]*?min-h-11/);
    expect(card).toMatch(/min-w-0/);
    expect(card).toMatch(/break-words/);
  });

  it('gibt Beleg-Chips und der Warum-Schaltfläche 44-px-Ziele', () => {
    expect(sourceOf('/FactChip.tsx')).toMatch(/min-h-11[^"]*min-w-11/);
    expect(BUTTON).toContain('min-h-11');
  });

  it('lässt lange Texte umbrechen (min-w-0 + break-words an Kacheln, min-w-0 am fieldset)', () => {
    expect(sourceOf('/QuestionGroup.tsx')).toMatch(/min-w-0 break-words/);
    expect(sourceOf('/PatientCheckinPage.tsx')).toMatch(/<fieldset[\s\S]*?min-w-0/);
  });
});

/** Aufbau des Cockpits für den ersten Bildschirm (S5); das echte 1366×768-Rendering misst A3 per E2E. */
describe('Cockpit-Layout für 1366×768 und 375 px (Quelltext)', () => {
  const page = sourceOf('/PatientCockpitPage.tsx');

  it('legt Kopf/Meldungen und Kurzfassung erst ab 1200 px nebeneinander (darunter einspaltig)', () => {
    expect(page).toMatch(
      /data-testid="cockpit-grid"[\s\S]*?min-\[1200px\]:grid-cols-\[minmax\(0,1\.3fr\)_minmax\(0,1fr\)\]/,
    );
    expect(page).not.toMatch(/(?<![:\w-])grid-cols-2/);
    expect(page).not.toMatch(/\blg:grid-cols/);
  });

  it('ordnet im Quelltext Kopf, Meldungen, Kurzfassung, kompakten Verlauf und vollen Verlauf in dieser Reihenfolge an', () => {
    const order = [
      '<CockpitHeader',
      'data-testid="alerts-section"',
      '<SummaryPanel',
      '<TimelineCompact',
      '<TimelineSection',
    ].map((marker) => page.indexOf(marker));
    expect(order.every((index) => index >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('klappt das Banner nur im Cockpit ein (Arbeitsliste bleibt ausgeklappt)', () => {
    const layout = sourceOf('/ClinicLayout.tsx');
    expect(layout).toContain("'/clinic/patients/:patientId'");
    expect(layout).toMatch(/<NotificationBanner collapsible=\{inCockpit\}/);
    expect(sourceOf('/NotificationBanner.tsx')).toMatch(/aria-expanded=\{!folded\}/);
  });

  it('macht die kompakte Leiste bedienbar: Karten als Schaltflächen ≥ 44 px, Zeichnung ohne Textrolle', () => {
    const compact = sourceOf('/TimelineCompact.tsx');
    expect(compact).toMatch(/<button[\s\S]*?min-h-11/);
    expect(compact).toMatch(/aria-hidden="true"/);
    expect(compact).toContain('timeline-full');
    expect(sourceOf('/TimelineSection.tsx')).toContain('id="timeline-full"');
    expect(compact).not.toMatch(/<text\b/); // keine SVG-Schrift unter 16 px
  });

  it('hält Aufklapper (Kopf-Details, weitere Meldungen/Sätze) als 44-px-Ziele', () => {
    for (const name of ['/CockpitHeader.tsx', '/PatientCockpitPage.tsx', '/SummaryPanel.tsx']) {
      const text = sourceOf(name);
      expect(text, name).toMatch(/<summary[^>]*min-h-11/);
    }
  });
  // F-08 (A3-Restbefunde F-07 F-01, F-06 F-02/F-03, styles.css-Notlösung)
  it('rechnet Belegnummern im Bericht in 16 px (sup erbt sonst 75 %)', () => {
    expect(sourceOf('/ReportSections.tsx')).toMatch(/<sup[^>]*\btext-base\b/);
  });

  it('zeigt die Konfigurationshistorie unter 640 px als Karten statt als 5-Spalten-Tabelle', () => {
    const history = sourceOf('/ConfigHistory.tsx');
    expect(history).toMatch(/<table[^>]*\bblock\b[^>]*\bsm:table\b/s);
    expect(history).toMatch(/<tr[^>]*\bblock\b[^>]*\bsm:table-row\b/s);
    expect(history).toContain('data-label');
    expect(history).toMatch(/before:content-\[attr\(data-label\)\]/);
  });

  it('führt Stufe, Überschrift, Zeit und Knöpfe einer Meldung in einem Kopfbereich zusammen', () => {
    const card = sourceOf('/AlertCard.tsx');
    expect(card).toContain('data-testid="alert-card-head"');
    expect(card).toMatch(/min-\[1200px\]:line-clamp-2/);
    expect(card).not.toMatch(/\bp-3\b/); // kompakte Abstände (S5 bei 1366×768)
  });

  it('lädt kein eigenes Challenge-Stylesheet mehr (Tailwind @source der Plattform genügt)', () => {
    const plugin = sourceOf('../plugin.tsx');
    expect(plugin).not.toMatch(/styles\.css|loadChallengeStyles/);
  });
  // F-10 adaptiver Check-in
  it('legt /patient auf den adaptiven Check-in und /patient/full auf den Vollfragebogen', () => {
    const plugin = sourceOf('../plugin.tsx');
    expect(plugin).toMatch(/path: 'patient',\s*element: <PatientSessionPage/);
    expect(plugin).toMatch(/path: 'patient\/full',\s*element: <PatientCheckinPage/);
  });

  it('zeigt den Akut-Hinweis vor Tipps und Bestätigung und lässt Platzhalter weg', () => {
    const confirmation = sourceOf('/SubmitConfirmation.tsx');
    const escalation = confirmation.indexOf('<EscalationNotice escalation');
    const advice = confirmation.indexOf('<AdviceList advice');
    const saved = confirmation.indexOf('id="checkin-saved-title"');
    expect(escalation).toBeGreaterThan(-1);
    expect(escalation).toBeLessThan(advice);
    expect(advice).toBeLessThan(saved);
    // der Platzhalter erscheint nur, wenn der Server gar keine Eskalation liefert
    expect(confirmation).toMatch(/receipt\.escalation \? null : \(/);
  });

  it('gibt der Sitzungskarte große Antwortkacheln (QuestionGroup) und genau eine h1 auf der Seite', () => {
    expect(sourceOf('/SessionCard.tsx')).toContain('<QuestionGroup');
    const page = sourceOf('/PatientSessionPage.tsx');
    expect(page.match(/<h1\b/g)).toHaveLength(1);
    expect(sourceOf('/SessionCard.tsx')).not.toMatch(/<h1\b/);
  });
  // F-11 Triage-Befund und Regelkarte
  it('hängt den Triage-Befund unter das Raster (erster Bildschirm S5 bleibt) und klappt ihn als 44-px-Ziel auf', () => {
    const page = sourceOf('/PatientCockpitPage.tsx');
    const grid = page.indexOf('data-testid="cockpit-grid"');
    const panel = page.indexOf('<TriagePanel');
    expect(grid).toBeGreaterThan(-1);
    expect(panel).toBeGreaterThan(grid);
    // seit T-32 liegen die sekundären Bereiche in den Tabs unter dem Raster (CockpitTabs)
    expect(panel).toBeGreaterThan(page.indexOf('<CockpitTabs'));
    expect(sourceOf('/TriagePanel.tsx')).toMatch(/<summary[^>]*min-h-11/);
    expect(sourceOf('/TriageRules.tsx')).toMatch(/<summary[^>]*min-h-11/);
  });

  it('zeigt Tipp-Regeln und Empfehlungen als Karten unter 640 px (CardTable) statt als breite Tabelle', () => {
    const table = sourceOf('/CardTable.tsx');
    expect(table).toMatch(/<table[\s\S]*?\bblock\b[\s\S]*?\bsm:table\b/);
    expect(table).toContain('data-label');
    expect(sourceOf('/AdviceRules.tsx')).toContain('<CardTable');
    expect(sourceOf('/TriagePanel.tsx')).toContain('<CardTable');
  });
  // F-12 Arzneimittelsuche
  it('trägt die Arzneimittelsuche in die Kopfnavigation ein (Shell bricht seit fix/nav-wrap um) und verlinkt sie auch von der Arbeitsliste', () => {
    const plugin = sourceOf('../plugin.tsx');
    expect(plugin).toContain("labelKey: 'waechter.nav.medications'");
    expect(sourceOf('/ClinicWorklistPage.tsx')).toContain('to="/clinic/medications"');
    expect(plugin).toContain("path: 'clinic/medications'");
    expect(plugin).toContain("path: 'clinic/medications/:medicationId'");
  });

  // F-13 FHIR-Export und -Push
  it('zeigt „An FHIR-Server senden“ nur der Administration und lädt das Transaction-Bundle als Datei', () => {
    const exportButton = sourceOf('/ExportButton.tsx');
    expect(exportButton).toMatch(/isAdmin \? <PushButton/);
    expect(exportButton).toContain("role === 'admin'");
    expect(exportButton).toContain('type="transaction"');
    expect(exportButton).toContain('data-testid="push-status"');
  });

  it('lässt die Aktionsleiste unverändert und legt die neuen FHIR-Aktionen eingeklappt unter das Raster (S5, 375 px)', () => {
    const page = sourceOf('/PatientCockpitPage.tsx');
    expect(page.indexOf('<FhirPanel')).toBeGreaterThan(page.indexOf('data-testid="cockpit-grid"'));
    expect(page.indexOf('<FhirPanel')).toBeGreaterThan(page.indexOf('<CockpitTabs'));
    expect(sourceOf('/CockpitActions.tsx')).not.toContain('FhirActions');
    expect(sourceOf('/FhirPanel.tsx')).toMatch(/<summary[^>]*min-h-11/);
  });

  it('gibt dem Suchfeld ein Label, 16-px-Schrift und 44-px-Ziele und öffnet SPC im neuen Tab mit noopener', () => {
    const page = sourceOf('/MedicationsPage.tsx');
    expect(page).toMatch(/<label htmlFor="medication-q"/);
    expect(page).toMatch(/<input[\s\S]*?min-h-11/);
    expect(page).toContain('role="search"');
    const card = sourceOf('/MedicationCard.tsx');
    expect(card).toContain('target="_blank"');
    expect(card).toContain('rel="noopener noreferrer"');
    expect(sourceOf('/CockpitHeader.tsx')).toMatch(/medicationSearchPath[\s\S]*min-h-11/);
  });
});
