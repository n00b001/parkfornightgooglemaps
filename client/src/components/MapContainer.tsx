import React from 'react';
import { GoogleMap, Marker } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: 'calc(100vh - 64px)' };

const getIcon = (type: string, isFavorite: boolean, isVisited: boolean) => {
  const colors: Record<string, string> = {
    cc: '#3B82F6', // Blue
    p: '#6B7280',  // Gray
    cp: '#10B981', // Green
    p_prive: '#F59E0B', // Amber
    ferme: '#EF4444', // Red
    nature: '#059669', // Dark Green
  };

  let color = colors[type] || '#3B82F6';
  if (isFavorite) color = '#EC4899'; // Pink for favorites

  return {
    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z',
    fillColor: color,
    fillOpacity: 1,
    strokeWeight: isVisited ? 4 : 2,
    strokeColor: isVisited ? '#10B981' : '#FFFFFF', // Green border for visited
    scale: isFavorite ? 1.8 : 1.5,
    anchor: new google.maps.Point(12, 22),
  };
};

const MapContainer: React.FC<any> = ({ places, onMarkerClick, center, favorites = [], visits = [] }) => {
  return (
    <GoogleMap mapContainerStyle={containerStyle} center={center} zoom={10}>
      {places.map((place: any) => (
        <Marker
          key={place.id}
          position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
          onClick={() => onMarkerClick(place)}
          icon={getIcon(place.code_type, favorites.includes(place.id), visits.includes(place.id))}
        />
      ))}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
