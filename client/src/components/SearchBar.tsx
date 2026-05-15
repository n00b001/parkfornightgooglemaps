import React from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

const SearchBar: React.FC<any> = ({ onSearch, onOpenFilters }) => {
  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <div className="flex items-center bg-white rounded-full shadow-lg overflow-hidden">
        <div className="pl-4"><Search size={20} /></div>
        <input className="w-full py-3 px-3 outline-none" placeholder="Search..." />
        <button onClick={onOpenFilters} className="pr-4"><SlidersHorizontal size={20} /></button>
      </div>
    </div>
  );
};

export default SearchBar;
