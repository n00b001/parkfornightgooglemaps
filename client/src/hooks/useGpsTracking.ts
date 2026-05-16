import { useEffect, useRef } from 'react';
import axios from 'axios';

export const useGpsTracking = (places: any[], isAuthenticated: boolean) => {
  const visitedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!navigator.geolocation || !isAuthenticated || places.length === 0) return;

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords;

        places.forEach(async (place) => {
          if (visitedRef.current.has(place.id)) return;

          const dist = calculateDistance(
            latitude,
            longitude,
            parseFloat(place.latitude),
            parseFloat(place.longitude)
          );

          // If within 100 meters (0.1 km)
          if (dist < 0.1) {
            try {
              visitedRef.current.add(place.id);
              await axios.post('/api/visits', { placeId: place.id });
              console.log(`Automatically recorded visit to: ${place.name}`);
            } catch (err) {
              // If failed, allow retry in next position update
              visitedRef.current.delete(place.id);
              console.error('Failed to record visit:', err);
            }
          }
        });
      },
      (error) => {
        console.error('Geolocation error:', error);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [places, isAuthenticated]);
};

/**
 * Calculates distance between two points using Haversine formula
 * @returns distance in kilometers
 */
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371; // Earth's radius in km
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a =
    Math.sin(dLat/2) * Math.sin(dLat/2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}
