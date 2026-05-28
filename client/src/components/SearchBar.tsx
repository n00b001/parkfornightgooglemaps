import React, { useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

const SearchBar: React.FC<any> = ({ onSearch, onOpenFilters, onQueryChange }) => {
  const [query, setQuery] = useState('');

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query || !window.google) return;

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
      <form onSubmit={handleSearch} className="flex items-center bg-gray-100 rounded-full overflow-hidden border border-gray-200 h-12">
        <div className="pl-4 text-gray-400"><Search size={18} /></div>
        <input
          className="w-full py-2 px-4 outline-none text-sm bg-transparent h-full"
          placeholder="Search for a location..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            onQueryChange(e.target.value);
          }}
        />
        <button type="button" onClick={onOpenFilters} className="pr-4 text-gray-500 hover:text-blue-600 transition-colors">
          <SlidersHorizontal size={18} />
        </button>
      </form>
    </div>
  );
};

export default SearchBar;
