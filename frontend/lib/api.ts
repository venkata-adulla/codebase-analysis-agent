import axios from 'axios'

const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'

/**
 * Browser: always call the **page origin** + `/api` (e.g. `http://localhost:3000/api`). Next.js
 * rewrites proxy to the real API (`http://backend:8000` inside Docker). Never use Docker hostnames
 * like `backend` in the browser — they are not resolvable on the host machine.
 *
 * We set baseURL per request in the browser so a stale bundle or env cannot point axios at
 * `http://backend:8000`.
 */
const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  },
})

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined' && window.location?.origin) {
    config.baseURL = `${window.location.origin}/api`
  }
  return config
})

// Add request interceptor to include auth token if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}, (error) => {
  return Promise.reject(error)
})

// Add response interceptor for error handling
api.interceptors.response.use((response) => {
  return response
}, (error) => {
  if (error.response?.status === 401) {
    // Handle unauthorized without redirecting to a non-existent /login route.
    localStorage.removeItem('auth_token')
  }
  return Promise.reject(error)
})

export default api
