import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night-db';
const STORE_NAME = 'places';

export const initDB = async (): Promise<IDBPDatabase> => {
  return openDB(DB_NAME, 2, {
    upgrade(db, oldVersion) {
      if (oldVersion < 1) {
        db.createObjectStore('places', { keyPath: 'id' });
      }
      if (oldVersion < 2) {
        db.createObjectStore('reviews', { keyPath: 'id' });
        db.createObjectStore('visits', { keyPath: 'id' });
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
