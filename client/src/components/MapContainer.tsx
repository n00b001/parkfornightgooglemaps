import React from 'react';
import { GoogleMap, Marker, MarkerClusterer } from '@react-google-maps/api';

const containerStyle = { width: '100%', height: '100%' };

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

const MapContainer: React.FC<any> = ({ places, onMarkerClick, center, onCenterChange, favorites = [], visited = [] }) => {
  const mapRef = React.useRef<google.maps.Map | null>(null);
  const [mapReady, setMapReady] = React.useState(false);
  const [mapError, setMapError] = React.useState<string | null>(null);

  const checkMapUsable = (map: google.maps.Map) => {
    // When Google Maps API quota is exceeded, getBounds() returns undefined
    // Check after a short delay to allow the map to fully initialize
    setTimeout(() => {
      try {
        const bounds = map.getBounds();
        if (bounds && bounds.getNorthEast() && bounds.getSouthWest()) {
          setMapReady(true);
          setMapError(null);
        } else {
          setMapError('Map failed to load. This is likely due to Google Maps API quota being exceeded. Please use a valid API key with billing enabled.');
        }
      } catch {
        setMapError('Map failed to initialize. Check your Google Maps API key configuration.');
      }
    }, 1000);
  };

  const handleLoad = (map: google.maps.Map) => {
    mapRef.current = map;
    checkMapUsable(map);
  };

  const handleIdle = () => {
    if (mapRef.current && onCenterChange && mapReady) {
      try {
        const mapCenter = mapRef.current.getCenter();
        if (mapCenter) {
          onCenterChange({ lat: mapCenter.lat(), lng: mapCenter.lng() });
        }
      } catch {
        // Map bounds not available (quota exceeded or other API issue)
      }
    }
  };

  if (mapError) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-gray-50 p-8">
        <div className="max-w-md text-center">
          <div className="bg-red-100 text-red-600 p-4 rounded-lg mb-4">
            <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <h3 className="font-bold text-lg">Map Unavailable</h3>
          </div>
          <p className="text-gray-600 mb-4">{mapError}</p>
          <p className="text-sm text-gray-500">
            Check the browser console for details. The Google Maps API key may need to be configured in Render dashboard under <code className="bg-gray-200 px-1 rounded">VITE_GOOGLE_MAPS_API_KEY</code>.
          </p>
        </div>
      </div>
    );
  }

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={center}
      zoom={10}
      onLoad={handleLoad}
      onIdle={handleIdle}
      options={{
        fullscreenControl: false,
        streetViewControl: false,
        mapTypeControl: false,
        zoomControlOptions: { position: google.maps.ControlPosition.RIGHT_CENTER }
      }}
    >
      {mapReady && (
        <MarkerClusterer options={{
          imagePath: '/m',
        }}>
          {(clusterer) => (
            <>
              {places.map((place: any) => {
                const isFavorite = favorites.includes(place.id);
                const isVisited = visited.includes(place.id);

                return (
                  <Marker
                    key={place.id}
                    position={{ lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) }}
                    onClick={() => onMarkerClick(place)}
                    icon={getIcon(place.type || place.code_type, isFavorite, isVisited)}
                    clusterer={clusterer}
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
                )
              })}
            </>
          )}
        </MarkerClusterer>
      )}
    </GoogleMap>
  );
};

export default React.memo(MapContainer);
