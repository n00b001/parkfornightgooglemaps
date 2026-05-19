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

  const color = colors[type] || '#3B82F6';

  // Use stroke color to indicate status: red for favorite, green for visited
  let strokeColor = '#FFFFFF';
  let strokeWeight = 2;

  if (isFavorite) {
    strokeColor = '#EF4444'; // Red
    strokeWeight = 4;
  } else if (isVisited) {
    strokeColor = '#10B981'; // Green
    strokeWeight = 4;
  }

  return {
    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z',
    fillColor: color,
    fillOpacity: 1,
    strokeWeight: strokeWeight,
    strokeColor: strokeColor,
    scale: 1.8,
    anchor: typeof google !== 'undefined' ? new google.maps.Point(12, 22) : undefined,
    labelOrigin: typeof google !== 'undefined' ? new google.maps.Point(12, 9) : undefined,
  };
};

interface MapContainerProps {
  places: any[];
  center: { lat: number; lng: number };
  onMarkerClick: (place: any) => void;
  favorites: number[];
  visits: number[];
}

const MapContainer: React.FC<MapContainerProps> = ({ places, onMarkerClick, center, favorites = [], visits = [] }) => {
  return (
    <GoogleMap mapContainerStyle={containerStyle} center={center} zoom={10}>
      {places.map((place: any) => {
        const isFavorite = favorites.includes(place.id);
        const isVisited = visits.includes(place.id);

        return (
          <Marker
            key={place.id}
            position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
            onClick={() => onMarkerClick(place)}
            icon={getIcon(place.code_type, isFavorite, isVisited)}
            label={{
              text: (place.code_type === 'cc' ? 'A' :
                     place.code_type === 'p' ? 'P' :
                     place.code_type === 'cp' ? 'C' :
                     place.code_type === 'p_prive' ? 'Pr' :
                     place.code_type === 'ferme' ? 'F' :
                     place.code_type === 'nature' ? 'N' : '?'),
              color: 'white',
              fontSize: '10px',
              fontWeight: 'bold'
            }}
          />
        );
      })}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
