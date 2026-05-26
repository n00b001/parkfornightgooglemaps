import React from 'react';
import { Star, MapPin, Heart, Navigation } from 'lucide-react';
import { getPhotoThumbUrl } from '../services/images';

// English type keys (must match server TYPE_CODE_MAP values)
const TYPE_NAMES: Record<string, string> = {
  rvPark: 'RV Park',
  parking: 'Parking',
  naturalParking: 'Natural Parking',
  campsite: 'Campsite',
  freeRvPark: 'Free RV Park',
  restArea: 'Rest Area',
  onSiteParking: 'On-Site Parking',
  serviceArea: 'Service Area',
  private: 'Private',
  paid: 'Paid',
  closed: 'Closed',
};

const TYPE_COLORS: Record<string, string> = {
  rvPark: 'bg-blue-100 text-blue-700',
  parking: 'bg-gray-100 text-gray-700',
  naturalParking: 'bg-emerald-100 text-emerald-700',
  campsite: 'bg-green-100 text-green-700',
  freeRvPark: 'bg-teal-100 text-teal-700',
  restArea: 'bg-purple-100 text-purple-700',
  onSiteParking: 'bg-indigo-100 text-indigo-700',
  serviceArea: 'bg-orange-100 text-orange-700',
  private: 'bg-amber-100 text-amber-700',
  paid: 'bg-yellow-100 text-yellow-700',
  closed: 'bg-red-100 text-red-700',
};

interface ListViewProps {
  places: any[];
  onPlaceClick: (place: any) => void;
  favorites: number[];
  onToggleFavorite: (placeId: number) => void;
}

const ListView: React.FC<ListViewProps> = ({ places, onPlaceClick, favorites, onToggleFavorite }) => {
  return (
    <div className="h-[calc(100vh-64px)] overflow-y-auto bg-gray-50 pb-32 pt-4 custom-scrollbar">
      <div className="max-w-2xl mx-auto px-4 space-y-4">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-extrabold text-gray-900">{places.length} spots found</h2>
          <div className="text-xs font-bold text-gray-400 uppercase tracking-widest">Sorted by relevance</div>
        </div>
        {places.map((place) => {
          const isFavorite = favorites.includes(place.id);
          const photo = getPhotoThumbUrl(place.photos?.[0]);
          return (
            <div
              key={place.id}
              onClick={() => onPlaceClick(place)}
              className="bg-white rounded-3xl shadow-sm border border-gray-100 overflow-hidden flex cursor-pointer hover:shadow-xl hover:scale-[1.01] transition-all duration-300 group"
            >
              <div className="w-36 h-36 flex-shrink-0 bg-gray-100 overflow-hidden">
                {photo ? (
                  <img src={photo} alt={place.title || place.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-300">
                    <MapPin size={32} strokeWidth={1.5} />
                  </div>
                )}
              </div>
              <div className="flex-1 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-start">
                    <h3 className="font-bold text-gray-900 line-clamp-1">{place.title || place.name}</h3>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(place.id);
                      }}
                      className={`p-2 rounded-full transition-colors ${isFavorite ? 'bg-red-50 text-red-500' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'}`}
                    >
                      <Heart
                        size={20}
                        fill={isFavorite ? 'currentColor' : 'none'}
                        strokeWidth={2.5}
                      />
                    </button>
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <div className="flex items-center gap-1">
                      <Star size={14} fill="orange" className="text-orange-500" />
                      <span className="text-sm font-bold">{place.rating ?? '0'}</span>
                      <span className="text-xs text-gray-400">({place.reviewCount ?? 0})</span>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${TYPE_COLORS[place.type || ''] || 'bg-gray-100 text-gray-600'}`}>
                      {TYPE_NAMES[place.type || ''] || 'Spot'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2 line-clamp-1 italic">{place.address}</p>
                </div>
                <div className="flex justify-end">
                   <button
                    onClick={(e) => {
                      e.stopPropagation();
                      window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`);
                    }}
                    className="p-1.5 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors"
                    title="Directions"
                  >
                    <Navigation size={16} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
        {places.length === 0 && (
          <div className="text-center py-20 text-gray-500">
            No parking spots found in this area.
          </div>
        )}
      </div>
    </div>
  );
};

export default ListView;
