import React, { useState, useEffect } from 'react';
import { Heart, Navigation, X, MessageSquare, ExternalLink, Star, Map, Droplets, Zap, Trash2, Wifi, Info, Bath, Waves, Eye, Dog, Utensils, Shirt, Share2, Compass } from 'lucide-react';
import axios from '../axiosConfig';
import ReviewForm from './ReviewForm';
import { saveReviews, getCachedReviews } from '../services/db';

const getStreetViewUrl = (lat: number, lng: number) => {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
  if (!apiKey) return null;
  return `https://maps.googleapis.com/maps/api/streetview?size=800x400&location=${lat},${lng}&fov=100&heading=215&pitch=0&key=${apiKey}`;
};

// English type keys (must match server TYPE_CODE_MAP values)
const TYPE_NAMES: Record<string, string> = {
  rvPark: 'RV Park',
  parking: 'Parking',
  naturalParking: 'Natural Parking',
  campsite: 'Campsite',
  freeRvPark: 'Free RV Park',
  restArea: 'Rest Area',
  onSiteParking: 'On-Site Parking',
  serviceArea: 'Service Area',
  private: 'Private',
  paid: 'Paid',
  closed: 'Closed',
};

const TYPE_COLORS: Record<string, string> = {
  rvPark: 'bg-blue-100 text-blue-700',
  parking: 'bg-gray-100 text-gray-700',
  naturalParking: 'bg-emerald-100 text-emerald-700',
  campsite: 'bg-green-100 text-green-700',
  freeRvPark: 'bg-teal-100 text-teal-700',
  restArea: 'bg-purple-100 text-purple-700',
  onSiteParking: 'bg-indigo-100 text-indigo-700',
  serviceArea: 'bg-orange-100 text-orange-700',
  private: 'bg-amber-100 text-amber-700',
  paid: 'bg-yellow-100 text-yellow-700',
  closed: 'bg-red-100 text-red-700',
};

// English amenity keys with their raw P4N counterparts
const AMENITIES = [
  { key: 'waterPoint', raw: 'point_eau', label: 'Water', icon: Droplets, color: 'text-blue-500' },
  { key: 'electricity', raw: 'electricite', label: 'Electricity', icon: Zap, color: 'text-yellow-500' },
  { key: 'trashCan', raw: 'poubelle', label: 'Trash', icon: Trash2, color: 'text-green-600' },
  { key: 'wifi', raw: 'wifi', label: 'Wifi', icon: Wifi, color: 'text-purple-500' },
  { key: 'wasteWaterDrain', raw: 'vidange_eaux_usees', label: 'Grey Water', icon: Info, color: 'text-gray-500' },
  { key: 'toiletDrain', raw: 'vidange_wc', label: 'Black Water', icon: Compass, color: 'text-gray-700' },
  { key: 'shower', raw: 'douche', label: 'Shower', icon: Bath, color: 'text-blue-400' },
  { key: 'swimming', raw: 'baignade', label: 'Waves', icon: Waves, color: 'text-cyan-500' },
  { key: 'pets', raw: 'animaux', label: 'Pets', icon: Dog, color: 'text-orange-400' },
  { key: 'picnicArea', raw: 'aire_pique_nique', label: 'Picnic', icon: Utensils, color: 'text-green-500' },
  { key: 'laundry', raw: 'laverie', label: 'Laundry', icon: Shirt, color: 'text-indigo-400' },
  { key: 'publicToilet', raw: 'wc_public', label: 'Public WC', icon: Map, color: 'text-blue-300' },
];

