import { _tours } from 'src/_mock/_tour';
import { CONFIG } from 'src/global-config';

import { TourDetailsView } from 'src/sections/tour/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Tour details | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { id } = await params;

  const currentTour = _tours.find((tour) => tour.id === id);

  return <TourDetailsView tour={currentTour} />;
}

