import dotenv from 'dotenv';

dotenv.config();

export const config = {
  supabaseUrl: process.env.SUPABASE_URL ?? '',
  supabaseAnonKey: process.env.SUPABASE_ANON_KEY ?? '',
  supabaseServiceRoleKey: process.env.SUPABASE_SERVICE_ROLE_KEY ?? '',
  gmailTo: process.env.GMAIL_TO ?? '',
  gmailCc: process.env.GMAIL_CC ?? '',
};

export function hasSupabaseConfig() {
  return Boolean(config.supabaseUrl && config.supabaseAnonKey);
}
