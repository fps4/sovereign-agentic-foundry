import { CONFIG } from 'src/global-config';

import { MapView } from 'src/sections/_examples/extra/map-view';

// ----------------------------------------------------------------------

export const metadata = { title: `Map | Components - ${CONFIG.appName}` };

export default function Page() {
  return <MapView />;
}
