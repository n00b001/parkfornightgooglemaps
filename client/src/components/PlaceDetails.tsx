import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, Droplets, Zap, Trash2, CheckCircle, MapPin, Camera } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated, isVisited }) => {
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
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.titre || place.name)}@${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const amenities = [
    { key: 'point_eau', label: 'Water', icon: <Droplets size={16} className="text-blue-500" /> },
    { key: 'electricite', label: 'Electricity', icon: <Zap size={16} className="text-yellow-500" /> },
    { key: 'poubelle', label: 'Trash', icon: <Trash2 size={16} className="text-gray-500" /> },
    { key: 'vidange_eaux_usees', label: 'Grey Water', icon: <Droplets size={16} className="text-gray-400" /> },
    { key: 'vidange_wc', label: 'WC Disposal', icon: <Droplets size={16} className="text-brown-500" /> },
  ].filter(a => place[a.key] === "1" || place.rawData?.[a.key] === "1");

  const photos = place.photos || place.rawData?.photos || [];

  return (
    <div className="fixed bottom-4 left-4 right-4 md:w-96 z-40 bg-white rounded-3xl shadow-2xl p-0 max-h-[85vh] overflow-y-auto">
      {/* Header Image / Gallery */}
      <div className="relative h-48 w-full bg-gray-200 rounded-t-3xl overflow-hidden">
        {photos.length > 0 ? (
          <img src={photos[0].m || photos[0].url} alt={place.titre} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400">
            <Camera size={48} />
          </div>
        )}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-black/50 text-white rounded-full hover:bg-black/70 transition-colors"
        >
          <X size={20} />
        </button>
        {isVisited && (
          <div className="absolute top-4 left-4 bg-green-500 text-white px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1 shadow-lg">
            <CheckCircle size={12} /> Visited
          </div>
        )}
      </div>

      <div className="p-6">
        <div className="flex justify-between items-start mb-2">
          <h2 className="text-2xl font-bold leading-tight">{place.titre || place.name}</h2>
        </div>

        <div className="flex items-center gap-1 mb-2">
          <Star size={16} fill="orange" className="text-orange-500" />
          <span className="font-bold text-lg">{place.note_moyenne || 'N/A'}</span>
          <span className="text-gray-400 text-sm">({place.nb_comm || 0} reviews)</span>
        </div>

        <div className="flex items-start gap-1 text-sm text-gray-500 mb-4">
          <MapPin size={16} className="mt-0.5 flex-shrink-0" />
          <p>{place.adresse}</p>
        </div>

        {amenities.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {amenities.map(a => (
              <div key={a.key} className="flex items-center gap-1 bg-gray-50 px-2 py-1 rounded-lg border border-gray-100" title={a.label}>
                {a.icon}
                <span className="text-xs font-medium text-gray-600">{a.label}</span>
              </div>
            ))}
          </div>
        )}

        {place.description && (
          <div className="mb-6">
            <p className="text-sm text-gray-700 leading-relaxed">{place.description}</p>
          </div>
        )}

        <div className="flex gap-2 mb-8">
          <button
            onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`)}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-2xl font-bold transition-all flex items-center justify-center gap-2 shadow-lg shadow-blue-200 active:scale-95"
          >
            <Navigation size={18} /> Directions
          </button>
          <button
            onClick={onToggleFavorite}
            className="p-3 border rounded-2xl hover:bg-gray-50 transition-colors active:scale-95"
            title={isFavorite ? "Remove from Favorites" : "Add to Favorites"}
          >
            <Heart size={20} fill={isFavorite ? '#EF4444' : 'none'} color={isFavorite ? '#EF4444' : 'currentColor'} />
          </button>
          <button
            onClick={addToGoogleMaps}
            className="p-3 border border-green-200 bg-green-50 text-green-700 rounded-2xl hover:bg-green-100 transition-colors active:scale-95"
            title="Open in Google Maps / Save to List"
          >
            <ExternalLink size={20} />
          </button>
        </div>

        {/* Photo Gallery if more than 1 photo */}
        {photos.length > 1 && (
          <div className="mb-8">
            <h3 className="font-bold mb-3 text-gray-900">Gallery</h3>
            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
              {photos.slice(1, 6).map((photo: any, idx: number) => (
                <img
                  key={idx}
                  src={photo.m || photo.url}
                  alt={`Gallery ${idx}`}
                  className="h-24 w-24 object-cover rounded-xl flex-shrink-0 bg-gray-100"
                />
              ))}
            </div>
          </div>
        )}

        <div className="border-t pt-6">
          <h3 className="font-bold mb-4 flex items-center gap-2 text-gray-900"><MessageSquare size={18} /> Reviews</h3>

          {isAuthenticated && (
            <div className="mb-6">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">Share your experience</h4>
              <ReviewForm placeId={place.id} onSuccess={fetchReviews} />
            </div>
          )}

          <div className="space-y-6">
            {isLoadingReviews ? (
              <div className="space-y-4 animate-pulse">
                {[1, 2].map(i => (
                  <div key={i} className="h-24 bg-gray-50 rounded-2xl" />
                ))}
              </div>
            ) : (
              <>
                {reviews.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold text-blue-500 uppercase tracking-wider mb-3">Community Reviews</h4>
                    <div className="space-y-4">
                      {reviews.map(r => (
                        <div key={r.id} className="text-sm bg-blue-50/30 p-4 rounded-2xl border border-blue-100/50">
                          <div className="flex justify-between items-center mb-2">
                            <span className="font-bold text-blue-900">{r.user?.name}</span>
                            <div className="flex gap-0.5">
                              {[...Array(5)].map((_, i) => (
                                <Star key={i} size={12} fill={i < r.rating ? '#F59E0B' : 'none'} stroke={i < r.rating ? '#F59E0B' : '#94A3B8'} />
                              ))}
                            </div>
                          </div>
                          <p className="text-gray-700 leading-relaxed">{r.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {p4nReviews.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">Park4Night Reviews</h4>
                    <div className="space-y-4">
                      {p4nReviews.map((r, idx) => (
                        <div key={idx} className="text-sm border-b border-gray-100 pb-4 last:border-0">
                          <div className="flex justify-between items-center mb-1">
                            <span className="font-bold text-gray-900">{r.auteur}</span>
                            <div className="flex items-center gap-1">
                              <Star size={12} fill="#F59E0B" className="text-yellow-500" />
                              <span className="text-orange-500 font-bold">{r.note}/5</span>
                            </div>
                          </div>
                          <p className="text-gray-600 italic leading-relaxed">"{r.texte}"</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {reviews.length === 0 && p4nReviews.length === 0 && (
                  <div className="text-center py-8">
                    <MessageSquare size={32} className="mx-auto text-gray-200 mb-2" />
                    <p className="text-sm text-gray-400 italic">Be the first to leave a review!</p>
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
