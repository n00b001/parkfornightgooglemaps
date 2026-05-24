import React, { useState, useEffect, useCallback } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces, getPendingVisits, clearPendingVisit } from './services/db';
import { Heart, LayoutList, Map as MapIcon, LocateFixed, LogOut } from 'lucide-react';
import MapContainer from './components/MapContainer';
import ListView from './components/ListView';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
import { useJsApiLoader } from '@react-google-maps/api';
import { Place, User, Filters } from './types';

const LIBRARIES: ("places" | "drawing" | "geometry" | "visualization")[] = ['places'];

const App: React.FC = () => {
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries: LIBRARIES
  });

  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [mapCenter, setMapCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [lastFetchedCenter, setLastFetchedCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<Filters>({});
  const [favorites, setFavorites] = useState<number[]>([]);
  const [visited, setVisited] = useState<number[]>([]);
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  const syncPendingVisits = useCallback(async () => {
    if (!navigator.onLine) return;
    const pending = await getPendingVisits();
    for (const visit of pending) {
      try {
        await axios.post('/api/visits', { placeId: visit.placeId });
        await clearPendingVisit(visit.id);
      } catch (err) {
        console.error('Failed to sync visit', err);
      }
    }
  }, []);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      syncPendingVisits();
    };
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [syncPendingVisits]);

  const { data: places = [], isLoading: isLoadingPlaces } = useQuery<Place[]>({
    queryKey: ['places', lastFetchedCenter],
    queryFn: async () => {
      try {
        const res = await axios.get('/api/places', { params: { lat: lastFetchedCenter.lat, lng: lastFetchedCenter.lng } });
        await savePlaces(res.data);
        return res.data;
      } catch (err) {
        console.warn('Network request failed, loading from cache');
        return await getCachedPlaces();
      }
    }
  });

  useGpsTracking(places, !!user, visited);

  useEffect(() => {
    axios.get('/auth/me').then(res => {
      setUser(res.data);
      if (res.data) {
        axios.get('/api/favorites').then(fRes => setFavorites(fRes.data.map((f: any) => f.placeId)));
        axios.get('/api/visits').then(vRes => setVisited(vRes.data.map((v: any) => v.placeId)));
        syncPendingVisits();
      }
    }).catch(() => setUser(null));
  }, [syncPendingVisits]);

  const displayPlaces = places
    .filter((p: Place) => {
      if (showOnlyFavorites && !favorites.includes(p.id)) return false;
      if (filters.type && (p.code_type || p.type) !== filters.type) return false;
      if (filters.minRating && p.rating < parseFloat(filters.minRating)) return false;
      if (filters.search && !p.name.toLowerCase().includes(filters.search.toLowerCase()) && !p.address?.toLowerCase().includes(filters.search.toLowerCase())) return false;

      // Filter by amenities
      const amenityKeys = ['point_eau', 'electricite', 'poubelle', 'wifi', 'vidange_eaux_usees', 'vidange_wc', 'douche', 'baignade'];
      for (const key of amenityKeys) {
        if (filters[key] && p.rawData[key] !== '1' && p[key] !== '1') return false;
      }

      return true;
    })
    .sort((a: Place, b: Place) => {
      if (filters.sortBy === 'rating') return b.rating - a.rating;
      if (filters.sortBy === 'distance') {
        const distA = Math.sqrt(Math.pow(a.latitude - mapCenter.lat, 2) + Math.pow(a.longitude - mapCenter.lng, 2));
        const distB = Math.sqrt(Math.pow(b.latitude - mapCenter.lat, 2) + Math.pow(b.longitude - mapCenter.lng, 2));
        return distA - distB;
      }
      return 0;
    });

  const handleCenterChange = (newCenter: { lat: number, lng: number }) => {
    setMapCenter(newCenter);
    const dist = Math.sqrt(Math.pow(newCenter.lat - lastFetchedCenter.lat, 2) + Math.pow(newCenter.lng - lastFetchedCenter.lng, 2));
    if (dist > 0.1) {
      setLastFetchedCenter(newCenter);
    }
  };

  const handleMyLocation = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition((pos) => {
        const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setMapCenter(coords);
        setLastFetchedCenter(coords);
      });
    }
  };

  const handleToggleFavorite = async (placeId: number) => {
    if (!user) {
      window.location.href = `${import.meta.env.VITE_API_URL}/auth/google?returnTo=${encodeURIComponent(window.location.origin)}`;
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

  const handleLogout = async () => {
    await axios.get('/auth/logout');
    setUser(null);
    setFavorites([]);
    setVisited([]);
  };

  const loginUrl = `${import.meta.env.VITE_API_URL}/auth/google?returnTo=${encodeURIComponent(window.location.origin)}`;

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-gray-100">
      <header className="h-16 bg-white border-b flex items-center px-4 justify-between z-30 gap-4">
        <div className="flex items-center gap-2">
          <div className="bg-blue-600 p-2 rounded-lg">
            <MapIcon className="text-white" size={20} />
          </div>
          <h1 className="font-bold text-lg hidden sm:block">Park4Night</h1>
        </div>

        <SearchBar onSearch={(coords) => { setMapCenter(coords); setLastFetchedCenter(coords); }} onOpenFilters={() => setIsFilterOpen(true)} />

        <div className="flex items-center gap-2">
          {!isOnline && (
            <div className="px-3 py-1 bg-amber-100 text-amber-700 text-xs font-bold rounded-full">
              Offline
            </div>
          )}
          {user ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowOnlyFavorites(!showOnlyFavorites)}
                className={`p-2 rounded-lg transition-colors ${showOnlyFavorites ? 'bg-red-50 text-red-500' : 'bg-gray-100 text-gray-600'}`}
              >
                <Heart size={20} fill={showOnlyFavorites ? 'currentColor' : 'none'} />
              </button>
              <img src={user.avatar} alt={user.name} className="w-8 h-8 rounded-full border hidden sm:block" />
              <button onClick={handleLogout} className="p-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200" title="Logout">
                <LogOut size={20} />
              </button>
            </div>
          ) : (
            <a href={loginUrl} className="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold text-sm hover:bg-blue-700">Sign In</a>
          )}
        </div>
      </header>

      <main className="flex-1 relative overflow-hidden">
        <div className="absolute top-4 right-4 z-10 flex flex-col gap-2">
          <button
            onClick={handleMyLocation}
            className="p-3 bg-white text-gray-600 rounded-full shadow-lg hover:bg-gray-50 border"
          >
            <LocateFixed size={20} />
          </button>
        </div>

        {isLoaded ? (
          <>
            {viewMode === 'map' ? (
              <MapContainer
                places={displayPlaces}
                center={mapCenter}
                onMarkerClick={setSelectedPlace}
                onCenterChange={handleCenterChange}
                favorites={favorites}
                visited={visited}
              />
            ) : (
              <ListView
                places={displayPlaces}
                onPlaceClick={setSelectedPlace}
                favorites={favorites}
                onToggleFavorite={handleToggleFavorite}
              />
            )}

            <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-20">
              <button
                onClick={() => setViewMode(viewMode === 'map' ? 'list' : 'map')}
                className="bg-gray-900 text-white px-6 py-3 rounded-full shadow-2xl flex items-center gap-2 font-bold hover:bg-black transition-colors"
              >
                {viewMode === 'map' ? <><LayoutList size={20} /> List View</> : <><MapIcon size={20} /> Map View</>}
              </button>
            </div>

            {isLoadingPlaces && (
              <div className="absolute inset-0 z-[60] bg-white/40 backdrop-blur-md flex flex-col items-center justify-center">
                <div className="relative">
                  <div className="w-16 h-16 border-4 border-blue-600/20 rounded-full" />
                  <div className="absolute top-0 left-0 w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
                </div>
                <p className="mt-4 text-gray-900 font-bold text-lg">Loading spots...</p>
              </div>
            )}
          </>
        ) : (
          <div className="absolute inset-0 bg-white flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="mt-4 text-gray-600 font-medium">Loading Google Maps...</p>
          </div>
        )}
      </main>

      <FilterModal isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} onApply={setFilters} />
      {selectedPlace && (
        <PlaceDetails
          place={selectedPlace}
          isAuthenticated={!!user}
          onClose={() => setSelectedPlace(null)}
          onToggleFavorite={() => handleToggleFavorite(selectedPlace.id)}
          isFavorite={favorites.includes(selectedPlace.id)}
        />
      )}
    </div>
  );
};

export default App;
