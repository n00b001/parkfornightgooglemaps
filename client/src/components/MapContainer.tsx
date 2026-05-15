import React from 'react';
import { GoogleMap, useJsApiLoader, Marker } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: '100vh' };

const getMarkerIcon = (type: string) => {
  let color = '#3B82F6'; // Default blue
  if (type === 'p_prive') color = '#EF4444'; // Red
  if (type === 'p_gratuit') color = '#10B981'; // Green
  if (type === 'camping') color = '#F59E0B'; // Orange

  const svg = `
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 31L26 18C28 15.5 29 13 29 10C29 4.5 24.5 0 19 0H13C7.5 0 3 4.5 3 10C3 13 4 15.5 6 18L16 31Z" fill="${color}"/>
      <circle cx="16" cy="10" r="5" fill="white"/>
    </svg>
  `;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
};

const MapContainer: React.FC<any> = ({ places, onMarkerClick, center }) => {
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
  });

  if (!isLoaded) return <div className="h-full w-full flex items-center justify-center bg-gray-100 text-gray-500 font-bold">Loading Map...</div>;

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={center}
      zoom={12}
      options={{
        disableDefaultUI: true,
        zoomControl: true,
        styles: [
          {
            featureType: 'poi',
            elementType: 'labels',
            stylers: [{ visibility: 'off' }]
          }
        ]
      }}
    >
      {places.map((place: any) => (
        <Marker
          key={place.id}
          position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
          onClick={() => onMarkerClick(place)}
          icon={{
            url: getMarkerIcon(place.code_type),
            scaledSize: new google.maps.Size(32, 32),
            anchor: new google.maps.Point(16, 32)
          }}
        />
      ))}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
