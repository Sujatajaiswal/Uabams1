import axios from 'axios'
import type {
  AlertRecord,
  ArchiveUploadResult,
  CalibrationInput,
  CalibrationRecord,
  DashboardData,
  GatewayStatus,
  ThresholdInput,
  ThresholdSetting,
} from '../types'

// In production this is injected at build time (Render static site env var).
// Falls back to localhost for local `npm run dev` against the docker-compose backend.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const API_TOKEN = import.meta.env.VITE_API_TOKEN || ''

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  if (API_TOKEN) {
    config.headers.Authorization = `Bearer ${API_TOKEN}`
  }
  return config
})

export async function getDashboard(): Promise<DashboardData> {
  const { data } = await api.get<DashboardData>('/api/v1/dashboard')
  return data
}

export async function getGateways(): Promise<GatewayStatus[]> {
  const { data } = await api.get<GatewayStatus[]>('/api/v1/gateways')
  return data
}

export interface CloudDataEndpoint<T = unknown> {
  key: string
  label: string
  path: string
  data: T
}

export interface IntegrationStatus {
  authentication: {
    apiAuthEnabled: boolean
    gatewayAuthEnabled: boolean
    operatorHeader: string
    gatewayHeader: string
  }
  smsServer: {
    configured: boolean
    mode: string
    recipientCount: number
    outputTable: string
    latestStatus: string | null
    latestMessage: string | null
  }
  database: {
    type: string
    notificationDeliveries: number
  }
}

export interface DemoSmsResult {
  ok: boolean
  alertId: number
  channel: string
  status: string
  recipient: string | null
  message: string | null
  providerMessageId: string | null
  outputTable: string
  createdAt: string
  sentAt: string | null
}

export const CLOUD_DATA_ENDPOINTS = [
  { key: 'dashboard', label: 'Dashboard Summary', path: '/api/v1/dashboard' },
  { key: 'alerts', label: 'Alerts', path: '/api/v1/alerts' },
  { key: 'threshold', label: 'Route Thresholds', path: '/api/v1/threshold' },
  { key: 'calibration', label: 'Calibration History', path: '/api/v1/calibration' },
  { key: 'gateways', label: 'Gateways', path: '/api/v1/gateways' },
  {
    key: 'notificationDeliveries',
    label: 'Notification Deliveries',
    path: '/api/v1/maintenance/notification-deliveries',
  },
  {
    key: 'integrationStatus',
    label: 'Authentication & SMS Status',
    path: '/api/v1/maintenance/integration-status',
  },
  {
    key: 'tmsDeliveries',
    label: 'TMS Deliveries',
    path: '/api/v1/maintenance/tms-deliveries',
  },
] as const

export async function getCloudDataEndpoints(): Promise<CloudDataEndpoint[]> {
  const responses = await Promise.all(
    CLOUD_DATA_ENDPOINTS.map(async (endpoint) => {
      const { data } = await api.get(endpoint.path)
      return { ...endpoint, data }
    }),
  )
  return responses
}

export async function getIntegrationStatus(): Promise<IntegrationStatus> {
  const { data } = await api.get<IntegrationStatus>('/api/v1/maintenance/integration-status')
  return data
}

export async function sendDemoSms(): Promise<DemoSmsResult> {
  const { data } = await api.post<DemoSmsResult>('/api/v1/maintenance/demo-sms')
  return data
}

export async function getAlerts(params?: { severity?: string; route?: string }): Promise<AlertRecord[]> {
  const { data } = await api.get<AlertRecord[]>('/api/v1/alerts', { params })
  return data
}

export async function getThresholds(): Promise<ThresholdSetting[]> {
  const { data } = await api.get<ThresholdSetting[]>('/api/v1/threshold')
  return data
}

export async function saveThreshold(payload: ThresholdInput): Promise<ThresholdSetting> {
  const { data } = await api.post<ThresholdSetting>('/api/v1/threshold', payload)
  return data
}

export async function getCalibrationHistory(params?: {
  gatewayId?: string
  axleId?: string
}): Promise<CalibrationRecord[]> {
  const { data } = await api.get<CalibrationRecord[]>('/api/v1/calibration', { params })
  return data
}

export async function saveCalibration(payload: CalibrationInput): Promise<CalibrationRecord> {
  const { data } = await api.post<CalibrationRecord>('/api/v1/calibration', payload)
  return data
}

export interface SimulatedUploadPayload {
  gatewayId: string
  trainId: string
  speed: number
  peak: number
  gps: { lat: number; lon: number }
}

export async function uploadArchive(payload: SimulatedUploadPayload): Promise<ArchiveUploadResult> {
  const { data } = await api.post<ArchiveUploadResult>('/api/v1/archive', payload)
  return data
}

/**
 * Triggers a browser download of the CRIS TMS export bundle (clause 2.5 of
 * the RDSO UABAMS spec: spatial acceleration data + processed peak data,
 * packaged alongside a genuine target .mdb container). See
 * backend/app/services/tms_export.py for the full rationale.
 */
export async function downloadTmsExport(days = 30): Promise<void> {
  const response = await api.get('/api/v1/export/tms', {
    params: { days },
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(response.data)
  const link = document.createElement('a')
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  link.href = url
  link.download = match?.[1] || `uabams_tms_export_${days}d.zip`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
