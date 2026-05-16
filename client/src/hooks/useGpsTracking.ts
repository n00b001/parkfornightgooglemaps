import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

export const useGpsTracking = (places: any[], isAuthenticated: boolean) => {
  const visitedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!navigator.geolocation || !isAuthenticated) return;

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        places.forEach(async (place) => {
          if (visitedRef.current.has(place.id)) return;
          const dist = calculateDistance(latitude, longitude, parseFloat(place.latitude), parseFloat(place.longitude));
          if (dist < 0.1) { // 100 meters
            try {
              visitedRef.current.add(place.id);
              await axios.post('/api/visits', { placeId: place.id });
            } catch (err) {
              visitedRef.current.delete(place.id);
            }
          }
        });
      },
      null,
      { enableHighAccuracy: true }
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, [places, isAuthenticated]);
};

function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}
