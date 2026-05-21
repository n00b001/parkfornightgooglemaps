import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, Map, Droplets, Zap, Trash2, Wifi, Info, Bath, Waves } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';

const AMENITIES = [
  { key: 'point_eau', label: 'Water', icon: Droplets, color: 'text-blue-500' },
  { key: 'electricite', label: 'Electricity', icon: Zap, color: 'text-yellow-500' },
  { key: 'poubelle', label: 'Trash', icon: Trash2, color: 'text-green-600' },
  { key: 'wifi', label: 'Wifi', icon: Wifi, color: 'text-purple-500' },
  { key: 'vidange_eaux_usees', label: 'Grey Water', icon: Info, color: 'text-gray-500' },
  { key: 'vidange_wc', label: 'Black Water', icon: Info, color: 'text-gray-700' },
  { key: 'douche', label: 'Shower', icon: Bath, color: 'text-blue-400' },
  { key: 'baignade', label: 'Waves', icon: Waves, color: 'text-cyan-500' },
];

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
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
    // Attempt to find the place on Google Maps using search with specific coordinates
    // This often triggers the "Save" and "Sidebar" UI for the specific place if Google can match it
    const query = encodeURIComponent(`${place.titre || place.name} ${place.adresse || ''}`);
    const url = `https://www.google.com/maps/search/?api=1&query=${query}&query_place_id=${place.google_place_id || ''}`;
    window.open(url, '_blank');
  };

  const openStreetView = () => {
    const url = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const photos = place.photos || [];

  return (
    <div className="fixed bottom-4 left-4 right-4 md:w-[450px] z-40 bg-white rounded-3xl shadow-2xl overflow-hidden max-h-[85vh] flex flex-col">
      {photos.length > 0 && (
        <div className="h-48 overflow-x-auto flex gap-1 snap-x bg-gray-100">
          {photos.map((p: any, idx: number) => (
            <img key={idx} src={p.lien_mini} alt={`Spot ${idx}`} className="h-full object-cover snap-center min-w-[80%]" />
          ))}
        </div>
      )}
      <div className="p-6 overflow-y-auto flex-1">
      <div className="flex justify-between mb-2">
        <h2 className="text-2xl font-bold">{place.titre || place.name}</h2>
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

      <div className="flex flex-col gap-3">
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
        </div>
        <div className="flex gap-2">
          <button
            onClick={openStreetView}
            className="flex-1 border border-gray-200 py-3 rounded-2xl font-bold hover:bg-gray-50 transition-colors flex items-center justify-center gap-2"
          >
            <Map size={18} /> Street View
          </button>
          <button
            onClick={addToGoogleMaps}
            className="flex-1 border border-green-200 bg-green-50 text-green-700 py-3 rounded-2xl font-bold hover:bg-green-100 transition-colors flex items-center justify-center gap-2"
            title="Open in Google Maps / Save to List"
          >
            <ExternalLink size={18} /> Google Maps
          </button>
        </div>
      </div>

      <div className="mt-6">
        <h3 className="text-xs font-bold text-gray-400 uppercase mb-2">Amenities</h3>
        <div className="grid grid-cols-4 gap-2">
          {AMENITIES.map(amenity => {
            const hasAmenity = place[amenity.key] === '1';
            if (!hasAmenity) return null;
            return (
              <div key={amenity.key} className="flex flex-col items-center p-2 bg-gray-50 rounded-xl border border-gray-100">
                <amenity.icon size={20} className={amenity.color} />
                <span className="text-[10px] mt-1 font-medium text-center">{amenity.label}</span>
              </div>
            );
          })}
          {!AMENITIES.some(a => place[a.key] === '1') && <p className="text-sm text-gray-400 italic col-span-4">No amenity info available.</p>}
        </div>
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
          {isLoadingReviews ? (
            <div className="space-y-3 animate-pulse">
              {[1, 2].map(i => (
                <div key={i} className="h-20 bg-gray-100 rounded-xl" />
              ))}
            </div>
          ) : (
            <>
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
          </>
          )}
        </div>
      </div>
      </div>
    </div>
  );
};

export default PlaceDetails;
