import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, MapPin } from 'lucide-react';
import axios from 'axios';
import ReviewForm from './ReviewForm';

interface PlaceDetailsProps {
  place: any;
  onClose: () => void;
  onToggleFavorite: () => void;
  isFavorite: boolean;
  isAuthenticated: boolean;
}

const PlaceDetails: React.FC<PlaceDetailsProps> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [reviews, setReviews] = useState<any[]>([]);
  const [isLoadingReviews, setIsLoadingReviews] = useState(false);

  const fetchReviews = async () => {
    setIsLoadingReviews(true);
    try {
      const res = await axios.get(`/api/places/${place.id}/reviews`);
      // Park4night reviews or local reviews
      setReviews(res.data.commentaires || res.data || []);
    } catch (err) {
      console.error('Failed to fetch reviews:', err);
    } finally {
      setIsLoadingReviews(false);
    }
  };

  useEffect(() => {
    if (place) fetchReviews();
  }, [place.id]);

  const addToGoogleMaps = () => {
    // This opens Google Maps search for the specific place, making it easy to save
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.name)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const getDirections = () => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 md:bottom-6 md:left-6 md:right-auto md:w-[400px] z-40 bg-white rounded-t-[32px] md:rounded-[32px] shadow-[0_-8px_30px_rgb(0,0,0,0.12)] p-6 max-h-[85vh] overflow-y-auto animate-in slide-in-from-bottom duration-300">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h2 className="text-2xl font-black text-gray-900 leading-tight">{place.name}</h2>
          <div className="flex items-center gap-1 mt-1 text-amber-500">
            <Star size={16} fill="currentColor" />
            <span className="font-bold">{place.rating || 'N/A'}</span>
            <span className="text-gray-400 font-normal text-sm ml-1">({reviews.length} reviews)</span>
          </div>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
          <X size={24} className="text-gray-400" />
        </button>
      </div>

      <div className="flex items-start gap-2 text-gray-500 mb-6">
        <MapPin size={18} className="mt-1 shrink-0" />
        <p className="text-sm leading-relaxed">{place.address}</p>
      </div>

      <div className="flex gap-3 mb-8">
        <button
          onClick={getDirections}
          className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-bold flex items-center justify-center gap-2 shadow-lg shadow-blue-200 transition-all active:scale-[0.98]"
        >
          <Navigation size={20} /> Directions
        </button>
        <button
          onClick={onToggleFavorite}
          className={`p-4 border rounded-2xl transition-all active:scale-[0.95] ${isFavorite ? 'bg-red-50 border-red-100' : 'bg-white border-gray-200'}`}
        >
          <Heart size={24} className={isFavorite ? 'text-red-500' : 'text-gray-400'} fill={isFavorite ? 'currentColor' : 'none'} />
        </button>
        <button
          onClick={addToGoogleMaps}
          className="p-4 border border-gray-200 rounded-2xl bg-white hover:bg-gray-50 transition-all active:scale-[0.95]"
          title="Open in Google Maps"
        >
          <ExternalLink size={24} className="text-gray-600" />
        </button>
      </div>

      <div className="space-y-6">
        <div className="flex items-center justify-between border-b pb-4">
          <h3 className="text-lg font-bold flex items-center gap-2 text-gray-800">
            <MessageSquare size={20} className="text-blue-500" /> Community Reviews
          </h3>
        </div>

        {isAuthenticated ? (
          <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
        ) : (
          <div className="p-4 bg-gray-50 rounded-2xl text-center">
            <p className="text-sm text-gray-500 mb-2">Sign in to share your experience</p>
            <a href="/auth/google" className="text-blue-600 font-bold text-sm hover:underline">Sign in with Google</a>
          </div>
        )}

        <div className="space-y-4">
          {isLoadingReviews ? (
            <div className="text-center py-4 text-gray-400 animate-pulse">Loading reviews...</div>
          ) : reviews.length > 0 ? (
            reviews.map((r: any, idx: number) => (
              <div key={r.id || idx} className="bg-gray-50 p-4 rounded-2xl border border-gray-100">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-bold text-sm text-gray-900">{r.user?.name || r.auteur || 'Traveler'}</span>
                  <div className="flex text-amber-400">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star key={i} size={12} fill={i < (r.rating || r.note || 5) ? 'currentColor' : 'none'} />
                    ))}
                  </div>
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">{r.content || r.texte}</p>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-gray-400 italic text-sm">No reviews yet. Be the first!</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
