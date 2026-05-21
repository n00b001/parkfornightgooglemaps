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
    <form onSubmit={handleSearch} className="flex items-center bg-white rounded-full shadow-lg overflow-hidden border border-gray-100 w-full">
      <div className="pl-4 text-gray-400"><Search size={18} /></div>
      <input
        className="w-full py-3 px-3 outline-none text-sm"
        placeholder="Search location..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <button type="button" onClick={onOpenFilters} className="pr-4 text-gray-400 hover:text-blue-600 transition-colors">
        <SlidersHorizontal size={18} />
      </button>
    </form>
  );
};

export default SearchBar;
