import React, { useState, useEffect, useMemo } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces, getPendingVisits, deletePendingVisit } from './services/db';
import { Heart, LayoutList, Map as MapIcon, LocateFixed } from 'lucide-react';
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
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const syncPendingVisits = async () => {
      if (!navigator.onLine || !user) return;
      const pending = await getPendingVisits();
      for (const visit of pending) {
        try {
          await axios.post('/api/visits', { placeId: visit.placeId });
          await deletePendingVisit(visit.id);
        } catch (err) {
          console.error('Failed to sync pending visit', err);
        }
      }
      // Refresh visited list after sync
      const vRes = await axios.get('/api/visits');
      setVisited(vRes.data.map((v: any) => v.placeId));
    };

    const handleOnline = () => {
      setIsOnline(true);
      syncPendingVisits();
    };
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    if (isOnline) syncPendingVisits();

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [isOnline, user]);

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
      }
    }).catch(() => setUser(null));
  }, []);

  const displayPlaces = useMemo(() => {
    let filtered = showOnlyFavorites
      ? places.filter((p: Place) => favorites.includes(p.id))
      : [...places];

    if (filters.type) {
      filtered = filtered.filter(p => (p.code_type || p.type) === filters.type);
    }

    if (filters.minRating) {
      filtered = filtered.filter(p => (p.note_moyenne || p.rating || 0) >= parseFloat(filters.minRating!));
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(p =>
        (p.titre || p.name || '').toLowerCase().includes(q) ||
        (p.adresse || p.address || '').toLowerCase().includes(q)
      );
    }

    // Amenity filters
    const amenityKeys = ['point_eau', 'electricite', 'poubelle', 'wifi', 'vidange_eaux_usees', 'vidange_wc', 'douche', 'baignade'];
    amenityKeys.forEach(key => {
      if (filters[key]) {
        filtered = filtered.filter(p => p[key] === '1' || p.rawData?.[key] === '1');
      }
    });

    if (filters.sortBy === 'rating') {
      filtered.sort((a, b) => (b.note_moyenne || b.rating || 0) - (a.note_moyenne || a.rating || 0));
    } else if (filters.sortBy === 'distance') {
      filtered.sort((a, b) => {
        const distA = Math.pow(a.latitude - mapCenter.lat, 2) + Math.pow(a.longitude - mapCenter.lng, 2);
        const distB = Math.pow(b.latitude - mapCenter.lat, 2) + Math.pow(b.longitude - mapCenter.lng, 2);
        return distA - distB;
      });
    }

    return filtered;
  }, [places, showOnlyFavorites, favorites, filters, searchQuery, mapCenter]);

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
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-gray-100 font-sans">
      <header className="h-16 bg-white border-b flex items-center px-4 justify-between z-30 gap-4 shadow-sm">
        <div className="flex items-center gap-2 min-w-fit">
          <div className="bg-blue-600 p-2 rounded-xl shadow-lg shadow-blue-200">
            <MapIcon className="text-white" size={20} />
          </div>
          <h1 className="font-black text-xl tracking-tight hidden sm:block bg-gradient-to-r from-blue-600 to-blue-800 bg-clip-text text-transparent">Park4Night</h1>
        </div>

        <SearchBar
          onSearch={(coords: any) => { setMapCenter(coords); setLastFetchedCenter(coords); }}
          onOpenFilters={() => setIsFilterOpen(true)}
          onQueryChange={setSearchQuery}
        />

        <div className="flex items-center gap-3">
          {!isOnline && (
            <div className="px-3 py-1 bg-amber-100 text-amber-700 text-[10px] font-black uppercase tracking-wider rounded-full border border-amber-200">
              Offline
            </div>
          )}
          {user ? (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowOnlyFavorites(!showOnlyFavorites)}
                className={`p-2.5 rounded-xl transition-all duration-300 ${showOnlyFavorites ? 'bg-red-50 text-red-500 shadow-inner' : 'bg-gray-50 text-gray-400 hover:text-gray-600'}`}
                title={showOnlyFavorites ? "Show All" : "Show Favorites"}
              >
                <Heart size={20} fill={showOnlyFavorites ? 'currentColor' : 'none'} />
              </button>
              <img src={user.avatar} alt={user.name} className="w-9 h-9 rounded-xl border-2 border-white shadow-md" />
            </div>
          ) : (
            <a href={loginUrl} className="bg-blue-600 text-white px-5 py-2.5 rounded-xl font-bold text-sm hover:bg-blue-700 transition-all shadow-lg shadow-blue-200 active:scale-95">Sign In</a>
          )}
        </div>
      </header>

      <main className="flex-1 relative overflow-hidden">
        <div className="absolute top-4 right-4 z-10 flex flex-col gap-3">
          <button
            onClick={handleMyLocation}
            className="p-3.5 bg-white text-gray-600 rounded-2xl shadow-xl hover:bg-gray-50 transition-all border border-gray-100 active:scale-90"
            title="My Location"
          >
            <LocateFixed size={22} />
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
                className="bg-gray-900/90 backdrop-blur-md text-white px-8 py-4 rounded-3xl shadow-2xl flex items-center gap-3 font-bold hover:bg-black transition-all active:scale-95 border border-white/10"
              >
                {viewMode === 'map' ? (
                  <><LayoutList size={20} /> List View</>
                ) : (
                  <><MapIcon size={20} /> Map View</>
                )}
              </button>
            </div>

            {isLoadingPlaces && (
              <div className="absolute inset-0 z-[60] bg-white/40 backdrop-blur-xl flex flex-col items-center justify-center transition-all duration-500">
                <div className="relative">
                  <div className="w-20 h-20 border-4 border-blue-600/10 rounded-full" />
                  <div className="absolute top-0 left-0 w-20 h-20 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
                </div>
                <p className="mt-6 text-gray-900 font-black text-xl tracking-tight animate-pulse">Finding the best spots...</p>
              </div>
            )}
          </>
        ) : (
          <div className="absolute inset-0 bg-white flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="mt-4 text-gray-600 font-bold">Loading Park4Night...</p>
          </div>
        )}
      </main>

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        onApply={(f: Filters) => { setFilters(f); setIsFilterOpen(false); }}
        initialFilters={filters}
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
    </div>
  );
};

export default App;
