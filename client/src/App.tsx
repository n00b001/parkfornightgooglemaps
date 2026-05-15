import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
import { savePlaces, getAllPlaces, searchPlacesOffline } from './services/db';

const API_URL = import.meta.env.VITE_API_URL || '';
axios.defaults.baseURL = API_URL;
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
    queryKey: ['places', mapCenter, filters, isOffline],
    queryFn: async () => {
      if (isOffline) {
        if (filters.search) {
          return await searchPlacesOffline(filters.search);
        }
        return await getAllPlaces();
      }
      try {
        const res = await axios.get('/api/places', {
          params: { lat: mapCenter.lat, lng: mapCenter.lng, ...filters }
        });
        await savePlaces(res.data);
        return res.data;
      } catch (err) {
        console.error('Fetch failed, falling back to offline data', err);
        return await getAllPlaces();
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
      window.location.href = `${API_URL}/auth/google`;
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
      {isOffline && (
        <div className="absolute top-0 left-0 right-0 z-50 bg-yellow-500 text-white text-center py-1 text-xs font-bold">
          Offline Mode - Showing cached data
        </div>
      )}
      <SearchBar
        onSearch={(search: string) => {
          setFilters({ ...filters, search });
          refetch();
        }}
        onOpenFilters={() => setIsFilterOpen(true)}
      />
      <MapContainer places={places} center={mapCenter} onMarkerClick={setSelectedPlace} />
      <FilterModal isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} onApply={(f: any) => {
        setFilters({ ...filters, ...f });
        setIsFilterOpen(false);
      }} />
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
          <a href={`${API_URL}/auth/google`} className="bg-white px-4 py-2 rounded-full shadow-md font-bold text-sm">Sign In</a>
        </div>
      )}
      {user && (
        <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
           <img src={user.avatar} alt={user.name} className="w-10 h-10 rounded-full border-2 border-white shadow-md" />
        </div>
      )}
    </div>
  );
};

export default App;
