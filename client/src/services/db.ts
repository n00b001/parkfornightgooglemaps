import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night_offline';
const STORE_NAME = 'places';

let dbPromise: Promise<IDBPDatabase>;

const getDB = () => {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        }
      },
    });
  }
  return dbPromise;
};

export const savePlaces = async (places: any[]) => {
  const db = await getDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const store = tx.objectStore(STORE_NAME);
  for (const place of places) {
    await store.put(place);
  }
  await tx.done;
};

export const getCachedPlaces = async () => {
  const db = await getDB();
  return db.getAll(STORE_NAME);
};
