import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, MapPin, Info, CheckCircle } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated, isVisited }) => {
  const [reviews, setReviews] = useState<any[]>([]);
  const [p4nReviews, setP4nReviews] = useState<any[]>([]);

  const fetchReviews = async () => {
    try {
      const [localRes, p4nRes] = await Promise.all([
        axios.get(`/api/reviews/${place.id}`),
        axios.get(`/api/places/${place.id}/reviews`)
      ]);
      setReviews(localRes.data);
      setP4nReviews(p4nRes.data?.commentaires || []);
    } catch (err) {
      console.error('Failed to fetch reviews', err);
    }
  };

  useEffect(() => {
    if (place) fetchReviews();
  }, [place]);

  const addToGoogleMaps = () => {
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  return (
    <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-96 z-40 bg-white rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
      <div className="relative h-32 bg-gradient-to-br from-blue-500 to-indigo-600 p-6 flex items-end">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-white/20 hover:bg-white/30 rounded-full text-white transition-colors"
        >
          <X size={20} />
        </button>
        <div>
          <h2 className="text-2xl font-bold text-white leading-tight">{place.titre || place.name}</h2>
          {isVisited && (
            <div className="flex items-center gap-1 text-green-300 text-xs font-bold mt-1 uppercase tracking-wider">
              <CheckCircle size={12} /> Visited
            </div>
          )}
        </div>
      </div>

      <div className="p-6 overflow-y-auto custom-scrollbar">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-1">
            <Star size={18} fill="#F59E0B" className="text-amber-500" />
            <span className="font-bold text-lg">{place.note_moyenne || 'N/A'}</span>
            <span className="text-gray-400 text-sm">({place.nb_comm || 0} reviews)</span>
          </div>
          <span className="px-3 py-1 bg-gray-100 rounded-full text-xs font-bold text-gray-600 uppercase tracking-tighter">
            {place.code_type}
          </span>
        </div>

        <div className="flex items-start gap-2 mb-4 text-gray-600">
          <MapPin size={18} className="mt-0.5 shrink-0 text-blue-500" />
          <p className="text-sm">{place.adresse}</p>
        </div>

        {place.description && (
          <div className="mb-6 bg-gray-50 p-4 rounded-2xl border border-gray-100">
            <h4 className="text-xs font-bold text-gray-400 uppercase mb-2 flex items-center gap-1">
              <Info size={12} /> Description
            </h4>
            <p className="text-sm text-gray-700 leading-relaxed">{place.description}</p>
          </div>
        )}

        <div className="flex gap-2 mb-8">
        <button
          onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
          className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-2xl font-bold transition-colors flex items-center justify-center gap-2 shadow-lg shadow-blue-200"
        >
          <Navigation size={18} /> Directions
        </button>
        <button
          onClick={onToggleFavorite}
          className="p-3 border rounded-xl hover:bg-gray-50 transition-colors"
          title={isFavorite ? "Remove from Favorites" : "Add to Favorites"}
        >
          <Heart size={20} fill={isFavorite ? 'red' : 'none'} color={isFavorite ? 'red' : 'currentColor'} />
        </button>
        <button
          onClick={addToGoogleMaps}
          className="p-3 border border-green-200 bg-green-50 text-green-700 rounded-xl hover:bg-green-100 transition-colors"
          title="Open in Google Maps / Save to List"
        >
          <ExternalLink size={20} />
        </button>
      </div>

        <div className="border-t pt-6">
        <h3 className="font-bold mb-2 flex items-center gap-2"><MessageSquare size={18} /> Reviews</h3>
        {isAuthenticated && (
          <div className="mb-4">
            <h4 className="text-xs font-bold text-gray-400 uppercase mb-2">Write a review</h4>
            <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
          </div>
        )}

        <div className="mt-4 space-y-4">
          {reviews.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-blue-500 uppercase mb-2">Community Reviews</h4>
              <div className="space-y-3">
                {reviews.map(r => (
                  <div key={r.id} className="text-sm bg-blue-50/30 p-3 rounded-xl border border-blue-100">
                    <div className="flex justify-between mb-1">
                      <span className="font-bold">{r.user?.name}</span>
                      <div className="flex gap-0.5">
                        {[...Array(5)].map((_, i) => (
                          <Star key={i} size={12} fill={i < r.rating ? 'orange' : 'none'} stroke={i < r.rating ? 'orange' : 'gray'} />
                        ))}
                      </div>
                    </div>
                    <p className="text-gray-700">{r.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {p4nReviews.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-gray-400 uppercase mb-2">Park4Night Reviews</h4>
              <div className="space-y-3">
                {p4nReviews.map((r, idx) => (
                  <div key={idx} className="text-sm border-b pb-2">
                    <div className="flex justify-between mb-1">
                      <span className="font-bold">{r.auteur}</span>
                      <span className="text-orange-500 font-bold">{r.note}/5</span>
                    </div>
                    <p className="text-gray-600 italic">"{r.texte}"</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {reviews.length === 0 && p4nReviews.length === 0 && (
            <p className="text-sm text-gray-400 italic">No reviews yet.</p>
          )}
        </div>
      </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
