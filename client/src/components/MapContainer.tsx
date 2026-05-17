import React from 'react';
import { GoogleMap, Marker } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: 'calc(100vh - 64px)' };

const getIcon = (type: string) => {
  const colors: Record<string, string> = {
    cc: '#3B82F6', // Blue
    p: '#6B7280',  // Gray
    cp: '#10B981', // Green
    p_prive: '#F59E0B', // Amber
    ferme: '#EF4444', // Red
    nature: '#059669', // Dark Green
  };

  const labels: Record<string, string> = {
    cc: 'A',
    p: 'P',
    cp: 'C',
    p_prive: 'Pr',
    ferme: 'F',
    nature: 'N',
  };

  const color = colors[type] || '#3B82F6';

  return {
    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z',
    fillColor: color,
    fillOpacity: 1,
    strokeWeight: 2,
    strokeColor: '#FFFFFF',
    scale: 1.8,
    anchor: new google.maps.Point(12, 22),
    labelOrigin: new google.maps.Point(12, 9),
  };
};

const MapContainer: React.FC<any> = ({ places, onMarkerClick, center }) => {
  return (
    <GoogleMap mapContainerStyle={containerStyle} center={center} zoom={10}>
      {places.map((place: any) => (
        <Marker
          key={place.id}
          position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
          onClick={() => onMarkerClick(place)}
          icon={getIcon(place.code_type)}
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
      ))}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
