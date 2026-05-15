import React, { useState } from 'react';
import { Search, Filter, SlidersHorizontal } from 'lucide-react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  onOpenFilters: () => void;
}

const SearchBar: React.FC<SearchBarProps> = ({ onSearch, onOpenFilters }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(query);
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <form onSubmit={handleSubmit} className="relative flex items-center bg-white rounded-full shadow-lg overflow-hidden">
        <div className="pl-4">
          <Search className="text-gray-400" size={20} />
        </div>
        <input
          type="text"
          className="w-full py-3 px-3 outline-none text-gray-700"
          placeholder="Search locations..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="button"
          onClick={onOpenFilters}
          className="pr-4 text-gray-500 hover:text-gray-800 transition-colors"
        >
          <SlidersHorizontal size={20} />
        </button>
      </form>
    </div>
  );
};

export default SearchBar;
