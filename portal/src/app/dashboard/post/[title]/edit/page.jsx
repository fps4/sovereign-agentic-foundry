import { kebabCase } from 'es-toolkit';

import { CONFIG } from 'src/global-config';
import { getPost } from 'src/actions/blog-ssr';
import axios, { endpoints } from 'src/lib/axios';

import { PostEditView } from 'src/sections/blog/view';

// ----------------------------------------------------------------------

export const metadata = { title: `Post edit | Dashboard - ${CONFIG.appName}` };

export default async function Page({ params }) {
  const { title } = await params;

  const { post } = await getPost(title);

  return <PostEditView post={post} />;
}
