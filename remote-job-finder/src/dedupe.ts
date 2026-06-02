import crypto from 'node:crypto';
import { NormalizedJob } from './types.js';

export function fingerprint(job: NormalizedJob): string {
  const value = `${job.company.trim().toLowerCase()}|${job.title.trim().toLowerCase()}|${job.apply_url.trim().toLowerCase()}`;
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function dedupeJobs(jobs: NormalizedJob[]): NormalizedJob[] {
  const seen = new Set<string>();
  return jobs.filter((job) => {
    const id = fingerprint(job);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}
