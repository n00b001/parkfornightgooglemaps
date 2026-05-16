import React, { useState } from 'react';
import { X, Filter, ArrowUpDown } from 'lucide-react';

interface FilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: any) => void;
}

const FilterModal: React.FC<FilterModalProps> = ({ isOpen, onClose, onApply }) => {
  const [type, setType] = useState('');
  const [minRating, setMinRating] = useState('');
  const [sortBy, setSortBy] = useState('');

  if (!isOpen) return null;

  const handleApply = () => {
    onApply({ type, minRating, sortBy });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl w-full max-w-md p-8 shadow-2xl animate-in fade-in zoom-in duration-200">
        <div className="flex justify-between items-center mb-8">
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Filter size={24} className="text-blue-600" /> Filters & Sort
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <X size={24} />
          </button>
        </div>

        <div className="space-y-6 mb-8">
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">Parking Type</label>
            <select
              className="w-full p-3 border border-gray-200 rounded-xl bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="">All Types</option>
              <option value="p_prive">Private Parking</option>
              <option value="p_gratuit">Free Parking</option>
              <option value="camping">Campsite</option>
              <option value="aire_prive">Private Area</option>
              <option value="ferme">Farm</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">Minimum Rating</label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min="0"
                max="5"
                step="0.5"
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                value={minRating || 0}
                onChange={(e) => setMinRating(e.target.value)}
              />
              <span className="font-bold text-blue-600 w-8">{minRating || 0}</span>
            </div>
          </div>

          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2 flex items-center gap-1">
              <ArrowUpDown size={16} /> Sort By
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                className={`py-2 px-4 rounded-xl border font-medium transition-all ${sortBy === 'rating' ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-gray-200 text-gray-600'}`}
                onClick={() => setSortBy(sortBy === 'rating' ? '' : 'rating')}
              >
                Highest Rated
              </button>
              {/* Distance sorting could be added here if implemented in backend */}
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => { setType(''); setMinRating(''); setSortBy(''); }}
            className="flex-1 py-3 px-4 border border-gray-200 rounded-xl font-bold text-gray-500 hover:bg-gray-50 transition-all"
          >
            Reset
          </button>
          <button
            onClick={handleApply}
            className="flex-[2] bg-blue-600 text-white py-3 px-4 rounded-xl font-bold shadow-lg shadow-blue-200 hover:bg-blue-700 active:scale-[0.98] transition-all"
          >
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterModal;
