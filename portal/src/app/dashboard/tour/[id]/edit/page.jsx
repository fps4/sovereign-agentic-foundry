import { _tours } from 'src/_mock/_tour';
import { CONFIG } from 'src/global-config';

import { TourEditView } from 'src/sections/tour/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Tour edit | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { id } = await params;

  const currentTour = _tours.find((tour) => tour.id === id);

  return <TourEditView tour={currentTour} />;
}
