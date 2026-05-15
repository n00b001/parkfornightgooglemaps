/**
 * Utility to add a point to user's Google Maps by generating a Save URL
 * or opening in a way that allows saving.
 */
export const addToGoogleMaps = (place: any) => {
  const { latitude, longitude, titre } = place;

  // Google Maps Search URL which usually prompts user with a "Save" button
  const query = encodeURIComponent(`${titre} @${latitude},${longitude}`);
  const url = `https://www.google.com/maps/search/?api=1&query=${query}`;

  window.open(url, '_blank');
};
