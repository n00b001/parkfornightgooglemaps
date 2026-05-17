import React from 'react';
import { GoogleMap, useJsApiLoader, Marker } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: 'calc(100vh - 64px)' };

<<<<<<< HEAD
const MapContainer: React.FC<any> = ({ places, onMarkerClick, center, onBoundsChange }) => {
=======
const MapContainer: React.FC<any> = ({ places, onMarkerClick, center }) => {
>>>>>>> main
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
  });

<<<<<<< HEAD
  const mapRef = React.useRef<google.maps.Map | null>(null);

  const handleDragEnd = () => {
    if (mapRef.current) {
      const newCenter = mapRef.current.getCenter();
      if (newCenter) {
        onBoundsChange({ lat: newCenter.lat(), lng: newCenter.lng() });
      }
    }
  };

  if (!isLoaded) return <div>Loading...</div>;

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={center}
      zoom={10}
      onLoad={(map) => { mapRef.current = map; }}
      onDragEnd={handleDragEnd}
    >
      {places.map((place: any) => {
        const isCamping = place.code_type?.includes('camping');
        const isPrivate = place.code_type?.includes('prive');

        return (
          <Marker
            key={place.id}
            position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
            onClick={() => onMarkerClick(place)}
            icon={{
              url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(`
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="16" cy="16" r="14" fill="${isCamping ? '#10b981' : isPrivate ? '#ef4444' : '#3b82f6'}" stroke="white" stroke-width="2"/>
                  <path d="M16 8L10 20H22L16 8Z" fill="white" />
                </svg>
              `)}`,
              scaledSize: new google.maps.Size(32, 32)
            }}
          />
        );
      })}
=======
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
>>>>>>> main
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
