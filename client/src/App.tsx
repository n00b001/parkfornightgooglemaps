import React, { useState, useEffect } from 'react';
import axios from './axiosConfig';
import { useQuery } from '@tanstack/react-query';
import { savePlaces, getCachedPlaces } from './services/db';
import { Heart } from 'lucide-react';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import { useJsApiLoader } from '@react-google-maps/api';

type Library = "places" | "drawing" | "geometry" | "visualization";
const LIBRARIES: Library[] = ['places'];
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';

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
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false);

  const { data: places = [] } = useQuery({
    queryKey: ['places', mapCenter, filters.type, filters.minRating],
    queryFn: async () => {
      try {
        const { type, minRating } = filters;
        const res = await axios.get('/api/places', { params: { lat: mapCenter.lat, lng: mapCenter.lng, type, minRating } });
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
      }
    }).catch(() => setUser(null));
  }, []);

  const calculateDistance = (lat1: number, lon1: number, lat2: number, lon2: number) => {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  };

  const displayPlaces = [...(showOnlyFavorites
    ? places.filter((p: any) => favorites.includes(p.id))
    : places)].sort((a: any, b: any) => {
      if (filters.sortBy === 'rating') {
        return (parseFloat(b.note_moyenne) || 0) - (parseFloat(a.note_moyenne) || 0);
      } else if (filters.sortBy === 'distance') {
        const distA = calculateDistance(mapCenter.lat, mapCenter.lng, parseFloat(a.latitude), parseFloat(a.longitude));
        const distB = calculateDistance(mapCenter.lat, mapCenter.lng, parseFloat(b.latitude), parseFloat(b.longitude));
        return distA - distB;
      }
      return 0;
    });

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
      <SearchBar isLoaded={isLoaded} onSearch={(coords: any) => setMapCenter(coords)} onOpenFilters={() => setIsFilterOpen(true)} />

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

      <MapContainer isLoaded={isLoaded} places={displayPlaces} center={mapCenter} onMarkerClick={setSelectedPlace} />
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
        <div className="absolute top-20 right-4 z-10 md:top-4">
          <a href={loginUrl} className="bg-white px-4 py-2 rounded-full shadow-lg font-bold text-sm border border-gray-100 transition-transform active:scale-95">Sign In</a>
        </div>
      )}
    </div>
  );
};

export default App;
