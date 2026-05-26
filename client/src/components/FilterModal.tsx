import React, { useState } from 'react';
import { X, Droplets, Zap, Trash2, Wifi, Bath, Waves, Dog, Utensils, Shirt, Info, Compass, Map } from 'lucide-react';

const AMENITIES_OPTIONS = [
  { key: 'waterPoint', label: 'Water', icon: Droplets },
  { key: 'electricity', label: 'Electricity', icon: Zap },
  { key: 'trashCan', label: 'Trash', icon: Trash2 },
  { key: 'wifi', label: 'Wifi', icon: Wifi },
  { key: 'wasteWaterDrain', label: 'Grey Water', icon: Info },
  { key: 'toiletDrain', label: 'Black Water', icon: Compass },
  { key: 'shower', label: 'Shower', icon: Bath },
  { key: 'swimming', label: 'Water Activity', icon: Waves },
  { key: 'pets', label: 'Pets', icon: Dog },
  { key: 'picnicArea', label: 'Picnic', icon: Utensils },
  { key: 'laundry', label: 'Laundry', icon: Shirt },
  { key: 'publicToilet', label: 'Public WC', icon: Map },
];

const FilterModal: React.FC<any> = ({ isOpen, onClose, onApply }) => {
  const [type, setType] = useState('');
  const [minRating, setMinRating] = useState('');
  const [sortBy, setSortBy] = useState('rating');
  const [amenities, setAmenities] = useState<string[]>([]);

  const toggleAmenity = (key: string) => {
    setAmenities(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md p-6">
        <div className="flex justify-between mb-4">
          <h2 className="text-xl font-bold">Filters & Sort</h2>
          <button onClick={onClose}><X size={24} /></button>
        </div>
        <div className="space-y-4 mb-6">
          <div>
            <label className="block text-sm font-bold mb-1">Type</label>
            <select className="w-full p-2 border rounded-lg" value={type} onChange={e => setType(e.target.value)}>
              <option value="">All Types</option>
              <option value="rvPark">RV Park</option>
              <option value="parking">Parking</option>
              <option value="campsite">Campsite</option>
              <option value="private">Private</option>
              <option value="closed">Closed</option>
              <option value="naturalParking">Natural Parking</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-bold mb-1">Min Rating</label>
            <input type="number" min="0" max="5" step="0.5" className="w-full p-2 border rounded-lg" value={minRating} onChange={e => setMinRating(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-bold mb-1">Sort By</label>
            <select className="w-full p-2 border rounded-lg" value={sortBy} onChange={e => setSortBy(e.target.value)}>
              <option value="rating">Rating (Highest First)</option>
              <option value="distance">Distance (Nearest First)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-bold mb-2">Amenities</label>
            <div className="grid grid-cols-2 gap-2">
              {AMENITIES_OPTIONS.map(opt => (
                <button
                  key={opt.key}
                  onClick={() => toggleAmenity(opt.key)}
                  className={`flex items-center gap-2 p-2 rounded-lg border text-sm transition-colors ${
                    amenities.includes(opt.key)
                      ? 'bg-blue-50 border-blue-200 text-blue-700'
                      : 'bg-white border-gray-100 text-gray-600'
                  }`}
                >
                  <opt.icon size={16} />
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <button
          onClick={() => {
            onApply({ type, minRating, sortBy, amenities });
            onClose();
          }}
          className="w-full bg-blue-600 text-white py-3 rounded-xl font-bold shadow-lg shadow-blue-200"
        >
          Apply Filters
        </button>
      </div>
    </div>
  );
};

export default FilterModal;
