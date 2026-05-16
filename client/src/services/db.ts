import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night-db';
const STORE_NAME = 'places';

export const initDB = async (): Promise<IDBPDatabase> => {
  return openDB(DB_NAME, 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    },
  });
};

export const savePlaces = async (places: any[]) => {
  const db = await initDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  for (const place of places) {
    await tx.store.put(place);
  }
  await tx.done;
};

export const getCachedPlaces = async (): Promise<any[]> => {
  const db = await initDB();
  return db.getAll(STORE_NAME);
};
