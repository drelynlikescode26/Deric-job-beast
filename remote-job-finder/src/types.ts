export type EmploymentType = 'full-time' | 'part-time' | 'contract' | 'temporary' | 'unknown';

export interface NormalizedJob {
  source: string;
  external_id: string;
  company: string;
  title: string;
  location: string;
  remote: boolean;
  salary_min?: number;
  salary_max?: number;
  description: string;
  apply_url: string;
  posted_at: string;
  employment_type: EmploymentType;
  experience_level: string;
  score?: number;
  why?: string[];
}

export interface FetchResult {
  jobs: NormalizedJob[];
  errors: string[];
}
