import React, { useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

const SearchBar: React.FC<any> = ({ onSearch, onOpenFilters }) => {
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
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <form onSubmit={handleSearch} className="flex items-center bg-white rounded-full shadow-lg overflow-hidden border border-gray-100">
        <div className="pl-4 text-gray-400"><Search size={20} /></div>
        <input
          className="w-full py-4 px-3 outline-none text-sm"
          placeholder="Search for a location..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="button" onClick={onOpenFilters} className="pr-4 text-gray-500 hover:text-blue-600 transition-colors">
          <SlidersHorizontal size={20} />
        </button>
      </form>
    </div>
  );
};

export default SearchBar;
