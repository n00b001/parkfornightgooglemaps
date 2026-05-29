export interface User {
	id: string;
	googleId: string;
	email: string;
	name?: string;
	avatar?: string;
}

export interface Place {
	id: number;
	name: string;
	title?: string;
	latitude: string | number;
	longitude: string | number;
	type: string;
	description?: string;
	address?: string;
	rating?: number;
	reviewCount?: number;
	photoCount?: number;
	photos?: any[];
	rawData?: any;
	[key: string]: any;
}

export interface Review {
	id: string;
	content: string;
	rating: number;
	user?: User;
	userId: string;
	placeId: number;
	createdAt: string;
}

export interface Visit {
	id: string;
	userId: string;
	placeId: number;
	visitedAt: string;
}

export interface Filters {
	type?: string;
	minRating?: string;
	sortBy?: string;
	amenities?: string[];
}
