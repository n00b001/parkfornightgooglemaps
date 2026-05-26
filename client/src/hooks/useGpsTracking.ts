import { useEffect, useRef } from 'react';
import axios from '../axiosConfig';
import { savePendingVisit } from '../services/db';

export const useGpsTracking = (places: any[], isAuthenticated: boolean, initialVisitedIds: number[] = [], onVisitRecorded?: (placeId: number) => void) => {
  const visitedRef = useRef<Set<number>>(new Set(initialVisitedIds));
  const placesRef = useRef<any[]>(places);
  const onVisitRecordedRef = useRef(onVisitRecorded);

  useEffect(() => {
    onVisitRecordedRef.current = onVisitRecorded;
  }, [onVisitRecorded]);

  useEffect(() => {
    placesRef.current = places;
  }, [places]);

  useEffect(() => {
    // Append initialVisitedIds from server to our local set
    // We don't overwrite to avoid losing spots recorded locally but not yet synced/refetched
    initialVisitedIds.forEach(id => visitedRef.current.add(id));
  }, [initialVisitedIds]);

  useEffect(() => {
    if (!navigator.geolocation || !isAuthenticated) return;

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        placesRef.current.forEach(async (place) => {
          if (visitedRef.current.has(place.id)) return;
          const dist = calculateDistance(latitude, longitude, parseFloat(place.latitude), parseFloat(place.longitude));
          if (dist < 0.1) { // 100 meters
            visitedRef.current.add(place.id);
            if (onVisitRecordedRef.current) onVisitRecordedRef.current(place.id);
            try {
              await axios.post('/api/visits', { placeId: place.id });
            } catch (err) {
              console.warn('Failed to record visit online, saving to pending', err);
              await savePendingVisit(place.id);
            }
          }
        });
      },
      null,
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, [isAuthenticated]);
};

function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}
