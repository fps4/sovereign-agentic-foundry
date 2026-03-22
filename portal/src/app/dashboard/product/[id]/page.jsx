import { CONFIG } from 'src/global-config';
import axios, { endpoints } from 'src/lib/axios';
import { getProduct } from 'src/actions/product-ssr';

import { ProductDetailsView } from 'src/sections/product/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Product details | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { id } = await params;

  const { product } = await getProduct(id);

  return <ProductDetailsView product={product} />;
}
