import { createClient } from '@supabase/supabase-js';
import { NormalizedJob } from './types.js';
import { config, hasSupabaseConfig } from './config.js';

const supabase = hasSupabaseConfig()
  ? createClient(config.supabaseUrl, config.supabaseServiceRoleKey || config.supabaseAnonKey)
  : null;

export async function saveJobsSeen(jobs: NormalizedJob[]) {
  if (!supabase) {
    return { status: 'skipped', reason: 'Supabase not configured' };
  }

  const rows = jobs.map((job) => ({
    source: job.source,
    company: job.company,
    title: job.title,
    apply_url: job.apply_url,
    posted_at: job.posted_at,
    first_seen_at: new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
  }));

  const { error } = await supabase.from('jobs_seen').insert(rows);
  if (error) throw error;

  return { status: 'saved', count: rows.length };
}

export async function saveDailyReport(summary: {
  report_date: string;
  jobs_scanned: number;
  jobs_sent: number;
  duplicates_skipped: number;
  errors_count: number;
  email_sent: boolean;
}) {
  if (!supabase) {
    return { status: 'skipped', reason: 'Supabase not configured' };
  }

  const { error } = await supabase.from('daily_reports').insert(summary);
  if (error) throw error;

  return { status: 'saved' };
}

export async function logError(service: string, message: string, severity: 'info' | 'warning' | 'error' = 'warning') {
  if (!supabase) {
    return { status: 'skipped', reason: 'Supabase not configured' };
  }

  const { error } = await supabase.from('errors').insert({ service, message, severity, resolved: false });
  if (error) throw error;

  return { status: 'saved' };
}
