import React, { useState } from 'react';
import { X } from 'lucide-react';

const FilterModal: React.FC<any> = ({ isOpen, onClose, onApply }) => {
  const [type, setType] = useState('');
  const [minRating, setMinRating] = useState('');
  const [sortBy, setSortBy] = useState('rating');

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
              <option value="cc">Motorhome Area</option>
              <option value="p">Parking</option>
              <option value="cp">Campsite</option>
              <option value="p_prive">Private Parking</option>
              <option value="ferme">Farm</option>
              <option value="nature">Nature Spot</option>
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
        </div>
        <button onClick={() => onApply({ type, minRating, sortBy })} className="w-full bg-blue-600 text-white py-3 rounded-xl font-bold">Apply</button>
      </div>
    </div>
  );
};

export default FilterModal;
