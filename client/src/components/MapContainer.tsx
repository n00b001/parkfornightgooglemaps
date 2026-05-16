import React from 'react';
import { GoogleMap, useJsApiLoader, Marker } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: '100vh' };

const getMarkerIcon = (type: string): google.maps.Symbol => {
  let color = '#3B82F6'; // Default blue
  if (type === 'camping') color = '#10B981'; // Green
  if (type === 'p_prive' || type === 'aire_prive') color = '#F59E0B'; // Amber
  if (type === 'p_gratuit') color = '#6366F1'; // Indigo

  return {
    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z',
    fillColor: color,
    fillOpacity: 1,
    strokeWeight: 2,
    strokeColor: '#FFFFFF',
    scale: 1.5,
    anchor: new google.maps.Point(12, 22)
  };
};

interface MapContainerProps {
  places: any[];
  center: { lat: number, lng: number };
  onMarkerClick: (place: any) => void;
}

const MapContainer: React.FC<MapContainerProps> = ({ places, onMarkerClick, center }) => {
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
  });

  const mapOptions = {
    disableDefaultUI: false,
    clickableIcons: false,
    styles: [
      {
        featureType: "poi",
        elementType: "labels",
        stylers: [{ visibility: "off" }]
      }
    ]
  };

  if (!isLoaded) return <div className="h-full w-full flex items-center justify-center bg-gray-50 text-gray-400 font-medium">Loading Map...</div>;

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={center}
      zoom={12}
      options={mapOptions}
    >
      {places.map((place: any) => (
        <Marker
          key={place.id}
          position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
          onClick={() => onMarkerClick(place)}
          icon={getMarkerIcon(place.type)}
          animation={window.google.maps.Animation.DROP}
        />
      ))}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
