import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink } from 'lucide-react';
import axios from 'axios';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [reviews, setReviews] = useState<any[]>([]);

  const fetchReviews = async () => {
    try {
      const res = await axios.get(`/api/reviews/${place.id}`);
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
    <div className="fixed bottom-4 left-4 right-4 md:w-96 z-40 bg-white rounded-3xl shadow-2xl p-6 max-h-[80vh] overflow-y-auto">
      <div className="flex justify-between mb-2">
        <h2 className="text-2xl font-bold">{place.titre}</h2>
        <button onClick={onClose}><X size={20} /></button>
      </div>
      <p className="text-sm text-gray-500 mb-4">{place.adresse}</p>
      <div className="flex gap-2">
        <button
          onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
          className="flex-1 bg-blue-600 text-white py-3 rounded-xl font-bold flex items-center justify-center gap-2"
        >
          <Navigation size={18} /> Directions
        </button>
        <button onClick={onToggleFavorite} className="p-3 border rounded-xl">
          <Heart size={20} fill={isFavorite ? 'red' : 'none'} />
        </button>
        <button onClick={addToGoogleMaps} className="p-3 border rounded-xl" title="Save to Google Maps">
          <ExternalLink size={20} />
        </button>
      </div>

      <div className="mt-6 border-t pt-4">
        <h3 className="font-bold mb-2 flex items-center gap-2"><MessageSquare size={18} /> Reviews</h3>
        {isAuthenticated && <ReviewForm placeId={place.id} onSuccess={fetchReviews} />}
        <div className="mt-4 space-y-3">
          {reviews.map(r => (
            <div key={r.id} className="text-sm border-b pb-2">
              <div className="font-bold">{r.user?.name}</div>
              <p>{r.content}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
