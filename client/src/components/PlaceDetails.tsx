import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
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
    <div className="fixed bottom-4 left-4 right-4 md:w-96 z-40 bg-white rounded-3xl shadow-2xl p-6 max-h-[80vh] overflow-y-auto">
      <div className="flex justify-between mb-2">
        <h2 className="text-2xl font-bold">{place.titre}</h2>
        <button onClick={onClose}><X size={20} /></button>
      </div>
      <div className="flex items-center gap-1 mb-1">
        <Star size={16} fill="orange" className="text-orange-500" />
        <span className="font-bold">{place.note_moyenne || 'N/A'}</span>
        <span className="text-gray-400 text-sm">({place.nb_comm || 0} reviews)</span>
      </div>
      <p className="text-sm text-gray-500 mb-4">{place.adresse}</p>

      {place.description && (
        <p className="text-sm text-gray-700 mb-4 line-clamp-3">{place.description}</p>
      )}

      <div className="flex gap-2">
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

      <div className="mt-6 border-t pt-4">
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
  );
};

export default PlaceDetails;
