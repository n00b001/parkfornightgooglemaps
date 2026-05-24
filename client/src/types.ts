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
  titre?: string;
  latitude: number;
  longitude: number;
  type: string;
  code_type?: string;
  description?: string;
  address?: string;
  adresse?: string;
  rating?: number;
  note_moyenne?: number;
  nb_comm?: number;
  rawData?: any;
  photos?: { lien_mini: string }[];
  [key: string]: any;
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
  sortBy?: 'rating' | 'distance';
  searchQuery?: string;
  [key: string]: any;
}
