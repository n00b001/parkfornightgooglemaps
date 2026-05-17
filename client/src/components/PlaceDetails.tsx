import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink } from 'lucide-react';
import axios from 'axios';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [reviews, setReviews] = useState<any[]>([]);

  const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '',
    withCredentials: true
  });

  const fetchReviews = async () => {
    try {
      const res = await api.get(`/api/reviews/${place.id}`);
      setReviews(res.data);
    } catch (err) {}
  };

  useEffect(() => {
    if (place) fetchReviews();
  }, [place]);

  const addToGoogleMaps = () => {
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-lg z-40 bg-white/95 backdrop-blur-md rounded-[2.5rem] shadow-[0_20px_50px_rgba(0,0,0,0.2)] p-6 max-h-[85vh] overflow-y-auto border border-white/20 animate-in fade-in slide-in-from-bottom-4 duration-300">
      <div className="flex justify-between items-start mb-2">
        <div>
          <h2 className="text-2xl font-extrabold text-gray-900 leading-tight">{place.titre}</h2>
          <div className="flex items-center gap-1 mt-1">
            <span className="bg-yellow-100 text-yellow-700 text-xs font-bold px-2 py-0.5 rounded-full">★ {place.note_moyenne || '0'}</span>
            <span className="text-gray-400 text-xs">• {place.adresse}</span>
          </div>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors"><X size={20} className="text-gray-400" /></button>
      </div>

      <div className="flex gap-3 mt-6">
        <button
          onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
          className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-bold flex items-center justify-center gap-2 shadow-lg shadow-blue-200 transition-all active:scale-95"
        >
          <Navigation size={18} /> Directions
        </button>
        <button onClick={onToggleFavorite} className="p-4 border border-gray-100 rounded-2xl hover:bg-gray-50 transition-all active:scale-95">
          <Heart size={20} className={isFavorite ? 'text-red-500 fill-red-500' : 'text-gray-400'} />
        </button>
        <button onClick={addToGoogleMaps} className="p-4 border border-gray-100 rounded-2xl hover:bg-gray-50 transition-all active:scale-95" title="Save to Google Maps">
          <ExternalLink size={20} className="text-gray-400" />
        </button>
      </div>

      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-lg text-gray-900 flex items-center gap-2">
            <MessageSquare size={18} className="text-blue-500" /> Reviews
          </h3>
          <span className="text-xs text-gray-400">{reviews.length} reviews</span>
        </div>

        {isAuthenticated && (
          <div className="bg-gray-50 p-4 rounded-2xl mb-4 border border-gray-100">
            <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
          </div>
        )}

        <div className="space-y-4">
          {reviews.length > 0 ? reviews.map(r => (
            <div key={r.id} className="p-4 bg-white border border-gray-100 rounded-2xl shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs">
                  {r.user?.name?.charAt(0) || 'U'}
                </div>
                <div>
                  <div className="text-sm font-bold text-gray-800">{r.user?.name}</div>
                  <div className="text-[10px] text-gray-400">{new Date(r.createdAt).toLocaleDateString()}</div>
                </div>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">{r.content}</p>
            </div>
          )) : (
            <div className="text-center py-8 text-gray-400 italic text-sm">No reviews yet. Be the first!</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
