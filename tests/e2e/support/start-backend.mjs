// Startet das Backend für Playwright (plattformneutral, nutzt das venv aus scripts/setup).
// Aufruf: node tests/e2e/support/start-backend.mjs   (Port über E2E_BACKEND_PORT, Standard 8100)
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const backendDir = join(repoRoot, 'platform', 'backend');
const venvPython =
  process.platform === 'win32'
    ? join(backendDir, '.venv', 'Scripts', 'python.exe')
    : join(backendDir, '.venv', 'bin', 'python');
const python = process.env.E2E_PYTHON ?? venvPython;

if (!existsSync(python)) {
  console.error(`Python nicht gefunden: ${python}. Zuerst scripts/setup ausführen.`);
  process.exit(1);
}

const port = process.env.E2E_BACKEND_PORT ?? '8100';
const env = {
  ...process.env,
  DEMO_MODE: 'true',
  // Eigene Wegwerf-Datenbank, damit E2E nie die Entwicklungsdaten berührt.
  DATABASE_URL: 'sqlite:///data/e2e.db',
};

// Frische DB je Lauf: Datei löschen, migrieren, neutrale Demo-Konten seeden.
for (const suffix of ['', '-journal', '-wal', '-shm']) {
  rmSync(join(backendDir, 'data', `e2e.db${suffix}`), { force: true });
}
const init = spawnSync(python, ['-m', 'app.cli', 'seed'], {
  cwd: backendDir,
  stdio: 'inherit',
  env,
});
if (init.status !== 0) {
  console.error('seed fehlgeschlagen (Exitcode ' + String(init.status) + ').');
  process.exit(init.status ?? 1);
}

const child = spawn(
  python,
  ['-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', port],
  { cwd: backendDir, stdio: 'inherit', env },
);

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill());
}
child.on('exit', (code) => process.exit(code ?? 0));
