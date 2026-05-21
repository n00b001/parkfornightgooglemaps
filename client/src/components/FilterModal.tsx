import React, { useState } from 'react';
import { X } from 'lucide-react';

const FilterModal: React.FC<any> = ({ isOpen, onClose, onApply }) => {
  const [type, setType] = useState('');
  const [minRating, setMinRating] = useState('');
  const [sortBy, setSortBy] = useState('rating');

  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-3xl w-full max-w-md p-6 shadow-2xl border border-gray-100">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-gray-900">Filters & Sort</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-400" title="Close">
            <X size={24} />
          </button>
        </div>
        <div className="space-y-6 mb-8">
          <div>
            <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Spot Type</label>
            <select className="w-full p-3 bg-gray-50 border border-gray-100 rounded-2xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-sm font-medium" value={type} onChange={e => setType(e.target.value)}>
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
            <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Minimum Rating</label>
            <div className="flex gap-2">
               {[0, 1, 2, 3, 4].map(r => (
                 <button
                   key={r}
                   onClick={() => setMinRating(r.toString())}
                   className={`flex-1 py-3 rounded-2xl font-bold text-sm transition-all border ${minRating === r.toString() ? 'bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-200' : 'bg-gray-50 border-gray-50 text-gray-500 hover:bg-gray-100'}`}
                 >
                   {r}+
                 </button>
               ))}
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Sort By</label>
            <div className="flex gap-2">
              <button
                onClick={() => setSortBy('rating')}
                className={`flex-1 py-3 rounded-2xl font-bold text-sm transition-all border ${sortBy === 'rating' ? 'bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-200' : 'bg-gray-50 border-gray-50 text-gray-500 hover:bg-gray-100'}`}
              >
                Best Rated
              </button>
              <button
                onClick={() => setSortBy('distance')}
                className={`flex-1 py-3 rounded-2xl font-bold text-sm transition-all border ${sortBy === 'distance' ? 'bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-200' : 'bg-gray-50 border-gray-50 text-gray-500 hover:bg-gray-100'}`}
              >
                Nearest
              </button>
            </div>
          </div>
        </div>
        <button
          onClick={() => { onApply({ type, minRating, sortBy }); onClose(); }}
          className="w-full bg-gray-900 text-white py-4 rounded-2xl font-bold hover:bg-black transition-all active:scale-[0.98] shadow-xl"
        >
          Apply Filters
        </button>
      </div>
    </div>
  );
};

export default FilterModal;
