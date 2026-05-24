import React, { useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

interface SearchBarProps {
  onSearch: (coords: { lat: number; lng: number }) => void;
  onOpenFilters: () => void;
}

const SearchBar: React.FC<SearchBarProps> = ({ onSearch, onOpenFilters }) => {
  const [query, setQuery] = useState('');

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query) return;

    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ address: query }, (results, status) => {
      if (status === 'OK' && results && results[0]) {
        const { lat, lng } = results[0].geometry.location;
        onSearch({ lat: lat(), lng: lng() });
      }
    });
  };

  return (
    <div className="flex-1 max-w-md">
      <form onSubmit={handleSearch} className="flex items-center bg-gray-100 rounded-full overflow-hidden border border-gray-200 focus-within:border-blue-400 focus-within:bg-white transition-all">
        <div className="pl-4 text-gray-400"><Search size={18} /></div>
        <input
          className="w-full py-2 px-3 outline-none text-sm bg-transparent"
          placeholder="Search for a location..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="button" onClick={onOpenFilters} className="pr-4 text-gray-500 hover:text-blue-600 transition-colors">
          <SlidersHorizontal size={18} />
        </button>
      </form>
    </div>
  );
};

export default SearchBar;
