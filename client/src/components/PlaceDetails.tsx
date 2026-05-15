import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, MapPin } from 'lucide-react';
import axios from 'axios';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchReviews = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/api/places/${place.id}/reviews`);
      setReviews(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (place) fetchReviews();
  }, [place]);

  const addToGoogleMaps = () => {
    // This allows adding/searching for the point on Google Maps
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const getDirections = () => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 md:bottom-4 md:left-4 md:right-auto md:w-[400px] z-40 bg-white rounded-t-3xl md:rounded-3xl shadow-[0_-10px_40px_rgba(0,0,0,0.1)] p-0 flex flex-col max-h-[85vh] overflow-hidden transition-all animate-in slide-in-from-bottom duration-300">
      <div className="relative h-48 w-full bg-gray-200">
        {place.url_image && (
          <img src={place.url_image} alt={place.titre} className="w-full h-full object-cover" />
        )}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-white/80 backdrop-blur-md rounded-full shadow-md hover:bg-white transition-colors"
        >
          <X size={20} />
        </button>
      </div>

      <div className="p-6 overflow-y-auto">
        <div className="flex justify-between items-start mb-1">
          <h2 className="text-2xl font-black text-gray-900 leading-tight">{place.titre}</h2>
          <div className="flex items-center gap-1 bg-yellow-100 text-yellow-700 px-2 py-1 rounded-lg font-bold text-sm">
            <Star size={14} fill="currentColor" />
            {place.note_moyenne || '0.0'}
          </div>
        </div>

        <div className="flex items-center gap-1 text-gray-500 mb-6 text-sm">
          <MapPin size={14} />
          <span className="truncate">{place.adresse}</span>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-8">
          <button
            onClick={getDirections}
            className="flex flex-col items-center gap-2 p-3 bg-blue-50 text-blue-600 rounded-2xl font-bold transition-all hover:bg-blue-100 active:scale-95"
          >
            <Navigation size={22} />
            <span className="text-[10px] uppercase tracking-wider">Directions</span>
          </button>

          <button
            onClick={onToggleFavorite}
            className={`flex flex-col items-center gap-2 p-3 rounded-2xl font-bold transition-all active:scale-95 ${isFavorite ? 'bg-red-50 text-red-500' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'}`}
          >
            <Heart size={22} fill={isFavorite ? 'currentColor' : 'none'} />
            <span className="text-[10px] uppercase tracking-wider">{isFavorite ? 'Saved' : 'Save'}</span>
          </button>

          <button
            onClick={addToGoogleMaps}
            className="flex flex-col items-center gap-2 p-3 bg-green-50 text-green-600 rounded-2xl font-bold transition-all hover:bg-green-100 active:scale-95"
            title="Open in Google Maps"
          >
            <ExternalLink size={22} />
            <span className="text-[10px] uppercase tracking-wider">G Maps</span>
          </button>
        </div>

        <div className="space-y-6">
          {place.description && (
            <div>
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">About</h3>
              <p className="text-gray-600 text-sm leading-relaxed">{place.description}</p>
            </div>
          )}

          <div>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                <MessageSquare size={14} /> Reviews
              </h3>
            </div>

            {isAuthenticated && (
              <div className="mb-6">
                <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
              </div>
            )}

            <div className="space-y-4">
              {loading ? (
                <div className="text-center py-4 text-gray-400 text-sm italic">Loading reviews...</div>
              ) : reviews.length > 0 ? (
                reviews.map(r => (
                  <div key={r.id} className="bg-gray-50 p-4 rounded-2xl">
                    <div className="flex justify-between mb-1">
                      <span className="font-bold text-sm text-gray-800">{r.user?.name}</span>
                      <div className="flex items-center gap-0.5 text-yellow-500">
                        {[...Array(5)].map((_, i) => (
                          <Star key={i} size={10} fill={i < r.rating ? 'currentColor' : 'none'} />
                        ))}
                      </div>
                    </div>
                    <p className="text-gray-600 text-sm">{r.content}</p>
                    {r.createdAt && (
                      <span className="text-[10px] text-gray-400 mt-2 block italic">
                        {new Date(r.createdAt).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                ))
              ) : (
                <div className="text-center py-4 text-gray-400 text-sm italic">No reviews yet</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
