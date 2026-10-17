import type { ReactNode } from 'react';

export interface CardTableColumn {
  key: string;
  label: string;
}

export interface CardTableRow {
  id: string;
  /** je Spalte der Inhalt, gleiche Reihenfolge wie `columns` */
  cells: ReactNode[];
}

const CELL =
  'block break-words px-2 py-1 text-left align-top text-base before:mr-1 before:font-semibold before:text-muted before:content-[attr(data-label)] sm:table-cell sm:py-2 sm:before:content-none';

/**
 * Kleine Lesetabelle: ab 640 px echte Tabelle, darunter pro Zeile eine Karte mit Beschriftung vor jedem
 * Wert (kein horizontales Scrollen auf 375 px). Die ARIA-Rollen halten die Tabellensemantik, obwohl
 * display:block sie in manchen Browsern auflöst.
 */
export function CardTable({
  label,
  columns,
  rows,
  testId,
}: {
  label: string;
  columns: readonly CardTableColumn[];
  rows: readonly CardTableRow[];
  testId?: string;
}) {
  return (
    <table
      role="table"
      aria-label={label}
      data-testid={testId}
      className="block w-full border-collapse sm:table"
    >
      <thead role="rowgroup" className="sr-only sm:not-sr-only sm:table-header-group">
        <tr role="row" className="border-b border-border-strong">
          {columns.map((column) => (
            <th
              key={column.key}
              role="columnheader"
              scope="col"
              className="px-2 py-2 text-left text-base font-semibold text-muted"
            >
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody role="rowgroup" className="block sm:table-row-group">
        {rows.map((row) => (
          <tr
            key={row.id}
            role="row"
            className="mb-2 block rounded-md border border-border p-2 sm:mb-0 sm:table-row sm:rounded-none sm:border-0 sm:border-b sm:p-0"
          >
            {row.cells.map((cell, index) => (
              <td
                key={columns[index]?.key ?? index}
                role="cell"
                data-label={columns[index]?.label}
                className={CELL}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
