import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import MapContainer from './components/MapContainer';
import SearchBar from './components/SearchBar';
import FilterModal from './components/FilterModal';
import PlaceDetails from './components/PlaceDetails';
import { useGpsTracking } from './hooks/useGpsTracking';
<<<<<<< HEAD
import { savePlaces, getCachedPlaces } from './services/db';
=======
>>>>>>> main

const App: React.FC = () => {
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
  const [mapCenter, setMapCenter] = useState({ lat: 48.8566, lng: 2.3522 });
  const [filters, setFilters] = useState<any>({});
  const [favorites, setFavorites] = useState<number[]>([]);

<<<<<<< HEAD
  const [searchTerm, setSearchTerm] = useState('');

  const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '',
    withCredentials: true
  });

  const { data: places = [], refetch } = useQuery({
    queryKey: ['places', mapCenter, filters, searchTerm],
    queryFn: async () => {
      try {
        const res = await api.get('/api/places', {
          params: {
            lat: mapCenter.lat,
            lng: mapCenter.lng,
            search: searchTerm,
            ...filters
          }
        });
        if (res.data && Array.isArray(res.data)) {
          savePlaces(res.data);
        }
        return res.data;
      } catch (err) {
        console.warn('Fetch failed, loading from cache', err);
        return getCachedPlaces();
      }
=======
  const { data: places = [], refetch } = useQuery({
    queryKey: ['places', mapCenter, filters],
    queryFn: async () => {
      const res = await axios.get('/api/places', { params: { lat: mapCenter.lat, lng: mapCenter.lng, ...filters } });
      return res.data;
>>>>>>> main
    }
  });

  useGpsTracking(places, !!user);

  useEffect(() => {
<<<<<<< HEAD
    api.get('/auth/me').then(res => {
      setUser(res.data);
      if (res.data) {
        api.get('/api/favorites').then(fRes => setFavorites(fRes.data.map((f: any) => f.placeId)));
=======
    axios.get('/auth/me').then(res => {
      setUser(res.data);
      if (res.data) {
        axios.get('/api/favorites').then(fRes => setFavorites(fRes.data.map((f: any) => f.placeId)));
>>>>>>> main
      }
    }).catch(() => setUser(null));
  }, []);

  const handleToggleFavorite = async (placeId: number) => {
    if (!user) {
<<<<<<< HEAD
      window.location.href = (import.meta.env.VITE_API_URL || '') + '/auth/google';
      return;
    }
    if (favorites.includes(placeId)) {
      await api.delete(`/api/favorites/${placeId}`);
      setFavorites(favorites.filter(id => id !== placeId));
    } else {
      await api.post('/api/favorites', { placeId });
=======
      window.location.href = '/auth/google';
      return;
    }
    if (favorites.includes(placeId)) {
      await axios.delete(`/api/favorites/${placeId}`);
      setFavorites(favorites.filter(id => id !== placeId));
    } else {
      await axios.post('/api/favorites', { placeId });
>>>>>>> main
      setFavorites([...favorites, placeId]);
    }
  };

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-gray-100">
<<<<<<< HEAD
      <SearchBar
        onSearch={(val: string) => setSearchTerm(val)}
        onOpenFilters={() => setIsFilterOpen(true)}
      />
      <MapContainer
        places={places}
        center={mapCenter}
        onMarkerClick={setSelectedPlace}
        onBoundsChange={(c: any) => setMapCenter(c)}
      />
=======
      <SearchBar onSearch={() => refetch()} onOpenFilters={() => setIsFilterOpen(true)} />
      <MapContainer places={places} center={mapCenter} onMarkerClick={setSelectedPlace} />
>>>>>>> main
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
          <a href="/auth/google" className="bg-white px-4 py-2 rounded-full shadow-md font-bold text-sm">Sign In</a>
        </div>
      )}
    </div>
  );
};

export default App;
