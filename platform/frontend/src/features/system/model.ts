import { z } from 'zod';

/**
 * Form von GET /api/v1/meta: die Plattform kennt nur diese Felder; Fach-Erweiterungen kommen als
 * weitere Schlüssel (`passthrough`) und werden vom Challenge-Paket mit eigenem Schema gelesen.
 */
export const metaSchema = z
  .object({
    app_name: z.string(),
    version: z.string(),
    demo_mode: z.boolean(),
    synthetic_data: z.literal(true),
    roles: z.array(z.string()),
    challenge_loaded: z.boolean(),
  })
  .passthrough();

export type Meta = z.infer<typeof metaSchema>;
