import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  // Required so the session cookie issued by /api/auth/login is sent
  // back on subsequent admin requests. Same-origin (via vite proxy) in
  // dev, so this is safe.
  withCredentials: true,
})

export default api
