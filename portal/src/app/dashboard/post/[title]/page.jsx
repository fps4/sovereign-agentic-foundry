import { CONFIG } from 'src/global-config';
import { getPost } from 'src/actions/blog-ssr';

import { PostDetailsView } from 'src/sections/blog/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Post details | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { title } = await params;

  const { post } = await getPost(title);

  return <PostDetailsView post={post} />;
}
