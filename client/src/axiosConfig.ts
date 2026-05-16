import axios from 'axios';

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_URL ? (import.meta.env.VITE_API_URL.startsWith('http') ? import.meta.env.VITE_API_URL : `https://${import.meta.env.VITE_API_URL}`) : '',
  withCredentials: true
});

export default instance;
