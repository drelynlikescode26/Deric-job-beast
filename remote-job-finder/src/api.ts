import { NormalizedJob } from './types.js';

const HIMALAYAS_URL = 'https://himalayas.app/jobs/api?category=customer-support&remote=true&limit=25';
const REMOTIVE_URL = 'https://remotive.com/api/remote-jobs?limit=25';
const LEVER_URL = 'https://api.lever.co/v0/postings?mode=json';
const GREENHOUSE_URL = 'https://boards-api.greenhouse.io/v1/boards/{board}/jobs';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}) for ${url}`);
  }
  return res.json() as Promise<T>;
}

function normalizeHimalayas(raw: any): NormalizedJob {
  return {
    source: 'himalayas',
    external_id: String(raw.id ?? raw.slug ?? raw.url),
    company: raw.company ?? 'Unknown Company',
    title: raw.title ?? 'Unknown Title',
    location: raw.location ?? 'Remote',
    remote: true,
    salary_min: raw.salary_min,
    salary_max: raw.salary_max,
    description: raw.description ?? '',
    apply_url: raw.url ?? raw.apply_url ?? '',
    posted_at: raw.date ?? new Date().toISOString(),
    employment_type: (raw.employment_type ?? 'full-time') as any,
    experience_level: raw.experience_level ?? 'entry-level',
  };
}

function normalizeRemotive(raw: any): NormalizedJob {
  return {
    source: 'remotive',
    external_id: String(raw.id ?? raw.slug),
    company: raw.company_name ?? 'Unknown Company',
    title: raw.title ?? 'Unknown Title',
    location: raw.candidate_required_location ?? 'Remote',
    remote: Boolean(raw.remote),
    salary_min: raw.salary_min,
    salary_max: raw.salary_max,
    description: raw.description ?? '',
    apply_url: raw.url ?? '',
    posted_at: raw.publication_date ?? new Date().toISOString(),
    employment_type: (raw.job_type ?? 'full-time') as any,
    experience_level: raw.experience_level ?? 'entry-level',
  };
}

function normalizeLever(raw: any): NormalizedJob {
  return {
    source: 'lever',
    external_id: String(raw.id ?? raw.text),
    company: raw.categories?.company ?? raw.organizations?.[0]?.name ?? 'Unknown Company',
    title: raw.text ?? 'Unknown Title',
    location: raw.categories?.location ?? 'Remote',
    remote: Boolean(raw.categories?.location?.toLowerCase().includes('remote') || raw.workplace === 'remote'),
    salary_min: undefined,
    salary_max: undefined,
    description: raw.description ?? '',
    apply_url: raw.applyUrl ?? raw.hostedUrl ?? '',
    posted_at: raw.createdAt ?? new Date().toISOString(),
    employment_type: (raw.categories?.commitment ?? 'full-time') as any,
    experience_level: raw.categories?.seniority ?? 'entry-level',
  };
}

export async function fetchJobs(): Promise<NormalizedJob[]> {
  const jobs: NormalizedJob[] = [];
  const errors: string[] = [];

  try {
    const himalayas = await fetchJson<any>(HIMALAYAS_URL);
    const himalayasItems = Array.isArray(himalayas) ? himalayas : himalayas.jobs ?? [];
    for (const item of himalayasItems) jobs.push(normalizeHimalayas(item));
  } catch (error) {
    errors.push(`Himalayas fetch failed: ${error}`);
  }

  try {
    const remotive = await fetchJson<any>(REMOTIVE_URL);
    const remotiveItems = Array.isArray(remotive) ? remotive : remotive.jobs ?? [];
    for (const item of remotiveItems) jobs.push(normalizeRemotive(item));
  } catch (error) {
    errors.push(`Remotive fetch failed: ${error}`);
  }

  try {
    const lever = await fetchJson<any[]>(LEVER_URL);
    for (const item of lever) jobs.push(normalizeLever(item));
  } catch (error) {
    errors.push(`Lever fetch failed: ${error}`);
  }

  return jobs;
}
