import React, { useState, useEffect } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import {
  savePlaces,
  getCachedPlaces,
  getPendingVisits,
  removePendingVisit,
  getPendingFavorites,
  removePendingFavorite,
  getPendingReviews,
  removePendingReview,
  savePendingFavorite
} from './services/db';
import { Heart, LayoutList, Map as MapIcon, LocateFixed, LogOut } from 'lucide-react';
import MapContainer from './components/MapContainer';
import ListView from './components/ListView';
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
  const [lastFetchedCenter, setLastFetchedCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<any>({});
  const [favorites, setFavorites] = useState<number[]>([]);
  const [visited, setVisited] = useState<number[]>([]);
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const handleOnline = async () => {
      setIsOnline(true);
      // Sync pending visits
      const pendingVisits = await getPendingVisits();
      for (const visit of pendingVisits) {
        try {
          await axios.post('/api/visits', { placeId: visit.placeId });
          await removePendingVisit(visit.placeId);
          setVisited(prev => [...prev, visit.placeId]);
        } catch (err) {
          console.error('Failed to sync visit', err);
        }
      }

      // Sync pending favorites
      const pendingFavs = await getPendingFavorites();
      for (const fav of pendingFavs) {
        try {
          if (fav.action === 'add') {
            await axios.post('/api/favorites', { placeId: fav.placeId });
          } else {
            await axios.delete(`/api/favorites/${fav.placeId}`);
          }
          await removePendingFavorite(fav.placeId);
        } catch (err) {
          console.error('Failed to sync favorite', err);
        }
      }

      // Sync pending reviews
      const pendingReviews = await getPendingReviews();
      for (const review of pendingReviews) {
        try {
          await axios.post('/api/reviews', {
            placeId: review.placeId,
            content: review.content,
            rating: review.rating
          });
          await removePendingReview(review.id);
        } catch (err) {
          console.error('Failed to sync review', err);
        }
      }
    };
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const { data: rawPlaces = [], isLoading: isLoadingPlaces } = useQuery({
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

  const [searchQuery, setSearchQuery] = useState('');

  const displayPlaces = React.useMemo(() => {
    let filtered = [...rawPlaces];

    // Filter by favorites toggle
    if (showOnlyFavorites) {
      filtered = filtered.filter((p: any) => favorites.includes(p.id));
    }

    // Filter by type
    if (filters.type) {
      filtered = filtered.filter((p: any) => p.code_type === filters.type);
    }

    // Filter by min rating
    if (filters.minRating) {
      filtered = filtered.filter((p: any) => (parseFloat(p.note_moyenne) || 0) >= parseFloat(filters.minRating));
    }

    // Filter by amenities
    if (filters.amenities && filters.amenities.length > 0) {
      filtered = filtered.filter((p: any) =>
        filters.amenities.every((amenity: string) => p[amenity] === '1')
      );
    }

    // Filter by search query
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter((p: any) =>
        (p.titre || '').toLowerCase().includes(q) ||
        (p.adresse || '').toLowerCase().includes(q)
      );
    }

    // Sort
    if (filters.sortBy === 'rating') {
      filtered.sort((a, b) => (parseFloat(b.note_moyenne) || 0) - (parseFloat(a.note_moyenne) || 0));
    } else if (filters.sortBy === 'distance') {
      filtered.sort((a, b) => {
        const distA = Math.sqrt(Math.pow(parseFloat(a.latitude) - mapCenter.lat, 2) + Math.pow(parseFloat(a.longitude) - mapCenter.lng, 2));
        const distB = Math.sqrt(Math.pow(parseFloat(b.latitude) - mapCenter.lat, 2) + Math.pow(parseFloat(b.longitude) - mapCenter.lng, 2));
        return distA - distB;
      });
    }

    return filtered;
  }, [rawPlaces, showOnlyFavorites, favorites, filters, searchQuery, mapCenter]);

  useGpsTracking(rawPlaces, !!user, visited);

  // Default map center to user's location on mount
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          setMapCenter(coords);
          setLastFetchedCenter(coords);
        },
        () => {
          // Geolocation denied or unavailable — keep Paris default
        }
      );
    }
  }, []);

  useEffect(() => {
    axios.get('/auth/me').then(res => {
      setUser(res.data);
      if (res.data) {
        axios.get('/api/favorites').then(fRes => setFavorites(fRes.data.map((f: any) => f.placeId)));
        axios.get('/api/visits').then(vRes => setVisited(vRes.data.map((v: any) => v.placeId)));
      }
    }).catch(() => setUser(null));
  }, []);

  const handleCenterChange = (newCenter: { lat: number, lng: number }) => {
    setMapCenter(newCenter);
    // Only trigger fetch if moved significantly (e.g., > 10km) or first time
    const dist = Math.sqrt(Math.pow(newCenter.lat - lastFetchedCenter.lat, 2) + Math.pow(newCenter.lng - lastFetchedCenter.lng, 2));
    if (dist > 0.1) { // roughly 10-11km
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

    const isCurrentlyFavorite = favorites.includes(placeId);

    if (isCurrentlyFavorite) {
      setFavorites(favorites.filter(id => id !== placeId));
      try {
        await axios.delete(`/api/favorites/${placeId}`);
      } catch (err) {
        if (!navigator.onLine) {
          await savePendingFavorite(placeId, 'remove');
        }
      }
    } else {
      setFavorites([...favorites, placeId]);
      try {
        await axios.post('/api/favorites', { placeId });
      } catch (err) {
        if (!navigator.onLine) {
          await savePendingFavorite(placeId, 'add');
        }
      }
    }
  };

  const handleLogout = async () => {
    try {
      await axios.get('/auth/logout');
      setUser(null);
      setFavorites([]);
      setVisited([]);
    } catch (err) {
      console.error('Logout failed', err);
    }
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

        <SearchBar
          onSearch={(coords: any) => { setMapCenter(coords); setLastFetchedCenter(coords); }}
          onOpenFilters={() => setIsFilterOpen(true)}
          onQueryChange={setSearchQuery}
        />

        <div className="flex items-center gap-2">
          {!isOnline && (
            <div className="px-3 py-1 bg-amber-100 text-amber-700 text-xs font-bold rounded-full animate-pulse">
              Offline
            </div>
          )}
          {user ? (
            <div className="flex items-center gap-2">
              <img src={user.avatar} alt={user.name} className="w-8 h-8 rounded-full border" />
              <button
                onClick={() => setShowOnlyFavorites(!showOnlyFavorites)}
                className={`p-2 rounded-lg transition-colors ${showOnlyFavorites ? 'bg-red-50 text-red-500' : 'bg-gray-100 text-gray-600'}`}
                title={showOnlyFavorites ? "Show All" : "Show Favorites"}
              >
                <Heart size={20} fill={showOnlyFavorites ? 'currentColor' : 'none'} />
              </button>
              <button
                onClick={handleLogout}
                className="p-2 text-gray-600 hover:text-red-600 transition-colors"
                title="Sign Out"
              >
                <LogOut size={20} />
              </button>
            </div>
          ) : (
            <a href={loginUrl} className="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold text-sm hover:bg-blue-700 transition-colors">Sign In</a>
          )}
        </div>
      </header>

      <main className="flex-1 relative overflow-hidden">
        <div className="absolute top-4 right-4 z-10 flex flex-col gap-2">
          <button
            onClick={handleMyLocation}
            className="p-3 bg-white text-gray-600 rounded-full shadow-lg hover:bg-gray-50 transition-colors border"
            title="My Location"
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
                {viewMode === 'map' ? (
                  <><LayoutList size={20} /> List View</>
                ) : (
                  <><MapIcon size={20} /> Map View</>
                )}
              </button>
            </div>

            {/* Subtle loading indicator - does not block user interaction */}
            {isLoadingPlaces && (
              <div className="absolute top-4 left-4 z-10 flex items-center gap-2 bg-white/90 backdrop-blur-sm px-3 py-2 rounded-full shadow-sm border">
                <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs font-medium text-gray-600">Loading spots...</span>
              </div>
            )}
          </>
        ) : (
          <div className="absolute inset-0 bg-white flex flex-col items-center justify-center">
            <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="mt-4 text-gray-600 font-medium">Loading Park4Night...</p>
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
