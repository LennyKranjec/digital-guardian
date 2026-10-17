import { pluginApi, type PluginApi } from './registry';

interface PluginModule {
  register?: (api: PluginApi) => void;
}

/**
 * Lädt `challenge/frontend/plugin.ts(x)`, falls vorhanden (Vite löst den Glob zur Build-Zeit auf;
 * ohne Datei ist die Liste leer und die Plattform bleibt ohne Fachfunktionen).
 */
const modules = import.meta.glob<PluginModule>('../../../challenge/frontend/plugin.{ts,tsx}', {
  eager: true,
});

export function loadChallengePlugins(): number {
  let loaded = 0;
  for (const module of Object.values(modules)) {
    module.register?.(pluginApi);
    loaded += 1;
  }
  return loaded;
}
