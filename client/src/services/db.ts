import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night-db';
const STORES = {
  PLACES: 'places',
  REVIEWS: 'reviews',
  VISITS: 'visits',
  PENDING_VISITS: 'pending-visits',
};

export const initDB = async (): Promise<IDBPDatabase> => {
  return openDB(DB_NAME, 3, {
    upgrade(db, oldVersion) {
      if (oldVersion < 1) {
        db.createObjectStore(STORES.PLACES, { keyPath: 'id' });
      }
      if (oldVersion < 2) {
        db.createObjectStore(STORES.REVIEWS, { keyPath: 'id' });
        db.createObjectStore(STORES.VISITS, { keyPath: 'id' });
      }
      if (oldVersion < 3) {
        if (!db.objectStoreNames.contains(STORES.PENDING_VISITS)) {
          db.createObjectStore(STORES.PENDING_VISITS, { keyPath: 'placeId' });
        }
      }
    },
  });
};

export const savePlaces = async (places: any[]) => {
  const db = await initDB();
  const tx = db.transaction(STORES.PLACES, 'readwrite');
  for (const place of places) {
    await tx.store.put(place);
  }
  await tx.done;
};

export const getCachedPlaces = async (): Promise<any[]> => {
  const db = await initDB();
  return db.getAll(STORES.PLACES);
};

export const saveReviews = async (placeId: number, reviews: any) => {
  const db = await initDB();
  await db.put(STORES.REVIEWS, { id: placeId, reviews, timestamp: Date.now() });
};

export const getCachedReviews = async (placeId: number): Promise<any | null> => {
  const db = await initDB();
  const data = await db.get(STORES.REVIEWS, placeId);
  return data ? data.reviews : null;
};

export const savePendingVisit = async (placeId: number) => {
  const db = await initDB();
  await db.put(STORES.PENDING_VISITS, { placeId, timestamp: Date.now() });
};

export const getPendingVisits = async (): Promise<any[]> => {
  const db = await initDB();
  return db.getAll(STORES.PENDING_VISITS);
};

export const removePendingVisit = async (placeId: number) => {
  const db = await initDB();
  await db.delete(STORES.PENDING_VISITS, placeId);
};
