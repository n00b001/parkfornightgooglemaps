import React from 'react';
import { GoogleMap, Marker } from '@react-google-maps/api';
import { Place } from '../types';

const containerStyle = { width: '100%', height: '100%' };

const getIcon = (type: string, isFavorite: boolean, isVisited: boolean) => {
  const colors: Record<string, string> = {
    cc: '#3B82F6', // Blue
    p: '#6B7280',  // Gray
    cp: '#10B981', // Green
    p_prive: '#F59E0B', // Amber
    ferme: '#8B5CF6', // Purple (changed from Red)
    nature: '#059669', // Dark Green
  };

  const color = colors[type] || '#3B82F6';

  let strokeColor = '#FFFFFF';
  let strokeWeight = 2;
  let scale = 1.8;

  if (isFavorite) {
    strokeColor = '#EF4444'; // Red for favorite
    strokeWeight = 4;
    scale = 2.2;
  } else if (isVisited) {
    strokeColor = '#10B981'; // Green for visited
    strokeWeight = 4;
    scale = 2.0;
  }

  return {
    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z',
    fillColor: color,
    fillOpacity: 1,
    strokeWeight: strokeWeight,
    strokeColor: strokeColor,
    scale: scale,
    anchor: new google.maps.Point(12, 22),
    labelOrigin: new google.maps.Point(12, 9),
  };
};

interface MapContainerProps {
  places: Place[];
  onMarkerClick: (place: Place) => void;
  center: { lat: number; lng: number };
  onCenterChange: (center: { lat: number; lng: number }) => void;
  favorites: number[];
  visited: number[];
}

const MapContainer: React.FC<MapContainerProps> = ({ places, onMarkerClick, center, onCenterChange, favorites = [], visited = [] }) => {
  const mapRef = React.useRef<google.maps.Map | null>(null);

  const handleIdle = () => {
    if (mapRef.current && onCenterChange) {
      const center = mapRef.current.getCenter();
      if (center) {
        onCenterChange({ lat: center.lat(), lng: center.lng() });
      }
    }
  };

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={center}
      zoom={12}
      onLoad={(map) => { mapRef.current = map; }}
      onIdle={handleIdle}
      options={{
        clickableIcons: false,
        disableDefaultUI: true,
        zoomControl: true,
        styles: [
          {
            featureType: "poi",
            elementType: "labels",
            stylers: [{ visibility: "off" }]
          }
        ]
      }}
    >
      {places.map((place: any) => {
        const isFavorite = favorites.includes(place.id);
        const isVisited = visited.includes(place.id);

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
      )})}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
