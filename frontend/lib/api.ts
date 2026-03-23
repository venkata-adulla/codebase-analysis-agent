import axios from 'axios'

const getDefaultApiUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL
  }
  if (typeof window !== 'undefined') {
    // Use backend host at same origin by default in workspace preview scenarios.
    return `${window.location.protocol}//${window.location.hostname}:8000`
  }
  return 'http://localhost:8000'
}

const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'

const api = axios.create({
  baseURL: getDefaultApiUrl(),
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  },
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
    // Handle unauthorized - clear token and redirect to login
    localStorage.removeItem('auth_token')
    window.location.href = '/login'
  }
  return Promise.reject(error)
})

export default api
