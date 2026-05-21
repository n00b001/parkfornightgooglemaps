import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, Map, Droplets, Zap, Trash2, Wifi, Info, Waves, ShowerHead } from 'lucide-react';
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
  { key: 'douche', label: 'Shower', icon: ShowerHead, color: 'text-blue-400' },
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
  }, [place.id]);

  const addToGoogleMaps = () => {
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre || place.name)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const openStreetView = () => {
    const url = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const photos = place.photos || [];

  return (
    <div className="fixed inset-x-4 bottom-4 md:inset-auto md:right-4 md:bottom-4 md:w-[450px] z-40 bg-white rounded-3xl shadow-2xl overflow-hidden max-h-[85vh] flex flex-col transition-all duration-300 ease-in-out border border-gray-100">
      {photos.length > 0 && (
        <div className="h-56 overflow-x-auto flex gap-1 snap-x bg-gray-100 scrollbar-hide">
          {photos.map((p: any, idx: number) => (
            <img key={idx} src={p.lien_mini} alt={`Spot ${idx}`} className="h-full object-cover snap-center min-w-[85%]" />
          ))}
        </div>
      )}
      <div className="p-6 overflow-y-auto flex-1">
        <div className="flex justify-between items-start mb-2">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 leading-tight">{place.titre || place.name}</h2>
            <div className="flex items-center gap-1 mt-1">
              <Star size={16} fill="orange" className="text-orange-500" />
              <span className="font-bold text-gray-900">{place.note_moyenne || 'N/A'}</span>
              <span className="text-gray-400 text-sm">({place.nb_comm || 0} reviews)</span>
              <span className="mx-2 text-gray-200">|</span>
              <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full uppercase tracking-wider">
                {place.code_type === 'cc' ? 'Motorhome' :
                 place.code_type === 'p' ? 'Parking' :
                 place.code_type === 'cp' ? 'Campsite' :
                 place.code_type === 'p_prive' ? 'Private' :
                 place.code_type === 'ferme' ? 'Farm' :
                 place.code_type === 'nature' ? 'Nature' : 'Other'}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors"><X size={20} className="text-gray-400" /></button>
        </div>

        <p className="text-sm text-gray-500 mb-4 flex items-start gap-1">
          <MapPin size={14} className="mt-0.5 flex-shrink-0" />
          {place.adresse}
        </p>

        {place.description && (
          <div className="bg-gray-50 p-4 rounded-2xl mb-6">
            <p className="text-sm text-gray-700 leading-relaxed italic">"{place.description}"</p>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <button
              onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-bold transition-all flex items-center justify-center gap-2 shadow-lg shadow-blue-200 active:scale-95"
            >
              <Navigation size={18} /> Directions
            </button>
            <button
              onClick={onToggleFavorite}
              className={`p-4 border rounded-2xl transition-all active:scale-95 ${isFavorite ? 'bg-red-50 border-red-100' : 'hover:bg-gray-50 border-gray-100'}`}
              title={isFavorite ? "Remove from Favorites" : "Add to Favorites"}
            >
              <Heart size={24} fill={isFavorite ? '#EF4444' : 'none'} color={isFavorite ? '#EF4444' : '#9CA3AF'} />
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={openStreetView}
              className="flex-1 border border-gray-100 py-3 rounded-2xl font-bold hover:bg-gray-50 transition-colors flex items-center justify-center gap-2 text-gray-700"
            >
              <Map size={18} className="text-gray-400" /> Street View
            </button>
            <button
              onClick={addToGoogleMaps}
              className="flex-1 border border-green-100 bg-green-50 text-green-700 py-3 rounded-2xl font-bold hover:bg-green-100 transition-colors flex items-center justify-center gap-2"
              title="Open in Google Maps / Save to List"
            >
              <ExternalLink size={18} /> Save to Google Maps
            </button>
          </div>
        </div>

        <div className="mt-8">
          <h3 className="text-xs font-bold text-gray-400 uppercase mb-4 tracking-widest">Amenities & Services</h3>
          <div className="grid grid-cols-4 gap-3">
            {AMENITIES.map(amenity => {
              const hasAmenity = place[amenity.key as keyof Place] === '1';
              if (!hasAmenity) return null;
              return (
                <div key={amenity.key} className="flex flex-col items-center p-3 bg-white rounded-2xl border border-gray-100 shadow-sm hover:border-blue-100 transition-colors">
                  <amenity.icon size={22} className={amenity.color} />
                  <span className="text-[10px] mt-2 font-bold text-gray-500 text-center">{amenity.label}</span>
                </div>
              );
            })}
            {!AMENITIES.some(a => place[a.key as keyof Place] === '1') && <p className="text-sm text-gray-400 italic col-span-4 py-4 text-center border-2 border-dashed border-gray-50 rounded-2xl">No amenity info available.</p>}
          </div>
        </div>

        <div className="mt-8 border-t border-gray-100 pt-6 pb-4">
          <h3 className="font-bold text-lg text-gray-900 mb-4 flex items-center gap-2"><MessageSquare size={20} className="text-blue-600" /> Reviews</h3>

          {isAuthenticated && (
            <div className="mb-8 bg-blue-50/50 p-4 rounded-2xl border border-blue-50">
              <h4 className="text-xs font-bold text-blue-600 uppercase mb-3 tracking-wider">Share your experience</h4>
              <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
            </div>
          )}

          <div className="space-y-6">
            {isLoadingReviews ? (
              <div className="space-y-4 animate-pulse">
                {[1, 2].map(i => (
                  <div key={i} className="h-24 bg-gray-100 rounded-2xl" />
                ))}
              </div>
            ) : (
              <>
                {reviews.length > 0 && (
                  <div>
                    <h4 className="text-[10px] font-bold text-blue-500 uppercase mb-4 tracking-widest">Local Community</h4>
                    <div className="space-y-4">
                      {reviews.map(r => (
                        <div key={r.id} className="text-sm bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
                          <div className="flex justify-between items-center mb-2">
                            <span className="font-bold text-gray-900">{r.user?.name}</span>
                            <div className="flex gap-0.5">
                              {[...Array(5)].map((_, i) => (
                                <Star key={i} size={12} fill={i < r.rating ? '#F59E0B' : 'none'} stroke={i < r.rating ? '#F59E0B' : '#D1D5DB'} />
                              ))}
                            </div>
                          </div>
                          <p className="text-gray-600 leading-relaxed">{r.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {p4nReviews.length > 0 && (
                  <div>
                    <h4 className="text-[10px] font-bold text-gray-400 uppercase mb-4 tracking-widest">Park4Night Reviews</h4>
                    <div className="space-y-4">
                      {p4nReviews.map((r, idx) => (
                        <div key={idx} className="text-sm border-b border-gray-50 pb-4 last:border-0">
                          <div className="flex justify-between items-center mb-1">
                            <span className="font-bold text-gray-800">{r.auteur}</span>
                            <div className="flex items-center gap-1">
                               <Star size={10} fill="#F59E0B" className="text-orange-500" />
                               <span className="text-orange-500 font-bold text-xs">{r.note}/5</span>
                            </div>
                          </div>
                          <p className="text-gray-500 italic leading-relaxed">"{r.texte}"</p>
                          <p className="text-[10px] text-gray-300 mt-1">{r.date}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {reviews.length === 0 && p4nReviews.length === 0 && (
                  <div className="text-center py-10">
                    <MessageSquare size={32} className="mx-auto text-gray-200 mb-2" />
                    <p className="text-sm text-gray-400">No reviews yet. Be the first to rate!</p>
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

const MapPin = ({ size, className }: { size?: number, className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
);

export default PlaceDetails;
