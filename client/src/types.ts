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
  latitude: number;
  longitude: number;
  type: string;
  description?: string;
  address?: string;
  rating?: number;
  rawData?: any;
  // Frequently used fields from Park4night rawData
  titre?: string;
  note_moyenne?: number;
  nb_comm?: number;
  photos?: { lien_mini: string; lien_large?: string }[];
  code_type?: string;
  adresse?: string;
  point_eau?: string;
  electricite?: string;
  poubelle?: string;
  wifi?: string;
  vidange_eaux_usees?: string;
  vidange_wc?: string;
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
  minRating?: string | number;
  sortBy?: 'rating' | 'distance';
}
