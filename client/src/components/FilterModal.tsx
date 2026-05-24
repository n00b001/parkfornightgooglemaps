import React, { useState } from 'react';
import { X } from 'lucide-react';

const AMENITY_FILTERS = [
  { key: 'point_eau', label: 'Water' },
  { key: 'electricite', label: 'Electricity' },
  { key: 'poubelle', label: 'Trash' },
  { key: 'wifi', label: 'Wifi' },
  { key: 'vidange_eaux_usees', label: 'Grey Water' },
  { key: 'vidange_wc', label: 'Black Water' },
  { key: 'douche', label: 'Shower' },
  { key: 'baignade', label: 'Waves' },
];

const FilterModal: React.FC<any> = ({ isOpen, onClose, onApply, initialFilters = {} }) => {
  const [filters, setFilters] = useState(initialFilters);

  if (!isOpen) return null;

  const handleAmenityToggle = (key: string) => {
    setFilters((prev: any) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl w-full max-w-md p-8 shadow-2xl animate-in fade-in zoom-in duration-200">
        <div className="flex justify-between items-center mb-8">
          <h2 className="text-2xl font-black tracking-tight text-gray-900">Filters & Sort</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <X size={24} />
          </button>
        </div>

        <div className="space-y-6 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
          <div>
            <label className="block text-xs font-black uppercase tracking-wider text-gray-400 mb-2">Spot Type</label>
            <select
              className="w-full p-3 bg-gray-50 border border-gray-100 rounded-2xl font-bold focus:ring-2 focus:ring-blue-500 outline-none transition-all appearance-none"
              value={filters.type || ''}
              onChange={e => setFilters({...filters, type: e.target.value})}
            >
              <option value="">All Types</option>
              <option value="cc">Motorhome Area</option>
              <option value="p">Parking</option>
              <option value="cp">Campsite</option>
              <option value="p_prive">Private Parking</option>
              <option value="ferme">Farm</option>
              <option value="nature">Nature Spot</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-black uppercase tracking-wider text-gray-400 mb-3">Amenities</label>
            <div className="grid grid-cols-2 gap-2">
              {AMENITY_FILTERS.map(amenity => (
                <button
                  key={amenity.key}
                  onClick={() => handleAmenityToggle(amenity.key)}
                  className={`flex items-center justify-center p-3 rounded-2xl text-xs font-bold border transition-all ${
                    filters[amenity.key]
                      ? 'bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-100'
                      : 'bg-gray-50 border-gray-100 text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  {amenity.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-black uppercase tracking-wider text-gray-400 mb-2">Min Rating</label>
              <input
                type="number"
                min="0" max="5" step="0.5"
                className="w-full p-3 bg-gray-50 border border-gray-100 rounded-2xl font-bold focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                value={filters.minRating || ''}
                onChange={e => setFilters({...filters, minRating: e.target.value})}
                placeholder="0.0"
              />
            </div>
            <div>
              <label className="block text-xs font-black uppercase tracking-wider text-gray-400 mb-2">Sort By</label>
              <select
                className="w-full p-3 bg-gray-50 border border-gray-100 rounded-2xl font-bold focus:ring-2 focus:ring-blue-500 outline-none transition-all appearance-none"
                value={filters.sortBy || 'rating'}
                onChange={e => setFilters({...filters, sortBy: e.target.value})}
              >
                <option value="rating">Highest Rated</option>
                <option value="distance">Nearest First</option>
              </select>
            </div>
          </div>
        </div>

        <div className="mt-8 flex gap-3">
          <button
            onClick={() => { setFilters({}); onApply({}); }}
            className="flex-1 py-4 bg-gray-100 text-gray-600 rounded-2xl font-bold hover:bg-gray-200 transition-all"
          >
            Reset
          </button>
          <button
            onClick={() => onApply(filters)}
            className="flex-[2] py-4 bg-blue-600 text-white rounded-2xl font-bold hover:bg-blue-700 shadow-xl shadow-blue-200 transition-all active:scale-95"
          >
            Show Results
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterModal;
