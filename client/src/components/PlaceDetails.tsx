import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, Map, Droplets, Zap, Trash2, Wifi, Info, Bath, Waves } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';
import { Place } from '../types';

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

interface PlaceDetailsProps {
  place: Place;
  onClose: () => void;
  onToggleFavorite: () => void;
  isFavorite: boolean;
  isAuthenticated: boolean;
}

const PlaceDetails: React.FC<PlaceDetailsProps> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [reviews, setReviews] = useState<any[]>([]);
  const [p4nReviews, setP4nReviews] = useState<any[]>([]);
  const [isLoadingReviews, setIsLoadingReviews] = useState(false);

  const fetchReviews = async () => {
    setIsLoadingReviews(true);
    try {
      const [localRes, p4nRes] = await Promise.all([
        axios.get(`/api/reviews/${place.id}`),
        axios.get(`/api/places/${place.id}/reviews`)
      ]);
      setReviews(localRes.data);
      setP4nReviews(p4nRes.data?.commentaires || []);
    } catch (err) {
      console.error('Failed to fetch reviews', err);
    } finally {
      setIsLoadingReviews(false);
    }
  };

  useEffect(() => {
    if (place) fetchReviews();
  }, [place]);

  const addToGoogleMaps = () => {
    const googlePlaceId = place.google_place_id || place.rawData?.google_place_id;
    if (googlePlaceId) {
      // Use the place ID for direct saving/viewing if available
      window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre || place.name)}&query_place_id=${googlePlaceId}`, '_blank');
    } else {
      const query = encodeURIComponent(`${place.titre || place.name} ${place.adresse || ''}`);
      window.open(`https://www.google.com/maps/search/?api=1&query=${query}`, '_blank');
    }
  };

  const openStreetView = () => {
    const url = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const photos = place.photos || place.rawData?.photos || [];

  return (
    <div className="fixed bottom-4 left-4 right-4 md:w-[450px] md:bottom-6 md:left-6 z-40 bg-white rounded-[2.5rem] shadow-[0_20px_50px_rgba(0,0,0,0.2)] overflow-hidden max-h-[85vh] flex flex-col animate-in slide-in-from-bottom duration-300">
      {photos.length > 0 && (
        <div className="h-56 overflow-x-auto flex gap-1 snap-x bg-gray-100 no-scrollbar">
          {photos.map((p: any, idx: number) => (
            <img key={idx} src={p.lien_mini} alt={`Spot ${idx}`} className="h-full object-cover snap-center min-w-[85%]" />
          ))}
        </div>
      )}
      <div className="p-8 overflow-y-auto flex-1 custom-scrollbar">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-2xl font-black tracking-tight text-gray-900 leading-tight">{place.titre || place.name}</h2>
            <div className="flex items-center gap-2 mt-2">
              <div className="flex items-center gap-1 bg-orange-50 px-2 py-1 rounded-lg">
                <Star size={14} fill="orange" className="text-orange-500" />
                <span className="font-black text-orange-700 text-sm">{place.note_moyenne || place.rating || 'N/A'}</span>
              </div>
              <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">({place.nb_comm || 0} reviews)</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <X size={20} className="text-gray-400" />
          </button>
        </div>

        <p className="text-sm text-gray-500 mb-6 font-medium leading-relaxed flex items-start gap-2">
          <Map size={16} className="mt-0.5 shrink-0" />
          {place.adresse || place.address}
        </p>

        {place.description && (
          <div className="mb-6">
            <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.2em] mb-2">Description</h3>
            <p className="text-sm text-gray-700 leading-relaxed">{place.description}</p>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <button
              onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-black text-sm transition-all flex items-center justify-center gap-2 shadow-xl shadow-blue-100 active:scale-95"
            >
              <Navigation size={18} fill="currentColor" /> Directions
            </button>
            <button
              onClick={onToggleFavorite}
              className={`p-4 border rounded-2xl transition-all active:scale-90 ${isFavorite ? 'bg-red-50 border-red-100 text-red-500' : 'bg-gray-50 border-gray-100 text-gray-400'}`}
              title={isFavorite ? "Remove from Favorites" : "Add to Favorites"}
            >
              <Heart size={20} fill={isFavorite ? 'currentColor' : 'none'} />
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={openStreetView}
              className="flex-1 bg-gray-50 border border-gray-100 py-4 rounded-2xl font-black text-sm text-gray-700 hover:bg-gray-100 transition-all flex items-center justify-center gap-2 active:scale-95"
            >
              <Map size={18} /> Street View
            </button>
            <button
              onClick={addToGoogleMaps}
              className="flex-1 border border-green-200 bg-green-50 text-green-700 py-4 rounded-2xl font-black text-sm hover:bg-green-100 transition-all flex items-center justify-center gap-2 active:scale-95"
              title="Open in Google Maps / Save to List"
            >
              <ExternalLink size={18} /> Google Maps
            </button>
          </div>
        </div>

        <div className="mt-8">
          <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.2em] mb-3">Amenities</h3>
          <div className="grid grid-cols-4 gap-2">
            {AMENITIES.map(amenity => {
              const hasAmenity = (place[amenity.key] === '1') || (place.rawData?.[amenity.key] === '1');
              if (!hasAmenity) return null;
              return (
                <div key={amenity.key} className="flex flex-col items-center p-3 bg-gray-50 rounded-2xl border border-gray-100 transition-all hover:bg-white hover:shadow-md">
                  <amenity.icon size={20} className={amenity.color} />
                  <span className="text-[9px] mt-1.5 font-black uppercase tracking-tighter text-center text-gray-500">{amenity.label}</span>
                </div>
              );
            })}
            {!AMENITIES.some(a => (place[a.key] === '1') || (place.rawData?.[a.key] === '1')) && (
              <p className="text-xs text-gray-400 font-bold italic col-span-4 bg-gray-50 p-4 rounded-2xl border border-dashed text-center">No amenity info available.</p>
            )}
          </div>
        </div>

        <div className="mt-10 border-t border-gray-100 pt-8">
          <h3 className="text-xl font-black tracking-tight text-gray-900 mb-6 flex items-center gap-2">
            <MessageSquare size={20} className="text-blue-600" /> Reviews
          </h3>

          {isAuthenticated && (
            <div className="mb-8 bg-blue-50/50 p-6 rounded-3xl border border-blue-100/50">
              <h4 className="text-[10px] font-black text-blue-400 uppercase tracking-[0.2em] mb-4">Write a review</h4>
              <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
            </div>
          )}

          <div className="space-y-6">
            {isLoadingReviews ? (
              <div className="space-y-4 animate-pulse">
                {[1, 2].map(i => (
                  <div key={i} className="h-24 bg-gray-100 rounded-3xl" />
                ))}
              </div>
            ) : (
              <>
                {reviews.length > 0 && (
                  <div>
                    <h4 className="text-[10px] font-black text-blue-500 uppercase tracking-[0.2em] mb-4">Community Reviews</h4>
                    <div className="space-y-4">
                      {reviews.map(r => (
                        <div key={r.id} className="text-sm bg-white p-5 rounded-3xl border border-gray-100 shadow-sm">
                          <div className="flex justify-between items-center mb-3">
                            <div className="flex items-center gap-2">
                              {r.user?.avatar && <img src={r.user.avatar} className="w-6 h-6 rounded-lg" alt="" />}
                              <span className="font-black text-gray-900">{r.user?.name}</span>
                            </div>
                            <div className="flex gap-0.5">
                              {[...Array(5)].map((_, i) => (
                                <Star key={i} size={10} fill={i < r.rating ? '#F59E0B' : 'none'} stroke={i < r.rating ? '#F59E0B' : '#D1D5DB'} />
                              ))}
                            </div>
                          </div>
                          <p className="text-gray-600 leading-relaxed font-medium">{r.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {p4nReviews.length > 0 && (
                  <div className="mt-8">
                    <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.2em] mb-4">Park4Night Reviews</h4>
                    <div className="space-y-4">
                      {p4nReviews.map((r, idx) => (
                        <div key={idx} className="text-sm border-b border-gray-50 pb-4 last:border-0">
                          <div className="flex justify-between mb-2">
                            <span className="font-black text-gray-800 text-xs">{r.auteur}</span>
                            <div className="flex items-center gap-1">
                              <Star size={10} fill="orange" className="text-orange-500" />
                              <span className="text-orange-600 font-black text-xs">{r.note}/5</span>
                            </div>
                          </div>
                          <p className="text-gray-500 italic leading-relaxed text-xs">"{r.texte}"</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {reviews.length === 0 && p4nReviews.length === 0 && (
                  <div className="bg-gray-50 p-8 rounded-3xl border border-dashed border-gray-200 text-center">
                    <p className="text-sm text-gray-400 font-bold italic">No reviews yet. Be the first!</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
