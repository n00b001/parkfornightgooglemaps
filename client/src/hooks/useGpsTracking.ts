import { useEffect, useRef } from 'react';
import axios from '../axiosConfig';
import { savePendingVisit } from '../services/db';

export const useGpsTracking = (places: any[], isAuthenticated: boolean, initialVisitedIds: number[] = []) => {
  const visitedRef = useRef<Set<number>>(new Set(initialVisitedIds));
  const placesRef = useRef<any[]>(places);

  useEffect(() => {
    placesRef.current = places;
  }, [places]);

  useEffect(() => {
    if (initialVisitedIds.length > 0) {
      initialVisitedIds.forEach(id => visitedRef.current.add(id));
    }
  }, [initialVisitedIds]);

  useEffect(() => {
    if (!navigator.geolocation || !isAuthenticated) return;

    const watchId = navigator.geolocation.watchPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        for (const place of placesRef.current) {
          if (visitedRef.current.has(place.id)) continue;

          const placeLat = parseFloat(place.latitude);
          const placeLng = parseFloat(place.longitude);

          const dist = calculateDistance(latitude, longitude, placeLat, placeLng);

          if (dist < 0.1) { // 100 meters
            visitedRef.current.add(place.id);
            try {
              if (navigator.onLine) {
                await axios.post('/api/visits', { placeId: place.id });
              } else {
                await savePendingVisit(place.id);
              }
            } catch (err) {
              console.error('Failed to record visit, saving to pending', err);
              await savePendingVisit(place.id);
            }
          }
        }
      },
      (error) => console.error('GPS error:', error),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [isAuthenticated]); // Only restart if auth status changes
};

function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}
