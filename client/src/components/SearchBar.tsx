import React from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

const SearchBar: React.FC<any> = ({ onSearch, onOpenFilters }) => {
<<<<<<< HEAD
  const [value, setValue] = React.useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(value);
  };

  return (
    <form onSubmit={handleSubmit} className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <div className="flex items-center bg-white rounded-full shadow-lg overflow-hidden border border-gray-100 focus-within:border-blue-400 transition-colors">
        <div className="pl-4 text-gray-400"><Search size={20} /></div>
        <input
          className="w-full py-3 px-3 outline-none text-gray-700 placeholder-gray-400"
          placeholder="Search by name or address..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="button" onClick={onOpenFilters} className="pr-4 text-gray-500 hover:text-blue-600 transition-colors">
          <SlidersHorizontal size={20} />
        </button>
      </div>
    </form>
=======
  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-md px-4">
      <div className="flex items-center bg-white rounded-full shadow-lg overflow-hidden">
        <div className="pl-4"><Search size={20} /></div>
        <input className="w-full py-3 px-3 outline-none" placeholder="Search..." />
        <button onClick={onOpenFilters} className="pr-4"><SlidersHorizontal size={20} /></button>
      </div>
    </div>
>>>>>>> main
  );
};

export default SearchBar;
