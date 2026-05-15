import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

export const useGpsTracking = (places: any[], isAuthenticated: boolean) => {
  const [currentPosition, setCurrentPosition] = useState<{ lat: number, lng: number } | null>(null);
  const visitedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!navigator.geolocation) return;

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        setCurrentPosition({ lat: latitude, lng: longitude });

        // Check if user is near any parking spot (within 100 meters)
        if (isAuthenticated && places.length > 0) {
          places.forEach(async (place) => {
            if (visitedRef.current.has(place.id)) return;

            const distance = calculateDistance(
              latitude,
              longitude,
              parseFloat(place.latitude),
              parseFloat(place.longitude)
            );

            if (distance < 0.1) { // 100 meters
              try {
                visitedRef.current.add(place.id);
                await axios.post('/api/visits', { placeId: place.id });
                console.log(`Automatically recorded visit to ${place.titre}`);
              } catch (err) {
                console.error('Failed to record automatic visit', err);
                visitedRef.current.delete(place.id); // Retry next time
              }
            }
          });
        }
      },
      (error) => console.error('GPS tracking error:', error),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [places, isAuthenticated]);

  return currentPosition;
};

// Haversine formula to calculate distance in km
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371; // Radius of the earth in km
  const dLat = deg2rad(lat2 - lat1);
  const dLon = deg2rad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const d = R * c; // Distance in km
  return d;
}

function deg2rad(deg: number) {
  return deg * (Math.PI / 180);
}
