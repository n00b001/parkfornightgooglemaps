import React, { useState, useEffect } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces } from './services/db';
import { Heart, List, Map as MapIcon } from 'lucide-react';
import MapContainer from './components/MapContainer';
import ListView from './components/ListView';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
import { useJsApiLoader } from '@react-google-maps/api';
import { LocateFixed } from 'lucide-react';

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

  const { data: places = [], isLoading: isLoadingPlaces } = useQuery({
    queryKey: ['places', lastFetchedCenter, filters],
    queryFn: async () => {
      try {
        const res = await axios.get('/api/places', { params: { lat: lastFetchedCenter.lat, lng: lastFetchedCenter.lng, ...filters } });
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

  const displayPlaces = showOnlyFavorites
    ? places.filter((p: any) => favorites.includes(p.id))
    : places;

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
      <SearchBar onSearch={(coords: any) => { setMapCenter(coords); setLastFetchedCenter(coords); }} onOpenFilters={() => setIsFilterOpen(true)} />

      <div className="absolute top-20 right-4 z-10 flex flex-col gap-2">
        <button
          onClick={() => setViewMode(viewMode === 'map' ? 'list' : 'map')}
          className="p-3 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition-colors"
          title={viewMode === 'map' ? "Show List" : "Show Map"}
        >
          {viewMode === 'map' ? <List size={20} /> : <MapIcon size={20} />}
        </button>
        <button
          onClick={handleMyLocation}
          className="p-3 bg-white text-gray-600 rounded-full shadow-lg hover:bg-gray-50 transition-colors"
          title="My Location"
        >
          <LocateFixed size={20} />
        </button>
        {user && (
          <button
            onClick={() => setShowOnlyFavorites(!showOnlyFavorites)}
            className={`p-3 rounded-full shadow-lg transition-colors ${showOnlyFavorites ? 'bg-red-500 text-white' : 'bg-white text-gray-600'}`}
            title={showOnlyFavorites ? "Show All" : "Show Favorites"}
          >
            <Heart size={20} fill={showOnlyFavorites ? 'white' : 'none'} />
          </button>
        )}
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
            />
          )}
          {isLoadingPlaces && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/10 backdrop-blur-[2px]">
              <div className="bg-white px-6 py-4 rounded-3xl shadow-2xl flex flex-col items-center gap-3">
                <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
                <span className="font-bold text-gray-700">Finding best spots...</span>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="flex items-center justify-center h-full">Loading Maps...</div>
      )}
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
      {!user && (
        <div className="absolute top-4 right-4 z-10">
          <a href={loginUrl} className="bg-white px-4 py-2 rounded-full shadow-md font-bold text-sm">Sign In</a>
        </div>
      )}
    </div>
  );
};

export default App;
