import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
import { savePlacesToCache, getCachedPlaces } from './services/db';

// Configure axios base URL and credentials
axios.defaults.baseURL = import.meta.env.VITE_API_URL || '';
axios.defaults.withCredentials = true;

const App: React.FC = () => {
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
  const [mapCenter, setMapCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<any>({});
  const [favorites, setFavorites] = useState<number[]>([]);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const { data: places = [], refetch } = useQuery({
    queryKey: ['places', mapCenter, filters],
    queryFn: async () => {
      try {
        if (navigator.onLine) {
          const res = await axios.get('/api/places', {
            params: {
              lat: mapCenter.lat,
              lng: mapCenter.lng,
              ...filters
            }
          });
          await savePlacesToCache(res.data);
          return res.data;
        } else {
          const cached = await getCachedPlaces();
          return cached;
        }
      } catch (err) {
        console.error('Fetch error:', err);
        return await getCachedPlaces();
      }
    }
  });

  useGpsTracking(places, !!user);

  useEffect(() => {
    axios.get('/auth/me').then(res => {
      setUser(res.data);
      if (res.data) {
        axios.get('/api/favorites').then(fRes => setFavorites(fRes.data.map((f: any) => f.placeId)));
      }
    }).catch(() => setUser(null));
  }, []);

  const handleToggleFavorite = async (placeId: number) => {
    if (!user) {
      window.location.href = `${axios.defaults.baseURL}/auth/google`;
      return;
    }
    try {
      if (favorites.includes(placeId)) {
        await axios.delete(`/api/favorites/${placeId}`);
        setFavorites(favorites.filter(id => id !== placeId));
      } else {
        await axios.post('/api/favorites', { placeId });
        setFavorites([...favorites, placeId]);
      }
    } catch (err) {
      console.error('Favorite toggle failed:', err);
    }
  };

  const handleLocationSelect = (lat: number, lng: number) => {
    setMapCenter({ lat, lng });
  };

  const handleSearch = (search: string) => {
    setFilters((prev: any) => ({ ...prev, search }));
  };

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-gray-50">
      {isOffline && (
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-20 bg-amber-100 text-amber-800 px-4 py-1 rounded-full text-xs font-bold border border-amber-200 shadow-sm">
          Offline Mode - Showing Cached Data
        </div>
      )}

      <SearchBar
        onSearch={handleSearch}
        onLocationSelect={handleLocationSelect}
        onOpenFilters={() => setIsFilterOpen(true)}
      />

      <MapContainer
        places={places}
        center={mapCenter}
        onMarkerClick={setSelectedPlace}
      />

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        onApply={setFilters}
      />

      {selectedPlace && (
        <PlaceDetails
          place={selectedPlace}
          isAuthenticated={!!user}
          onClose={() => setSelectedPlace(null)}
          onToggleFavorite={() => handleToggleFavorite(selectedPlace.id)}
          isFavorite={favorites.includes(selectedPlace.id)}
        />
      )}

      {!user && (
        <div className="absolute top-4 right-4 z-10">
          <a
            href={`${axios.defaults.baseURL}/auth/google`}
            className="bg-white px-6 py-3 rounded-2xl shadow-xl font-bold text-sm text-gray-700 border border-gray-100 hover:bg-gray-50 transition-all flex items-center gap-2"
          >
            Sign In
          </a>
        </div>
      )}

      {/* User profile mini-fab if logged in */}
      {user && (
        <div className="absolute top-4 right-4 z-10">
          <div className="bg-white p-1 rounded-2xl shadow-xl border border-gray-100 flex items-center gap-3">
             <img src={user.avatar} alt={user.name} className="w-10 h-10 rounded-xl" />
             <div className="pr-4 hidden md:block">
               <div className="text-xs font-bold text-gray-900">{user.name}</div>
               <div className="text-[10px] text-gray-400">Contributor</div>
             </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
