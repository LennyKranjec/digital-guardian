import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { CockpitTabs } from './CockpitTabs';

const TABS = [
  { id: 'a', label: 'Verlauf', content: <p>Inhalt A</p> },
  { id: 'b', label: 'Export', content: <p>Inhalt B</p> },
  { id: 'c', label: 'Triage', content: <p>Inhalt C</p> },
];

describe('CockpitTabs (T-32): ein Bereich sichtbar, alle eingehängt', () => {
  it('zeigt anfangs nur den gewählten Bereich, die anderen bleiben im DOM (hidden)', () => {
    render(<CockpitTabs label="Bereiche" tabs={TABS} initial="b" />);
    expect(screen.getByRole('tab', { name: 'Export' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Inhalt B')).toBeVisible();
    expect(screen.getByTestId('cockpit-panel-a')).not.toBeVisible();
    expect(screen.getByText('Inhalt A', { selector: 'p' })).toBeInTheDocument();
  });

  it('wechselt per Klick und per Pfeiltasten (zyklisch) und setzt den Fokus', async () => {
    const user = userEvent.setup();
    render(<CockpitTabs label="Bereiche" tabs={TABS} />);
    expect(screen.getByText('Inhalt A')).toBeVisible();
    await user.click(screen.getByTestId('cockpit-tab-b'));
    expect(screen.getByText('Inhalt B')).toBeVisible();
    expect(screen.getByTestId('cockpit-panel-a')).not.toBeVisible();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByTestId('cockpit-tab-c')).toHaveFocus();
    expect(screen.getByText('Inhalt C')).toBeVisible();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByTestId('cockpit-tab-a')).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(screen.getByTestId('cockpit-tab-c')).toHaveFocus();
  });

  it('hat Tab-Rollen, Bezüge und Touchziele ab 44 px (min-h-11)', () => {
    render(<CockpitTabs label="Bereiche" tabs={TABS} />);
    expect(screen.getByRole('tablist', { name: 'Bereiche' })).toBeInTheDocument();
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab.className).toContain('min-h-11');
      const panel = document.getElementById(tab.getAttribute('aria-controls') ?? '');
      expect(panel).toHaveAttribute('role', 'tabpanel');
    }
  });
});
