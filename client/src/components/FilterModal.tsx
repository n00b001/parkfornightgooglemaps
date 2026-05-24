import React, { useState } from 'react';
import { X, Droplets, Zap, Trash2, Wifi, Info, Bath, Waves } from 'lucide-react';
import { Filters } from '../types';

interface FilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: Filters) => void;
}

const AMENITIES = [
  { key: 'point_eau', label: 'Water', icon: Droplets, color: 'text-blue-500' },
  { key: 'electricite', label: 'Electricity', icon: Zap, color: 'text-yellow-500' },
  { key: 'poubelle', label: 'Trash', icon: Trash2, color: 'text-green-600' },
  { key: 'wifi', label: 'Wifi', icon: Wifi, color: 'text-purple-500' },
  { key: 'vidange_eaux_usees', label: 'Grey Water', icon: Info, color: 'text-gray-500' },
  { key: 'vidange_wc', label: 'Black Water', icon: Info, color: 'text-gray-700' },
  { key: 'douche', label: 'Shower', icon: Bath, color: 'text-blue-400' },
  { key: 'baignade', label: 'Waves', icon: Waves, color: 'text-cyan-500' },
];

const FilterModal: React.FC<FilterModalProps> = ({ isOpen, onClose, onApply }) => {
  const [type, setType] = useState('');
  const [minRating, setMinRating] = useState('');
  const [sortBy, setSortBy] = useState('rating');
  const [selectedAmenities, setSelectedAmenities] = useState<Record<string, boolean>>({});

  if (!isOpen) return null;

  const handleToggleAmenity = (key: string) => {
    setSelectedAmenities(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleApply = () => {
    onApply({
      type,
      minRating,
      sortBy,
      ...selectedAmenities
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl w-full max-w-md p-6 shadow-2xl animate-in fade-in zoom-in duration-200">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Filters & Sort</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors"><X size={24} /></button>
        </div>

        <div className="space-y-6 max-h-[60vh] overflow-y-auto pr-2">
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">Spot Type</label>
            <select className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all" value={type} onChange={e => setType(e.target.value)}>
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
            <label className="block text-sm font-bold text-gray-700 mb-2">Amenities</label>
            <div className="grid grid-cols-4 gap-3">
              {AMENITIES.map(amenity => (
                <button
                  key={amenity.key}
                  onClick={() => handleToggleAmenity(amenity.key)}
                  className={`flex flex-col items-center p-3 rounded-xl border transition-all ${
                    selectedAmenities[amenity.key] ? 'bg-blue-50 border-blue-200 ring-2 ring-blue-500' : 'bg-gray-50 border-gray-100 hover:border-gray-300'
                  }`}
                >
                  <amenity.icon size={20} className={selectedAmenities[amenity.key] ? amenity.color : 'text-gray-400'} />
                  <span className={`text-[10px] mt-1 font-bold text-center ${selectedAmenities[amenity.key] ? 'text-blue-700' : 'text-gray-500'}`}>{amenity.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">Min Rating</label>
              <input
                type="number"
                min="0" max="5" step="0.5"
                className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-blue-500"
                value={minRating}
                onChange={e => setMinRating(e.target.value)}
                placeholder="0-5"
              />
            </div>
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">Sort By</label>
              <select className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-blue-500" value={sortBy} onChange={e => setSortBy(e.target.value)}>
                <option value="rating">Top Rated</option>
                <option value="distance">Nearest</option>
              </select>
            </div>
          </div>
        </div>

        <button
          onClick={handleApply}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-bold mt-8 shadow-lg shadow-blue-200 transition-all active:scale-[0.98]"
        >
          Apply Filters
        </button>
      </div>
    </div>
  );
};

export default FilterModal;
