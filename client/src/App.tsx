import React, { useState, useEffect } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces } from './services/db';
import { Heart, List, Map as MapIcon, LocateFixed, User as UserIcon } from 'lucide-react';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import ListView from './components/ListView';
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

  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [mapCenter, setMapCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [lastFetchedCenter, setLastFetchedCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<Filters>({});
  const [favorites, setFavorites] = useState<number[]>([]);
  const [visited, setVisited] = useState<number[]>([]);
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

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
    <div className="relative h-screen w-screen overflow-hidden bg-gray-100">
      {isLoadingPlaces && (
        <div className="absolute inset-0 z-[100] flex items-center justify-center bg-white/40 backdrop-blur-sm transition-all duration-500">
          <div className="flex flex-col items-center gap-4 bg-white p-8 rounded-3xl shadow-2xl border border-gray-100">
            <div className="relative w-16 h-16">
              <div className="absolute inset-0 border-4 border-blue-100 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
            </div>
            <div className="text-center">
              <h3 className="text-lg font-bold text-gray-900">Finding Spots</h3>
              <p className="text-sm text-gray-500">Exploring nearby parking...</p>
            </div>
          </div>
        </div>
      )}

      {/* Top Header */}
      <div className="absolute top-0 inset-x-0 z-20 p-4 flex gap-2">
        <div className="flex-1">
          <SearchBar onSearch={(coords: any) => { setMapCenter(coords); setLastFetchedCenter(coords); }} onOpenFilters={() => setIsFilterOpen(true)} />
        </div>
        {!user ? (
          <a href={loginUrl} className="bg-white p-3 rounded-full shadow-lg hover:bg-gray-50 transition-colors border border-gray-100 flex items-center justify-center">
            <UserIcon size={20} className="text-gray-600" />
          </a>
        ) : (
          <button className="bg-white p-1 rounded-full shadow-lg border-2 border-blue-500 overflow-hidden w-11 h-11">
             <img src={user.avatar} alt={user.name} className="w-full h-full object-cover" />
          </button>
        )}
      </div>

      {/* Floating Action Buttons */}
      <div className="absolute top-20 right-4 z-10 flex flex-col gap-3">
        <button
          onClick={handleMyLocation}
          className="p-3 bg-white text-gray-600 rounded-full shadow-lg hover:bg-gray-50 transition-colors border border-gray-50"
          title="My Location"
        >
          <LocateFixed size={20} />
        </button>
        <button
          onClick={() => setViewMode(viewMode === 'map' ? 'list' : 'map')}
          className="p-3 bg-white text-gray-600 rounded-full shadow-lg hover:bg-gray-50 transition-colors border border-gray-50"
          title={viewMode === 'map' ? 'List View' : 'Map View'}
        >
          {viewMode === 'map' ? <List size={20} /> : <MapIcon size={20} />}
        </button>
        {user && (
          <button
            onClick={() => setShowOnlyFavorites(!showOnlyFavorites)}
            className={`p-3 rounded-full shadow-lg transition-all border border-gray-50 ${showOnlyFavorites ? 'bg-red-500 text-white border-red-400' : 'bg-white text-gray-600'}`}
            title={showOnlyFavorites ? "Show All" : "Show Favorites"}
          >
            <Heart size={20} fill={showOnlyFavorites ? 'white' : 'none'} />
          </button>
        )}
      </div>

      {isLoaded ? (
        <>
          <div className={`h-full w-full transition-opacity duration-300 ${viewMode === 'map' ? 'opacity-100' : 'opacity-0 pointer-events-none absolute'}`}>
            <MapContainer
              places={displayPlaces}
              center={mapCenter}
              onMarkerClick={setSelectedPlace}
              onCenterChange={handleCenterChange}
              favorites={favorites}
              visited={visited}
            />
          </div>
          <div className={`h-full w-full transition-opacity duration-300 ${viewMode === 'list' ? 'opacity-100' : 'opacity-0 pointer-events-none absolute'}`}>
            <ListView
              places={displayPlaces}
              onPlaceClick={setSelectedPlace}
              favorites={favorites}
            />
          </div>
        </>
      ) : (
        <div className="flex items-center justify-center h-full bg-gray-50">
           <div className="text-center">
             <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
             <p className="text-gray-500 font-medium">Initializing Maps...</p>
           </div>
        </div>
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
    </div>
  );
};

export default App;
