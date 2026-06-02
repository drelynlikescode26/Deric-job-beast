import { fetchJobs } from './api.js';
import { dedupeJobs } from './dedupe.js';
import { filterJobs } from './filter.js';
import { scoreJobs } from './score.js';
import { saveDailyReport, saveJobsSeen, logError } from './persist.js';

async function main() {
  const rawJobs = await fetchJobs();
  const filteredJobs = filterJobs(rawJobs);
  const uniqueJobs = dedupeJobs(filteredJobs);
  const scoredJobs = scoreJobs(uniqueJobs);

  try {
    await saveJobsSeen(uniqueJobs);
    await saveDailyReport({
      report_date: new Date().toISOString().slice(0, 10),
      jobs_scanned: rawJobs.length,
      jobs_sent: scoredJobs.length,
      duplicates_skipped: filteredJobs.length - uniqueJobs.length,
      errors_count: 0,
      email_sent: false,
    });
  } catch (error) {
    await logError('Persistence', error instanceof Error ? error.message : String(error), 'warning');
  }

  console.log(JSON.stringify({
    scanned: rawJobs.length,
    filtered: filteredJobs.length,
    unique: uniqueJobs.length,
    top: scoredJobs.length,
    jobs: scoredJobs,
  }, null, 2));
}

main().catch((error) => {
  console.error('Daily job run failed:', error);
  process.exitCode = 1;
});
