/**
 * Supabase browser client removed — auth goes through rate-limited Flask
 * endpoints and sessionStore. This module remains only so older imports
 * fail loudly instead of shipping an anon key in the bundle.
 */
export const supabase = null;
export const isSupabaseConfigured = true;
