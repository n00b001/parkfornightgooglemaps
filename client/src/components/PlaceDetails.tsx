import React, { useState, useEffect } from 'react';
import { Heart, Star, MapPin, Navigation, X, ExternalLink, MessageSquare } from 'lucide-react';
import axios from 'axios';
import ReviewForm from './ReviewForm';

interface PlaceDetailsProps {
  place: any;
  onClose: () => void;
  onToggleFavorite: (id: number) => void;
  isFavorite: boolean;
  onAddToGoogleMaps: (place: any) => void;
  isAuthenticated: boolean;
}

const PlaceDetails: React.FC<PlaceDetailsProps> = ({
  place,
  onClose,
  onToggleFavorite,
  isFavorite,
  onAddToGoogleMaps,
  isAuthenticated
}) => {
  const [reviews, setReviews] = useState<any[]>([]);
  const [showReviewForm, setShowReviewForm] = useState(false);

  const fetchReviews = async () => {
    try {
      const res = await axios.get(`/api/reviews/${place.id}`);
      setReviews(res.data);
    } catch (err) {
      console.error('Failed to fetch reviews', err);
    }
  };

  useEffect(() => {
    if (place) {
      fetchReviews();
      setShowReviewForm(false);
    }
  }, [place]);

  if (!place) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-white rounded-t-3xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom duration-300 md:left-4 md:bottom-4 md:w-96 md:rounded-3xl max-h-[80vh] flex flex-col">
      <div className="relative h-48 bg-gray-200 shrink-0">
        <img
          src={place.photo_url || 'https://images.unsplash.com/photo-1523987355523-c7b5b0dd90a7?auto=format&fit=crop&q=80&w=800'}
          alt={place.titre}
          className="w-full h-full object-cover"
        />
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-2 bg-white/80 backdrop-blur rounded-full shadow-md"
        >
          <X size={20} />
        </button>
      </div>

      <div className="p-6 overflow-y-auto">
        <div className="flex justify-between items-start mb-2">
          <h2 className="text-2xl font-bold">{place.titre}</h2>
          <button
            onClick={() => onToggleFavorite(place.id)}
            className={`p-2 rounded-full border ${isFavorite ? 'bg-red-50 border-red-200 text-red-500' : 'bg-gray-50 border-gray-100 text-gray-400'}`}
          >
            <Heart size={20} fill={isFavorite ? 'currentColor' : 'none'} />
          </button>
        </div>

        <div className="flex items-center text-sm text-gray-500 mb-4">
          <Star className="text-yellow-400 fill-current mr-1" size={16} />
          <span className="font-bold text-gray-900 mr-1">{place.note_moyenne || '0'}</span>
          <span>({place.nb_commentaires || 0} reviews)</span>
          <span className="mx-2">•</span>
          <span className="bg-blue-50 text-blue-600 px-2 py-0.5 rounded text-xs font-semibold">
            {place.code_type}
          </span>
        </div>

        <div className="flex items-center text-gray-600 mb-4">
          <MapPin size={18} className="mr-2 shrink-0" />
          <p className="text-sm">{place.adresse}</p>
        </div>

        <div className="flex gap-2 mt-6">
          <button
            className="flex-1 bg-blue-600 text-white py-3 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-blue-700 transition-colors"
            onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
          >
            <Navigation size={18} />
            Directions
          </button>
          <button
            className="px-4 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
            onClick={() => onAddToGoogleMaps(place)}
            title="Add to Google Maps"
          >
            <ExternalLink size={18} className="text-gray-600" />
          </button>
        </div>

        <div className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-lg flex items-center gap-2">
              <MessageSquare size={20} />
              Reviews
            </h3>
            {isAuthenticated && !showReviewForm && (
              <button
                onClick={() => setShowReviewForm(true)}
                className="text-blue-600 text-sm font-semibold"
              >
                Write a review
              </button>
            )}
          </div>

          {showReviewForm && (
            <ReviewForm
              placeId={place.id}
              onSuccess={() => {
                setShowReviewForm(false);
                fetchReviews();
              }}
            />
          )}

          <div className="space-y-4 mt-4">
            {reviews.map((review) => (
              <div key={review.id} className="border-b border-gray-100 pb-4 last:border-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-sm">{review.user?.name || 'Anonymous'}</span>
                  <div className="flex">
                    {[...Array(5)].map((_, i) => (
                      <Star key={i} size={12} className={i < review.rating ? 'text-yellow-400 fill-current' : 'text-gray-300'} />
                    ))}
                  </div>
                </div>
                <p className="text-sm text-gray-600">{review.content}</p>
              </div>
            ))}
            {reviews.length === 0 && <p className="text-sm text-gray-400 italic">No local reviews yet.</p>}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
