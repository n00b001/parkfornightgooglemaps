import { openDB, IDBPDatabase } from "idb";

const DB_NAME = "park4night-db";
const STORES = {
	PLACES: "places",
	REVIEWS: "reviews",
	VISITS: "visits",
	PENDING_VISITS: "pending-visits",
	PENDING_FAVORITES: "pending-favorites",
	PENDING_REVIEWS: "pending-reviews",
};

export const initDB = async (): Promise<IDBPDatabase> => {
	return openDB(DB_NAME, 4, {
		upgrade(db, oldVersion) {
			if (oldVersion < 1) {
				db.createObjectStore(STORES.PLACES, { keyPath: "id" });
			}
			if (oldVersion < 2) {
				db.createObjectStore(STORES.REVIEWS, { keyPath: "id" });
				db.createObjectStore(STORES.VISITS, { keyPath: "id" });
			}
			if (oldVersion < 3) {
				if (!db.objectStoreNames.contains(STORES.PENDING_VISITS)) {
					db.createObjectStore(STORES.PENDING_VISITS, { keyPath: "placeId" });
				}
			}
			if (oldVersion < 4) {
				if (!db.objectStoreNames.contains(STORES.PENDING_FAVORITES)) {
					db.createObjectStore(STORES.PENDING_FAVORITES, {
						keyPath: "placeId",
					});
				}
				if (!db.objectStoreNames.contains(STORES.PENDING_REVIEWS)) {
					db.createObjectStore(STORES.PENDING_REVIEWS, {
						keyPath: "id",
						autoIncrement: true,
					});
				}
			}
		},
	});
};

export const saveReviews = async (placeId: number, reviews: any) => {
	const db = await initDB();
	await db.put(STORES.REVIEWS, { id: placeId, reviews, timestamp: Date.now() });
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

export const savePendingFavorite = async (
	placeId: number,
	action: "add" | "remove",
) => {
	const db = await initDB();
	await db.put(STORES.PENDING_FAVORITES, {
		placeId,
		action,
		timestamp: Date.now(),
	});
};

export const getPendingFavorites = async (): Promise<any[]> => {
	const db = await initDB();
	return db.getAll(STORES.PENDING_FAVORITES);
};

export const removePendingFavorite = async (placeId: number) => {
	const db = await initDB();
	await db.delete(STORES.PENDING_FAVORITES, placeId);
};

export const savePendingReview = async (review: {
	placeId: number;
	content: string;
	rating: number;
}) => {
	const db = await initDB();
	await db.put(STORES.PENDING_REVIEWS, { ...review, timestamp: Date.now() });
};

export const getPendingReviews = async (): Promise<any[]> => {
	const db = await initDB();
	return db.getAll(STORES.PENDING_REVIEWS);
};

export const removePendingReview = async (id: number) => {
	const db = await initDB();
	await db.delete(STORES.PENDING_REVIEWS, id);
};
