import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, MapPin } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [localReviews, setLocalReviews] = useState<any[]>([]);
  const [p4nReviews, setP4nReviews] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'info' | 'reviews'>('info');

  const fetchReviews = async () => {
    try {
      // Local reviews
      const localRes = await axios.get(`/api/reviews/${place.id}`);
      setLocalReviews(localRes.data);

      // P4N reviews
      const p4nRes = await axios.get(`/api/places/${place.id}/reviews`);
      setP4nReviews(p4nRes.data.comm || []);
    } catch (err) {
      console.error('Failed to fetch reviews', err);
    }
  };

  useEffect(() => {
    if (place) {
      fetchReviews();
      setActiveTab('info');
    }
  }, [place]);

  const addToGoogleMaps = () => {
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  if (!place) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-white rounded-t-[32px] shadow-2xl transition-all duration-300 ease-in-out max-h-[90vh] overflow-hidden flex flex-col md:left-4 md:bottom-4 md:right-auto md:w-[400px] md:rounded-[32px]">
      {/* Handle for mobile */}
      <div className="w-12 h-1.5 bg-gray-200 rounded-full mx-auto mt-3 mb-1 md:hidden" />

      <div className="p-6 overflow-y-auto">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-2xl font-extrabold text-gray-900 leading-tight">{place.titre}</h2>
            <div className="flex items-center gap-2 mt-1">
              <div className="flex items-center bg-orange-50 px-2 py-0.5 rounded-lg">
                <Star size={14} fill="orange" className="text-orange-500 mr-1" />
                <span className="font-bold text-orange-700 text-sm">{place.note_moyenne || '0'}</span>
              </div>
              <span className="text-gray-400 text-sm">{place.nb_comm || 0} reviews</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="flex border-b mb-4">
            <button
                className={`pb-2 px-4 text-sm font-bold transition-colors ${activeTab === 'info' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
                onClick={() => setActiveTab('info')}
            >
                Info
            </button>
            <button
                className={`pb-2 px-4 text-sm font-bold transition-colors ${activeTab === 'reviews' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}
                onClick={() => setActiveTab('reviews')}
            >
                Reviews ({localReviews.length + p4nReviews.length})
            </button>
        </div>

        {activeTab === 'info' ? (
            <div className="space-y-4">
                <div className="flex items-start gap-3 text-gray-600">
                    <MapPin size={18} className="mt-0.5 flex-shrink-0" />
                    <p className="text-sm">{place.adresse}</p>
                </div>

                {place.description && (
                    <div className="bg-gray-50 p-4 rounded-2xl">
                        <p className="text-sm text-gray-700 leading-relaxed italic">"{place.description}"</p>
                    </div>
                )}

                <div className="grid grid-cols-2 gap-3 pt-2">
                    <button
                        onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`, '_blank')}
                        className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-bold transition-all shadow-lg shadow-blue-100"
                    >
                        <Navigation size={18} /> Directions
                    </button>
                    <div className="flex gap-2">
                        <button
                            onClick={onToggleFavorite}
                            className={`flex-1 flex items-center justify-center border-2 rounded-2xl transition-colors ${isFavorite ? 'border-red-100 bg-red-50 text-red-500' : 'border-gray-100 hover:bg-gray-50 text-gray-500'}`}
                        >
                            <Heart size={20} fill={isFavorite ? 'currentColor' : 'none'} />
                        </button>
                        <button
                            onClick={addToGoogleMaps}
                            className="flex-1 flex items-center justify-center border-2 border-gray-100 rounded-2xl hover:bg-gray-50 text-gray-500 transition-colors"
                            title="Save to Google Maps"
                        >
                            <ExternalLink size={20} />
                        </button>
                    </div>
                </div>
            </div>
        ) : (
            <div className="space-y-6">
                {isAuthenticated && (
                    <div className="mb-6">
                        <h3 className="text-sm font-bold text-gray-900 mb-2">Write a review</h3>
                        <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
                    </div>
                )}

                <div className="space-y-6">
                    {localReviews.length > 0 && (
                        <div>
                            <h3 className="text-xs font-black uppercase tracking-wider text-gray-400 mb-3">Community Reviews</h3>
                            <div className="space-y-4">
                                {localReviews.map(r => (
                                    <div key={r.id} className="bg-blue-50/50 p-4 rounded-2xl">
                                        <div className="flex justify-between items-center mb-1">
                                            <span className="font-bold text-sm">{r.user?.name}</span>
                                            <div className="flex gap-0.5">
                                                {[...Array(5)].map((_, i) => (
                                                    <Star key={i} size={10} fill={i < r.rating ? '#3B82F6' : 'none'} className={i < r.rating ? 'text-blue-500' : 'text-gray-300'} />
                                                ))}
                                            </div>
                                        </div>
                                        <p className="text-sm text-gray-700">{r.content}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {p4nReviews.length > 0 && (
                        <div>
                            <h3 className="text-xs font-black uppercase tracking-wider text-gray-400 mb-3">Park4night Reviews</h3>
                            <div className="space-y-4">
                                {p4nReviews.map((r, idx) => (
                                    <div key={idx} className="border-b border-gray-100 pb-4 last:border-0">
                                        <div className="flex justify-between items-center mb-1">
                                            <span className="font-bold text-sm text-gray-900">{r.auteur || 'User'}</span>
                                            <span className="text-[10px] text-gray-400 font-medium">{r.date_envoi}</span>
                                        </div>
                                        <p className="text-sm text-gray-600 line-clamp-4">{r.texte}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {localReviews.length === 0 && p4nReviews.length === 0 && (
                        <div className="text-center py-8 text-gray-400 italic text-sm">
                            No reviews yet.
                        </div>
                    )}
                </div>
            </div>
        )}
      </div>
    </div>
  );
};

export default PlaceDetails;
