import axios from 'axios'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
    ...(process.env.NEXT_PUBLIC_API_KEY ? { 'X-API-Key': process.env.NEXT_PUBLIC_API_KEY } : {}),
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
