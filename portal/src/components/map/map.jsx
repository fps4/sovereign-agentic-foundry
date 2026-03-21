import { lazy, Suspense } from 'react';
import { useIsClient } from 'minimal-shared/hooks';

import Skeleton from '@mui/material/Skeleton';
import { styled } from '@mui/material/styles';

import { CONFIG } from 'src/global-config';

// ----------------------------------------------------------------------

const LazyMap = lazy(() =>
  import('react-map-gl/mapbox').then((module) => ({ default: module.default }))
);

export function Map({ ref, sx, ...other }) {
  const isClient = useIsClient();

  const renderFallback = () => (
    <Skeleton
      variant="rectangular"
      sx={{
        top: 0,
        left: 0,
        width: 1,
        height: 1,
        position: 'absolute',
      }}
    />
  );

  return (
    <MapRoot sx={sx}>
      {isClient ? (
        <Suspense fallback={renderFallback()}>
          <LazyMap ref={ref} mapboxAccessToken={CONFIG.mapboxApiKey} {...other} />
        </Suspense>
      ) : (
        renderFallback()
      )}
    </MapRoot>
  );
}

// ----------------------------------------------------------------------

const MapRoot = styled('div')({
  width: '100%',
  overflow: 'hidden',
  position: 'relative',
});
