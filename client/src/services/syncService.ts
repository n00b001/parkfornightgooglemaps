import axios from '../axiosConfig';
import {
  getOfflineReviews,
  deleteOfflineReview,
  getOfflineVisits,
  deleteOfflineVisit
} from './db';

export const syncOfflineData = async () => {
  if (!navigator.onLine) return;

  // Sync reviews
  const offlineReviews = await getOfflineReviews();
  for (const review of offlineReviews) {
    try {
      const { tempId, ...reviewData } = review;
      await axios.post('/api/reviews', reviewData);
      await deleteOfflineReview(tempId);
    } catch (err) {
      console.error('Failed to sync review:', err);
    }
  }

  // Sync visits
  const offlineVisits = await getOfflineVisits();
  for (const visit of offlineVisits) {
    try {
      await axios.post('/api/visits', { placeId: visit.placeId });
      await deleteOfflineVisit(visit.placeId);
    } catch (err) {
      console.error('Failed to sync visit:', err);
    }
  }
};

window.addEventListener('online', syncOfflineData);
