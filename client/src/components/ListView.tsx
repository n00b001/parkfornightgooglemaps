import React from 'react';
import { Star, MapPin, Heart, Navigation } from 'lucide-react';

const TYPE_NAMES: Record<string, string> = {
  cc: 'Motorhome Area',
  p: 'Parking',
  cp: 'Campsite',
  p_prive: 'Private Parking',
  ferme: 'Farm',
  nature: 'Nature Spot',
};

const TYPE_COLORS: Record<string, string> = {
  cc: 'bg-blue-100 text-blue-700',
  p: 'bg-gray-100 text-gray-700',
  cp: 'bg-green-100 text-green-700',
  p_prive: 'bg-amber-100 text-amber-700',
  ferme: 'bg-red-100 text-red-700',
  nature: 'bg-emerald-100 text-emerald-700',
};

interface ListViewProps {
  places: any[];
  onPlaceClick: (place: any) => void;
  favorites: number[];
  onToggleFavorite: (placeId: number) => void;
}

const ListView: React.FC<ListViewProps> = ({ places, onPlaceClick, favorites, onToggleFavorite }) => {
  return (
    <div className="h-[calc(100vh-64px)] overflow-y-auto bg-gray-50 pb-28 pt-4">
      <div className="max-w-2xl mx-auto p-4 space-y-4">
        {places.map((place) => {
          const isFavorite = favorites.includes(place.id);
          const photo = place.photos?.[0]?.lien_mini;

          return (
            <div
              key={place.id}
              onClick={() => onPlaceClick(place)}
              className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="w-32 h-32 flex-shrink-0 bg-gray-200">
                {photo ? (
                  <img src={photo} alt={place.titre || place.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-400">
                    <MapPin size={24} />
                  </div>
                )}
              </div>
              <div className="flex-1 p-4 flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-start">
                    <h3 className="font-bold text-gray-900 line-clamp-1">{place.titre || place.name}</h3>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(place.id);
                      }}
                      className="p-1 focus:outline-none"
                    >
                      <Heart
                        size={20}
                        className={isFavorite ? 'text-red-500 fill-red-500' : 'text-gray-400'}
                      />
                    </button>
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <div className="flex items-center gap-1">
                      <Star size={14} fill="orange" className="text-orange-500" />
                      <span className="text-sm font-bold">{place.note_moyenne || '0'}</span>
                      <span className="text-xs text-gray-400">({place.nb_comm || 0})</span>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${TYPE_COLORS[place.code_type || ''] || 'bg-gray-100 text-gray-600'}`}>
                      {TYPE_NAMES[place.code_type || ''] || 'Spot'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2 line-clamp-1 italic">{place.adresse}</p>
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
