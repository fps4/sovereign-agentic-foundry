import { _orders } from 'src/_mock/_order';
import { CONFIG } from 'src/global-config';

import { OrderDetailsView } from 'src/sections/order/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Order details | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { id } = await params;

  const currentOrder = _orders.find((order) => order.id === id);

  return <OrderDetailsView order={currentOrder} />;
}
