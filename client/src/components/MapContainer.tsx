import React from 'react';
import { GoogleMap, useJsApiLoader, Marker } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: 'calc(100vh - 64px)' };

const MapContainer: React.FC<any> = ({ places, onMarkerClick, center }) => {
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
  });

  if (!isLoaded) return <div>Loading...</div>;

  return (
    <GoogleMap mapContainerStyle={containerStyle} center={center} zoom={10}>
      {places.map((place: any) => (
        <Marker
          key={place.id}
          position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
          onClick={() => onMarkerClick(place)}
        />
      ))}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
