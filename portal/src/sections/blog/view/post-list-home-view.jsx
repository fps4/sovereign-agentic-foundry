'use client';

import { useState } from 'react';
import { orderBy } from 'es-toolkit';

import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';

import { POST_SORT_OPTIONS } from 'src/_mock';

import { EmptyContent } from 'src/components/empty-content';

import { PostList } from '../post-list';
import { PostSort } from '../post-sort';
import { PostSearch } from '../post-search';

// ----------------------------------------------------------------------

export function PostListHomeView({ posts }) {
  const [sortBy, setSortBy] = useState('latest');

  const dataFiltered = applyFilter({ inputData: posts, sortBy });

  const renderNoData = () => <EmptyContent filled sx={{ py: 10 }} />;

  const isEmpty = !posts.length;

  return (
    <Container sx={{ mb: 10 }}>
      <Typography variant="h4" sx={[{ my: { xs: 3, md: 5 } }]}>
        Blog
      </Typography>

      <Box
        sx={[
          {
            gap: 3,
            display: 'flex',
            mb: { xs: 3, md: 5 },
            justifyContent: 'space-between',
            flexDirection: { xs: 'column', sm: 'row' },
            alignItems: { xs: 'flex-end', sm: 'center' },
          },
        ]}
      >
        <PostSearch redirectPath={(title) => paths.post.details(title)} />

        <PostSort
          sort={sortBy}
          onSort={(newValue) => setSortBy(newValue)}
          sortOptions={POST_SORT_OPTIONS}
        />
      </Box>

      {isEmpty ? renderNoData() : <PostList posts={dataFiltered} />}
    </Container>
  );
}

// ----------------------------------------------------------------------

function applyFilter({ inputData, sortBy }) {
  if (sortBy === 'latest') {
    return orderBy(inputData, ['createdAt'], ['desc']);
  }

  if (sortBy === 'oldest') {
    return orderBy(inputData, ['createdAt'], ['asc']);
  }

  if (sortBy === 'popular') {
    return orderBy(inputData, ['totalViews'], ['desc']);
  }

  return inputData;
}
