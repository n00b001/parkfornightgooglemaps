import React from 'react';
import { Star, MapPin, Navigation, Info } from 'lucide-react';

interface ListViewProps {
  places: any[];
  onPlaceClick: (place: any) => void;
  favorites: number[];
}

const ListView: React.FC<ListViewProps> = ({ places, onPlaceClick, favorites }) => {
  return (
    <div className="h-full overflow-y-auto bg-gray-50 p-4 pt-20 pb-24">
      <div className="max-w-2xl mx-auto space-y-4">
        {places.map((place) => (
          <div
            key={place.id}
            onClick={() => onPlaceClick(place)}
            className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 flex gap-4 cursor-pointer hover:shadow-md transition-shadow active:scale-[0.98]"
          >
            <div className="w-24 h-24 rounded-xl bg-gray-100 flex-shrink-0 overflow-hidden">
              {place.photos?.[0]?.lien_mini ? (
                <img src={place.photos[0].lien_mini} alt={place.titre || place.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-gray-300">
                  <MapPin size={32} />
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-start">
                <h3 className="font-bold text-lg truncate">{place.titre || place.name}</h3>
                {favorites.includes(place.id) && (
                  <span className="text-red-500 text-xs font-bold bg-red-50 px-2 py-1 rounded-full">Favorite</span>
                )}
              </div>
              <div className="flex items-center gap-1 mt-1 text-sm">
                <Star size={14} fill="orange" className="text-orange-500" />
                <span className="font-bold">{place.note_moyenne || place.rating || 'N/A'}</span>
                <span className="text-gray-400">({place.nb_comm || 0} reviews)</span>
              </div>
              <p className="text-gray-500 text-sm mt-1 truncate">{place.adresse || place.address}</p>
              <div className="flex gap-2 mt-3">
                <span className="px-2 py-1 bg-blue-50 text-blue-600 text-[10px] font-bold rounded-md uppercase tracking-wider">
                  {place.code_type || place.type}
                </span>
                {place.point_eau === '1' && <span className="text-[10px] text-gray-400 font-medium flex items-center gap-0.5"><Info size={10} /> Water</span>}
              </div>
            </div>
          </div>
        ))}
        {places.length === 0 && (
          <div className="text-center py-20">
            <p className="text-gray-500">No parking spots found in this area.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ListView;
