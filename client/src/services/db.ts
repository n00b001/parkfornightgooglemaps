import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night-db';
const PLACES_STORE = 'places';
const REVIEWS_STORE = 'reviews';
const VISITS_STORE = 'visits';

export const initDB = async (): Promise<IDBPDatabase> => {
  return openDB(DB_NAME, 2, {
    upgrade(db, oldVersion) {
      if (oldVersion < 1) {
        db.createObjectStore(PLACES_STORE, { keyPath: 'id' });
      }
      if (oldVersion < 2) {
        if (!db.objectStoreNames.contains(REVIEWS_STORE)) {
          db.createObjectStore(REVIEWS_STORE, { keyPath: 'tempId', autoIncrement: true });
        }
        if (!db.objectStoreNames.contains(VISITS_STORE)) {
          db.createObjectStore(VISITS_STORE, { keyPath: 'placeId' });
        }
      }
    },
  });
};

export const savePlaces = async (places: any[]) => {
  const db = await initDB();
  const tx = db.transaction(PLACES_STORE, 'readwrite');
  for (const place of places) {
    await tx.store.put(place);
  }
  await tx.done;
};

export const getCachedPlaces = async (): Promise<any[]> => {
  const db = await initDB();
  return db.getAll(PLACES_STORE);
};

export const saveOfflineReview = async (review: any) => {
  const db = await initDB();
  return db.add(REVIEWS_STORE, { ...review, tempId: Date.now() });
};

export const getOfflineReviews = async () => {
  const db = await initDB();
  return db.getAll(REVIEWS_STORE);
};

export const deleteOfflineReview = async (tempId: number) => {
  const db = await initDB();
  return db.delete(REVIEWS_STORE, tempId);
};

export const saveOfflineVisit = async (placeId: number) => {
  const db = await initDB();
  return db.put(VISITS_STORE, { placeId, timestamp: new Date().toISOString() });
};

export const getOfflineVisits = async () => {
  const db = await initDB();
  return db.getAll(VISITS_STORE);
};

export const deleteOfflineVisit = async (placeId: number) => {
  const db = await initDB();
  return db.delete(VISITS_STORE, placeId);
};
