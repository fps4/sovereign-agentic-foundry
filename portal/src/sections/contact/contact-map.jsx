import { useState } from 'react';

import Typography from '@mui/material/Typography';
import { useColorScheme } from '@mui/material/styles';

import { Iconify } from 'src/components/iconify';
import { Map, MapPopup, MapMarker, MapControls } from 'src/components/map';

// ----------------------------------------------------------------------

export function ContactMap({ contacts, sx }) {
  const { mode } = useColorScheme();

  const [popupInfo, setPopupInfo] = useState(null);

  return (
    <Map
      initialViewState={{ latitude: 12, longitude: 42, zoom: 2 }}
      mapStyle={`mapbox://styles/mapbox/${mode === 'light' ? 'light' : 'dark'}-v10`}
      sx={[
        () => ({
          borderRadius: 1.5,
          height: { xs: 320, md: 560 },
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <MapControls hideGeolocate />

      {contacts.map((country, index) => (
        <MapMarker
          key={`marker-${index}`}
          latitude={country.latlng[0]}
          longitude={country.latlng[1]}
          onClick={(event) => {
            event.originalEvent.stopPropagation();
            setPopupInfo(country);
          }}
        />
      ))}

      {popupInfo && (
        <MapPopup
          longitude={popupInfo.latlng[1]}
          latitude={popupInfo.latlng[0]}
          onClose={() => setPopupInfo(null)}
        >
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Address
          </Typography>

          <Typography component="div" variant="caption">
            {popupInfo.address}
          </Typography>

          <Typography
            component="div"
            variant="caption"
            sx={{ mt: 1, display: 'flex', alignItems: 'center' }}
          >
            <Iconify icon="solar:phone-bold" width={14} sx={{ mr: 0.5 }} />
            {popupInfo.phoneNumber}
          </Typography>
        </MapPopup>
      )}
    </Map>
  );
}
