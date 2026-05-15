import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
import { addToGoogleMaps } from './utils/googleMaps';
import { savePlacesToOffline, getOfflinePlaces } from './services/offlineDb';

const App: React.FC = () => {
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<any>(null);
  const [favorites, setFavorites] = useState<number[]>([]);
  const [user, setUser] = useState<any>(null);
  const [mapCenter, setMapCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<any>({});

  const { data: places = [], isLoading, refetch } = useQuery({
    queryKey: ['places', mapCenter, filters],
    queryFn: async () => {
      try {
        const params = {
          lat: mapCenter.lat,
          lng: mapCenter.lng,
          ...filters
        };
        const res = await axios.get('/api/places', { params });
        const data = res.data;
        await savePlacesToOffline(data);
        return data;
      } catch (err) {
        console.log('Fetching offline data...');
        return await getOfflinePlaces();
      }
    }
  });

  useGpsTracking(places, !!user);

  useEffect(() => {
    axios.get('/auth/me').then(res => setUser(res.data)).catch(() => setUser(null));

    // Get user location on start
    navigator.geolocation.getCurrentPosition(
      (pos) => setMapCenter({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => console.error(err)
    );
  }, []);

  const handleToggleFavorite = async (placeId: number) => {
    if (!user) {
      window.location.href = '/auth/google';
      return;
    }

    if (favorites.includes(placeId)) {
      await axios.delete(`/api/favorites/${placeId}`);
      setFavorites(favorites.filter(id => id !== placeId));
    } else {
      await axios.post('/api/favorites', { placeId });
      setFavorites([...favorites, placeId]);
    }
  };

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-gray-100">
      <SearchBar
        onSearch={(query) => {
          // In a real app, use Geocoding API to get lat/lng from query
          console.log('Searching for:', query);
          refetch();
        }}
        onOpenFilters={() => setIsFilterOpen(true)}
      />

      <MapContainer
        places={places}
        center={mapCenter}
        onMarkerClick={(place) => setSelectedPlace(place)}
      />

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        onApply={(newFilters) => {
          setFilters(newFilters);
          setIsFilterOpen(false);
        }}
      />

      {selectedPlace && (
        <PlaceDetails
          place={selectedPlace}
          isFavorite={favorites.includes(selectedPlace.id)}
          isAuthenticated={!!user}
          onClose={() => setSelectedPlace(null)}
          onToggleFavorite={handleToggleFavorite}
          onAddToGoogleMaps={addToGoogleMaps}
        />
      )}

      {!user && (
        <div className="absolute top-4 right-4 z-10">
          <a
            href="/auth/google"
            className="bg-white px-4 py-2 rounded-full shadow-md font-semibold text-sm hover:bg-gray-50 transition-colors"
          >
            Sign in with Google
          </a>
        </div>
      )}
    </div>
  );
};

export default App;
