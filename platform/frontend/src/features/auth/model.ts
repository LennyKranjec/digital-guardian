import { z } from 'zod';

/** Rollen sind frei benannte Texte aus der Backend-Registry (kein festes Enum in der Plattform). */
export type Role = string;

/** Form von POST /auth/login und GET /auth/me. */
export const userSchema = z.object({
  id: z.string(),
  username: z.string(),
  display_name: z.string(),
  role: z.string(),
  subject_id: z.string().nullable().optional(),
});
export type User = z.infer<typeof userSchema>;

/** Form von GET /demo/accounts (nur im DEMO_MODE). */
export const demoAccountSchema = z.object({
  username: z.string(),
  password: z.string(),
  role: z.string(),
  label: z.string(),
});
export const demoAccountsSchema = z.array(demoAccountSchema);
export type DemoAccount = z.infer<typeof demoAccountSchema>;
