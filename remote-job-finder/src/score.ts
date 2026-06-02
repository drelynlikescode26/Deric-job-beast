import { NormalizedJob } from './types.js';

export function scoreJobs(jobs: NormalizedJob[]): NormalizedJob[] {
  return jobs
    .map((job) => {
      const haystack = `${job.title} ${job.description}`.toLowerCase();
      let score = 0;
      const why: string[] = [];

      if (job.remote) {
        score += 20;
        why.push('remote-friendly role');
      }
      if (haystack.includes('customer support') || haystack.includes('customer success') || haystack.includes('client support')) {
        score += 25;
        why.push('customer-facing work matches the target profile');
      }
      if (haystack.includes('entry level') || haystack.includes('associate') || haystack.includes('specialist')) {
        score += 15;
        why.push('entry-level friendly language');
      }
      if (job.salary_min && job.salary_max) {
        score += 10;
        why.push('salary range is available');
      }

      return { ...job, score: Math.min(100, score), why };
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 10);
}
