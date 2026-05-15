import React, { useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

const SearchBar: React.FC<any> = ({ onSearch, onOpenFilters }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(query);
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <form onSubmit={handleSubmit} className="flex items-center bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
        <div className="pl-4 text-gray-400"><Search size={20} /></div>
        <input
          className="w-full py-4 px-3 outline-none text-gray-700 placeholder-gray-400 font-medium"
          placeholder="Search locations..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="flex items-center pr-2">
          <button
            type="button"
            onClick={onOpenFilters}
            className="p-2 hover:bg-gray-50 rounded-xl transition-colors text-gray-500"
          >
            <SlidersHorizontal size={20} />
          </button>
        </div>
      </form>
    </div>
  );
};

export default SearchBar;
