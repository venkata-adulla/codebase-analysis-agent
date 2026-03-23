import axios from 'axios'

const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  },
})

api.interceptors.request.use((config) => {
  if (!config.baseURL?.startsWith('/api') && process.env.NEXT_PUBLIC_API_URL) {
    config.baseURL = process.env.NEXT_PUBLIC_API_URL
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
    // Handle unauthorized - clear token and redirect to login
    localStorage.removeItem('auth_token')
    window.location.href = '/login'
  }
  return Promise.reject(error)
})

export default api
