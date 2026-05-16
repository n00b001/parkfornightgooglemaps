import React, { useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import axios from 'axios';

interface SearchBarProps {
  onSearch: (search: string) => void;
  onLocationSelect: (lat: number, lng: number) => void;
  onOpenFilters: () => void;
}

const SearchBar: React.FC<SearchBarProps> = ({ onSearch, onLocationSelect, onOpenFilters }) => {
  const [query, setQuery] = useState('');

  const handleLocationSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query) return;

    try {
      // Use Google Geocoding API if available, or just search by name
      const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
      if (apiKey) {
        const res = await axios.get(`https://maps.googleapis.com/maps/api/geocode/json`, {
          params: { address: query, key: apiKey }
        });
        if (res.data.results?.[0]) {
          const { lat, lng } = res.data.results[0].geometry.location;
          onLocationSelect(lat, lng);
        }
      }
      onSearch(query);
    } catch (err) {
      console.error('Geocoding error:', err);
      onSearch(query);
    }
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <form onSubmit={handleLocationSearch} className="flex items-center bg-white rounded-full shadow-lg overflow-hidden border border-gray-200">
        <div className="pl-4 text-gray-400">
          <Search size={20} />
        </div>
        <input
          className="w-full py-3 px-3 outline-none text-gray-700 bg-transparent"
          placeholder="Search locations or parking..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="button"
          onClick={onOpenFilters}
          className="pr-4 text-gray-500 hover:text-blue-600 transition-colors"
        >
          <SlidersHorizontal size={20} />
        </button>
      </form>
    </div>
  );
};

export default SearchBar;
