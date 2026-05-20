import axios from 'axios'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

const http = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10000
})

http.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response) {
      return Promise.reject({
        ...(error.response.data || {}),
        status: error.response.status,
        status_code: error.response.status
      })
    }
    return Promise.reject(error)
  }
)

export { http, apiBaseUrl }

export default {
  verifyCode: code => http.get(`/parent/verify/${code}`),
  getStudent: code => http.get(`/parent/student/${code}`),
  getScores: (code, params) => http.get(`/parent/scores/${code}`, { params }),
  getNotifications: (code, params) => http.get(`/parent/notifications/${code}`, { params }),
  getHomework: (code, params) => http.get(`/parent/homework/${code}`, { params }),
  getStats: (code, params) => http.get(`/parent/stats/${code}`, { params })
}
