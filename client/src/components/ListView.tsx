import React from 'react';
import { Star, MapPin } from 'lucide-react';
import { Place } from '../types';

interface ListViewProps {
  places: Place[];
  onPlaceClick: (place: Place) => void;
  favorites: number[];
}

const ListView: React.FC<ListViewProps> = ({ places, onPlaceClick, favorites }) => {
  return (
    <div className="h-full overflow-y-auto bg-gray-50 pb-20 pt-20 px-4">
      <div className="max-w-2xl mx-auto space-y-4">
        {places.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-500">
            <p className="text-lg font-medium">No spots found in this area</p>
            <p className="text-sm">Try moving the map or changing filters</p>
          </div>
        ) : (
          places.map((place) => (
            <div
              key={place.id}
              onClick={() => onPlaceClick(place)}
              className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="w-32 h-32 flex-shrink-0 bg-gray-200">
                {place.photos && place.photos.length > 0 ? (
                  <img
                    src={place.photos[0].lien_mini}
                    alt={place.titre}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-400">
                    <MapPin size={24} />
                  </div>
                )}
              </div>
              <div className="p-4 flex-1 min-w-0">
                <div className="flex justify-between items-start">
                  <h3 className="font-bold text-lg truncate pr-2">{place.titre || place.name}</h3>
                  {favorites.includes(place.id) && (
                    <div className="bg-red-50 text-red-500 p-1 rounded-md">
                      <Star size={14} fill="currentColor" />
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 mt-1">
                  <Star size={14} className="text-orange-500" fill="currentColor" />
                  <span className="text-sm font-bold">{place.note_moyenne || 'N/A'}</span>
                  <span className="text-gray-400 text-xs">({place.nb_comm || 0})</span>
                  <span className="mx-1 text-gray-300">•</span>
                  <span className="text-xs text-gray-500 uppercase font-semibold">
                    {place.code_type === 'cc' ? 'Motorhome' :
                     place.code_type === 'p' ? 'Parking' :
                     place.code_type === 'cp' ? 'Campsite' :
                     place.code_type === 'p_prive' ? 'Private' :
                     place.code_type === 'ferme' ? 'Farm' :
                     place.code_type === 'nature' ? 'Nature' : 'Other'}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-2 truncate">{place.adresse}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ListView;
