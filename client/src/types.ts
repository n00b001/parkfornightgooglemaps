export interface Place {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  type: string;
  description?: string;
  address?: string;
  rating: number;
  rawData: any;
  [key: string]: any; // For dynamic amenity checks like place.point_eau
}

export interface User {
  id: string;
  googleId: string;
  email: string;
  name: string;
  avatar: string;
}

export interface Review {
  id: string;
  content: string;
  rating: number;
  userId: string;
  placeId: number;
  user?: User;
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
  search?: string;
  [key: string]: any; // For amenities
}
