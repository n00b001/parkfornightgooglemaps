import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night-db';
const STORES = {
  PLACES: 'places',
  REVIEWS: 'reviews',
  VISITS: 'visits',
  PENDING_VISITS: 'pending-visits'
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
          db.createObjectStore(STORES.PENDING_VISITS, { keyPath: 'id', autoIncrement: true });
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

export const savePendingVisit = async (placeId: number) => {
  const db = await initDB();
  await db.add(STORES.PENDING_VISITS, { placeId, timestamp: new Date().toISOString() });
};

export const getPendingVisits = async () => {
  const db = await initDB();
  return db.getAll(STORES.PENDING_VISITS);
};

export const clearPendingVisit = async (id: number) => {
  const db = await initDB();
  await db.delete(STORES.PENDING_VISITS, id);
};
