import { NormalizedJob } from './types.js';

const TARGET_KEYWORDS = [
  'customer support',
  'customer success',
  'client success',
  'account coordinator',
  'sales support',
  'virtual assistant',
  'operations assistant',
  'scheduling coordinator',
  'support specialist',
  'support representative',
  'csr',
  'care coordinator',
  'client support',
  'support',
  'customer',
  'client',
  'success',
  'assistant',
  'operations',
  'sales',
];

export function filterJobs(jobs: NormalizedJob[]): NormalizedJob[] {
  return jobs.filter((job) => {
    const haystack = `${job.title} ${job.description}`.toLowerCase();
    const remoteMatch = job.remote || haystack.includes('remote');
    const keywordMatch = TARGET_KEYWORDS.some((keyword) => haystack.includes(keyword));
    const notCommissionOnly = !haystack.includes('commission only');
    const notSenior = !haystack.includes('senior') && !haystack.includes('lead');
    return remoteMatch && keywordMatch && notCommissionOnly && notSenior;
  });
}
