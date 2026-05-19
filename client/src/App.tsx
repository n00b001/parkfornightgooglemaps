import React, { useState, useEffect } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces } from './services/db';
import { syncOfflineData } from './services/syncService';
import { Heart } from 'lucide-react';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
import { useJsApiLoader } from '@react-google-maps/api';

const LIBRARIES: ("places" | "drawing" | "geometry" | "visualization")[] = ['places'];

const App: React.FC = () => {
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries: LIBRARIES
  });

  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
  const [mapCenter, setMapCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<any>({});
  const [favorites, setFavorites] = useState<number[]>([]);
  const [visits, setVisits] = useState<number[]>([]);
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

  const { data: places = [], isLoading: isLoadingPlaces } = useQuery({
    queryKey: ['places', mapCenter, filters],
    queryFn: async () => {
      try {
        const res = await axios.get('/api/places', { params: { lat: mapCenter.lat, lng: mapCenter.lng, ...filters } });
        await savePlaces(res.data);
        return res.data;
      } catch (err) {
        console.warn('Network request failed, loading from cache');
        return await getCachedPlaces();
      }
    }
  });

  useGpsTracking(places, !!user);

  useEffect(() => {
    const initApp = async () => {
      try {
        const res = await axios.get('/auth/me');
        setUser(res.data);
        if (res.data) {
          const [favRes, visitRes] = await Promise.all([
            axios.get('/api/favorites'),
            axios.get('/api/visits')
          ]);
          setFavorites(favRes.data.map((f: any) => f.placeId));
          setVisits(visitRes.data.map((v: any) => v.placeId));

          // Sync offline data when user is authenticated and app loads
          await syncOfflineData();
        }
      } catch (err) {
        setUser(null);
      }
    };
    initApp();
  }, []);

  // Listen for online event to trigger sync
  useEffect(() => {
    window.addEventListener('online', syncOfflineData);
    return () => window.removeEventListener('online', syncOfflineData);
  }, []);

  const displayPlaces = showOnlyFavorites
    ? places.filter((p: any) => favorites.includes(p.id))
    : places;

  const handleToggleFavorite = async (placeId: number) => {
    if (!user) {
      const returnTo = window.location.origin;
      window.location.href = `${import.meta.env.VITE_API_URL}/auth/google?returnTo=${encodeURIComponent(returnTo)}`;
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

  const loginUrl = `${import.meta.env.VITE_API_URL}/auth/google?returnTo=${encodeURIComponent(window.location.origin)}`;

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-gray-100">
      <SearchBar onSearch={(coords: any) => setMapCenter(coords)} onOpenFilters={() => setIsFilterOpen(true)} />

      {user && (
        <div className="absolute top-20 right-4 z-10 flex flex-col gap-2">
          <button
            onClick={() => setShowOnlyFavorites(!showOnlyFavorites)}
            className={`p-3 rounded-full shadow-lg transition-all active:scale-95 ${showOnlyFavorites ? 'bg-red-500 text-white' : 'bg-white text-gray-600'}`}
          >
            <Heart size={20} fill={showOnlyFavorites ? 'white' : 'none'} />
          </button>
        </div>
      )}

      {isLoaded ? (
        <>
          <MapContainer
            places={displayPlaces}
            center={mapCenter}
            onMarkerClick={setSelectedPlace}
            favorites={favorites}
            visits={visits}
          />
          {isLoadingPlaces && (
            <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10 bg-white/90 px-4 py-2 rounded-full shadow-lg flex items-center gap-2 backdrop-blur-sm border border-white/20">
              <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm font-medium">Fetching parking spots...</span>
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-full gap-4">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-500 font-medium">Loading Google Maps...</p>
        </div>
      )}

      <FilterModal isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} onApply={setFilters} />

      {selectedPlace && (
        <PlaceDetails
          place={selectedPlace}
          isAuthenticated={!!user}
          isVisited={visits.includes(selectedPlace.id)}
          onClose={() => setSelectedPlace(null)}
          onToggleFavorite={() => handleToggleFavorite(selectedPlace.id)}
          isFavorite={favorites.includes(selectedPlace.id)}
        />
      )}

      {!user && (
        <div className="absolute top-4 right-4 z-10">
          <a href={loginUrl} className="bg-white px-6 py-3 rounded-full shadow-lg font-bold text-sm text-blue-600 hover:bg-blue-50 transition-colors border border-gray-100">
            Sign In
          </a>
        </div>
      )}
    </div>
  );
};

export default App;
