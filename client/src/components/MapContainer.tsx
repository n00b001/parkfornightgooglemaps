import React, { useState, useCallback, useRef } from 'react';
import { GoogleMap, useJsApiLoader, Marker, InfoWindow } from '@react-google-maps/api';

const containerStyle = {
  width: '100%',
  height: 'calc(100vh - 64px)'
};

const defaultCenter = {
  lat: 48.8566,
  lng: 2.3522
};

interface MapProps {
  places: any[];
  onMarkerClick: (place: any) => void;
  center?: { lat: number; lng: number };
}

const MapContainer: React.FC<MapProps> = ({ places, onMarkerClick, center }) => {
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY
  });

  const [map, setMap] = useState<google.maps.Map | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<any>(null);

  const onLoad = useCallback(function callback(map: google.maps.Map) {
    setMap(map);
  }, []);

  const onUnmount = useCallback(function callback(map: google.maps.Map) {
    setMap(null);
  }, []);

  if (!isLoaded) return <div>Loading...</div>;

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={center || defaultCenter}
      zoom={10}
      onLoad={onLoad}
      onUnmount={onUnmount}
      options={{
        clickableIcons: false,
        streetViewControl: false,
        mapTypeControl: false,
        fullscreenControl: false
      }}
    >
      {places.map((place) => (
        <Marker
          key={place.id}
          position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
          onClick={() => {
            setSelectedPlace(place);
            onMarkerClick(place);
          }}
          icon={{
            url: `/markers/${place.code_type}.png`, // Placeholder icon path
            scaledSize: new google.maps.Size(30, 30)
          }}
        />
      ))}

      {selectedPlace && (
        <InfoWindow
          position={{ lat: parseFloat(selectedPlace.latitude), lng: parseFloat(selectedPlace.longitude) }}
          onCloseClick={() => setSelectedPlace(null)}
        >
          <div className="p-2">
            <h3 className="font-bold">{selectedPlace.titre}</h3>
            <p className="text-sm">{selectedPlace.adresse}</p>
          </div>
        </InfoWindow>
      )}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
