import { useEffect, useRef } from 'react';
import axios from '../axiosConfig';
import { savePendingVisit } from '../services/db';
import { Place } from '../types';

export const useGpsTracking = (places: Place[], isAuthenticated: boolean, initialVisitedIds: number[] = []) => {
  const visitedRef = useRef<Set<number>>(new Set(initialVisitedIds));
  const placesRef = useRef<Place[]>(places);

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
      (position) => {
        const { latitude, longitude } = position.coords;
        placesRef.current.forEach(async (place) => {
          if (visitedRef.current.has(place.id)) return;
          const dist = calculateDistance(latitude, longitude, parseFloat(place.latitude.toString()), parseFloat(place.longitude.toString()));
          if (dist < 0.1) { // 100 meters
            try {
              visitedRef.current.add(place.id);
              if (navigator.onLine) {
                await axios.post('/api/visits', { placeId: place.id });
              } else {
                await savePendingVisit(place.id);
              }
            } catch (err) {
              await savePendingVisit(place.id);
            }
          }
        });
      },
      null,
      { enableHighAccuracy: true }
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
