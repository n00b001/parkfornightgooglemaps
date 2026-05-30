import axios from 'axios'
import { supabase } from './lib/supabase'

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL.startsWith('http')
      ? import.meta.env.VITE_API_URL
      : `https://${import.meta.env.VITE_API_URL}`)
    : '',
})

// Attach Supabase JWT to every request
instance.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

export default instance
