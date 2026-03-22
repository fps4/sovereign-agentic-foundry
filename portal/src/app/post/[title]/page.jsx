import { CONFIG } from 'src/global-config';
import { getPost, getLatestPosts } from 'src/actions/blog-ssr';

import { PostDetailsHomeView } from 'src/sections/blog/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Post details - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { title } = await params;

  const { post } = await getPost(title);
  const { latestPosts } = await getLatestPosts(title);

  return <PostDetailsHomeView post={post} latestPosts={latestPosts} />;
}
