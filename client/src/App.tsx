import React, { useState, useEffect } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces } from './services/db';
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

  const { data: places = [], refetch } = useQuery({
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
    axios.get('/auth/me').then(res => {
      setUser(res.data);
      if (res.data) {
        axios.get('/api/favorites').then(fRes => setFavorites(fRes.data.map((f: any) => f.placeId)));
        axios.get('/api/visits').then(vRes => setVisits(vRes.data.map((v: any) => v.placeId)));
      }
    }).catch(() => setUser(null));
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
            className={`p-3 rounded-full shadow-lg transition-colors \${showOnlyFavorites ? 'bg-red-500 text-white' : 'bg-white text-gray-600'}`}
          >
            <Heart size={20} fill={showOnlyFavorites ? 'white' : 'none'} />
          </button>
        </div>
      )}

      {isLoaded ? (
        <MapContainer
          places={displayPlaces}
          center={mapCenter}
          onMarkerClick={setSelectedPlace}
          favorites={favorites}
          visits={visits}
        />
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
          isVisited={visits.includes(selectedPlace.id)}
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
