import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'park4night-db';
const STORE_NAME = 'places';

export interface Place {
  id: number;
  titre: string;
  latitude: number;
  longitude: number;
  code_type: string;
  adresse: string;
  note_moyenne: number;
  [key: string]: any;
}

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

export const savePlaces = async (places: Place[]) => {
  const db = await getDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  await Promise.all([
    ...places.map((place) => tx.store.put(place)),
    tx.done,
  ]);
};

export const getAllPlaces = async (): Promise<Place[]> => {
  const db = await getDB();
  return db.getAll(STORE_NAME);
};

export const searchPlacesOffline = async (query: string): Promise<Place[]> => {
  const places = await getAllPlaces();
  if (!query) return places;

  const lowQuery = query.toLowerCase();
  return places.filter(p =>
    p.titre?.toLowerCase().includes(lowQuery) ||
    p.adresse?.toLowerCase().includes(lowQuery)
  );
};
