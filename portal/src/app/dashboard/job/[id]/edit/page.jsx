import { _jobs } from 'src/_mock/_job';
import { CONFIG } from 'src/global-config';

import { JobEditView } from 'src/sections/job/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Job edit | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { id } = await params;

  const currentJob = _jobs.find((job) => job.id === id);

  return <JobEditView job={currentJob} />;
}