const PlaceDetails: React.FC<any> = ({ place, onClose, onToggleFavorite, isFavorite, isAuthenticated }) => {
  const [reviews, setReviews] = useState<any[]>([]);
  const [p4nReviews, setP4nReviews] = useState<any[]>([]);
  const [isLoadingReviews, setIsLoadingReviews] = useState(false);
  const [googleDetails, setGoogleDetails] = useState<any>(null);
  const [streetViewAvailable, setStreetViewAvailable] = useState(false);
  const [streetViewError, setStreetViewError] = useState(false);

  const checkStreetViewAvailability = () => {
    if (!window.google || !window.google.maps) return;

    const svService = new google.maps.StreetViewService();
    const location = new google.maps.LatLng(
      parseFloat(place.latitude),
      parseFloat(place.longitude)
    );

    svService.getPanorama(
      { location, radius: 500 },
      (data, status) => {
        if (status === google.maps.StreetViewStatus.OK && data) {
          setStreetViewAvailable(true);
        } else {
          setStreetViewAvailable(false);
        }
      }
    );
  };

  const fetchGoogleDetails = () => {
    if (!window.google || !window.google.maps || !window.google.maps.places) return;

    const service = new google.maps.places.PlacesService(document.createElement('div'));
    const request = {
      location: new google.maps.LatLng(parseFloat(place.latitude), parseFloat(place.longitude)),
      radius: 50,
      keyword: place.title || place.name
    };

    service.nearbySearch(request, (results, status) => {
      if (status === google.maps.places.PlacesServiceStatus.OK && results && results[0]) {
        const placeId = results[0].place_id;
        if (placeId) {
          service.getDetails({ placeId, fields: ['rating', 'user_ratings_total', 'reviews', 'url', 'place_id'] }, (details, detailStatus) => {
            if (detailStatus === google.maps.places.PlacesServiceStatus.OK) {
              setGoogleDetails(details);
            }
          });
        }
      }
    });
  };

  const fetchReviews = async () => {
    setIsLoadingReviews(true);
    try {
      const [localRes, p4nRes] = await Promise.all([
        axios.get(`/api/reviews/${place.id}`),
        axios.get(`/api/places/${place.id}/reviews`)
      ]);
      const local = localRes.data;
      const p4n = p4nRes.data?.reviews || [];
      setReviews(local);
      setP4nReviews(p4n);
      await saveReviews(place.id, { local, p4n });
    } catch (err) {
      console.error('Failed to fetch reviews, trying cache', err);
      const cached = await getCachedReviews(place.id);
      if (cached) {
        setReviews(cached.local || []);
        setP4nReviews(cached.p4n || []);
      }
    } finally {
      setIsLoadingReviews(false);
    }
  };

  useEffect(() => {
    if (place) {
      fetchReviews();
      fetchGoogleDetails();
      checkStreetViewAvailability();
    }
  }, [place]);

  const addToGoogleMaps = () => {
    // If we have a direct Google Maps URL from Places API, use it!
    if (googleDetails?.url) {
      window.open(googleDetails.url, '_blank');
      return;
    }

    const googlePlaceId = googleDetails?.place_id || place.google_place_id || place.rawData?.google_place_id;
    const query = encodeURIComponent(`${place.title || place.name} ${place.address || ''}`);
    const url = googlePlaceId
      ? `https://www.google.com/maps/search/?api=1&query=${query}&query_place_id=${googlePlaceId}`
      : `https://www.google.com/maps/search/?api=1&query=${query}`;
    window.open(url, '_blank');
  };

  const openStreetView = () => {
    const url = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${place.latitude},${place.longitude}`;
    window.open(url, '_blank');
  };

  const sharePlace = async () => {
    const url = new URL(window.location.origin);
    url.searchParams.set('place', place.id.toString());
    const shareData = {
      title: place.title || place.name,
      text: `Check out this parking spot on Park4Night: ${place.title || place.name}`,
      url: url.toString(),
    };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
      } catch (err) {
        console.error('Share failed', err);
      }
    } else {
      await navigator.clipboard.writeText(`${shareData.title} - ${shareData.url}`);
      alert('Link copied to clipboard!');
    }
  };

  const photos = place.photos || [];

  return (
    <div className="fixed bottom-4 left-4 right-4 md:w-[450px] z-40 bg-white rounded-3xl shadow-2xl overflow-hidden max-h-[85vh] flex flex-col">
      {photos.length > 0 && (
        <div className="h-48 overflow-x-auto flex gap-1 snap-x bg-gray-100">
          {photos.map((p: any, idx: number) => (
            <img key={idx} src={p.thumbUrl || p.lien_mini} alt={`Spot ${idx}`} className="h-full object-cover snap-center min-w-[80%]" />
          ))}
        </div>
      )}

      {/* Street View Embed */}
      {streetViewAvailable && getStreetViewUrl(parseFloat(place.latitude), parseFloat(place.longitude)) && (
        <div className="relative h-40 bg-gray-900">
          <img
            src={getStreetViewUrl(parseFloat(place.latitude), parseFloat(place.longitude))!}
            alt="Street View preview"
            className="w-full h-full object-cover"
            onError={() => setStreetViewError(true)}
          />
          {!streetViewError && (
            <div className="absolute bottom-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded-lg flex items-center gap-1">
              <Eye size={12} />
              <span>Street View</span>
            </div>
          )}
        </div>
      )}
      <div className="p-6 overflow-y-auto flex-1">
      <div className="flex justify-between items-start mb-1">
        <div>
          <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-full uppercase mb-2 ${TYPE_COLORS[place.type || ''] || 'bg-gray-100 text-gray-600'}`}>
            {TYPE_NAMES[place.type || ''] || 'Spot'}
          </span>
          <h2 className="text-2xl font-bold leading-tight">{place.title || place.name}</h2>
        </div>
        <div className="flex gap-2">
          <button onClick={sharePlace} className="p-1 text-gray-500 hover:text-blue-600 transition-colors">
            <Share2 size={20} />
          </button>
          <button onClick={onClose} className="p-1 text-gray-500 hover:text-black transition-colors">
            <X size={20} />
          </button>
        </div>
      </div>
      <div className="flex items-center gap-4 mb-1">
        <div className="flex items-center gap-1">
          <Star size={16} fill="orange" className="text-orange-500" />
          <span className="font-bold">{place.rating ?? 'N/A'}</span>
          <span className="text-gray-400 text-xs">({place.reviewCount ?? 0} p4n)</span>
        </div>
        {googleDetails && (
          <div className="flex items-center gap-1.5 bg-blue-50 px-2 py-1 rounded-lg">
            <Star size={16} fill="#3B82F6" className="text-blue-500" />
            <span className="font-bold text-blue-700">{googleDetails.rating}</span>
            <span className="text-blue-400 text-xs font-medium">({googleDetails.user_ratings_total})</span>
          </div>
        )}
      </div>
      <p className="text-sm text-gray-500 mb-4">{place.address}</p>

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
        <div className="grid grid-cols-4 gap-3">
          {AMENITIES.map(amenity => {
            // Check in top level (Prisma), rawData (Live/Local), or original raw key in rawData
            const hasAmenity =
              place[amenity.key] === '1' ||
              place.rawData?.[amenity.key] === '1' ||
              place.rawData?.[amenity.raw] === '1' ||
              place.rawData?.[amenity.raw] === true;

            if (!hasAmenity) return null;
            return (
              <div key={amenity.key} className="flex flex-col items-center p-3 bg-white rounded-2xl border border-gray-100 shadow-sm hover:border-blue-200 transition-colors">
                <amenity.icon size={20} className={`${amenity.color} mb-1`} />
                <span className="text-[10px] font-bold text-gray-600 text-center leading-tight">{amenity.label}</span>
              </div>
            );
          })}
          {!AMENITIES.some(a => (
            place[a.key] === '1' ||
            place.rawData?.[a.key] === '1' ||
            place.rawData?.[a.raw] === '1' ||
            place.rawData?.[a.raw] === true
          )) && <p className="text-sm text-gray-400 italic col-span-4">No amenity info available.</p>}
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
                      <span className="font-bold">{r.author}</span>
                      <span className="text-orange-500 font-bold">{r.rating}/5</span>
                    </div>
                    <p className="text-gray-600 italic">"{r.content}"</p>
                    {r.needsTranslation && (
                      <span className="text-[10px] text-gray-400 italic">(original language)</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {googleDetails?.reviews && googleDetails.reviews.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-blue-600 uppercase mb-2">Google Reviews</h4>
              <div className="space-y-3">
                {googleDetails.reviews.slice(0, 3).map((r: any, idx: number) => (
                  <div key={idx} className="text-sm bg-gray-50 p-3 rounded-xl border border-gray-100">
                    <div className="flex justify-between mb-1">
                      <span className="font-bold">{r.author_name}</span>
                      <span className="text-blue-600 font-bold">{r.rating}/5</span>
                    </div>
                    <p className="text-gray-600 italic">"{r.text.substring(0, 150)}{r.text.length > 150 ? '...' : ''}"</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {reviews.length === 0 && p4nReviews.length === 0 && !googleDetails?.reviews?.length && (
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
