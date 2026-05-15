import React, { useState } from 'react';
import { X } from 'lucide-react';

interface FilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: any) => void;
}

const PLACE_TYPES = [
  { id: 'p_prive', name: 'Private Parking' },
  { id: 'p_gratuit', name: 'Free Parking' },
  { id: 'camping', name: 'Campsite' },
  { id: 'aire_prive', name: 'Private Area' },
  { id: 'ferme', name: 'Farm' }
];

const FilterModal: React.FC<FilterModalProps> = ({ isOpen, onClose, onApply }) => {
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [minRating, setMinRating] = useState<number | null>(null);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/50">
      <div className="bg-white w-full max-w-lg rounded-t-2xl sm:rounded-2xl shadow-xl overflow-hidden animate-in slide-in-from-bottom duration-300">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-xl font-bold">Filters</h2>
          <button onClick={onClose} className="p-1 rounded-full hover:bg-gray-100">
            <X size={24} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <h3 className="font-semibold mb-3">Place Type</h3>
            <div className="flex flex-wrap gap-2">
              {PLACE_TYPES.map(type => (
                <button
                  key={type.id}
                  onClick={() => setSelectedType(selectedType === type.id ? null : type.id)}
                  className={`px-4 py-2 border rounded-full text-sm transition-colors ${
                    selectedType === type.id
                    ? 'bg-blue-600 border-blue-600 text-white'
                    : 'hover:bg-blue-50 hover:border-blue-500'
                  }`}
                >
                  {type.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <h3 className="font-semibold mb-3">Minimum Rating</h3>
            <div className="flex space-x-2">
              {[3, 4, 4.5].map(rating => (
                <button
                  key={rating}
                  onClick={() => setMinRating(minRating === rating ? null : rating)}
                  className={`px-4 py-2 border rounded-full text-sm transition-colors ${
                    minRating === rating
                    ? 'bg-yellow-400 border-yellow-400 text-white'
                    : 'hover:bg-yellow-50 hover:border-yellow-500'
                  }`}
                >
                  {rating}+ ⭐
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="p-4 border-t flex space-x-3">
          <button
            onClick={() => onApply({ type: selectedType, minRating })}
            className="flex-1 py-3 bg-blue-600 text-white font-bold rounded-xl hover:bg-blue-700 transition-colors"
          >
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterModal;
