import { useEffect, useMemo, useState } from 'react'
import { Database, Download, FileJson, RefreshCcw } from 'lucide-react'
import Topbar from '../components/Topbar'
import {
  CLOUD_DATA_ENDPOINTS,
  api,
  downloadTmsExport,
  getCloudDataEndpoints,
  type CloudDataEndpoint,
} from '../api/client'

type FlatRow = Record<string, string | number | boolean | null>

const API_BASE = api.defaults.baseURL ?? ''

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function flatten(value: unknown, prefix = ''): FlatRow {
  if (!isRecord(value)) {
    return { [prefix || 'value']: toCell(value) }
  }

  return Object.entries(value).reduce<FlatRow>((row, [key, child]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key
    if (Array.isArray(child)) {
      row[nextKey] = `${child.length} item(s)`
    } else if (isRecord(child)) {
      Object.assign(row, flatten(child, nextKey))
    } else {
      row[nextKey] = toCell(child)
    }
    return row
  }, {})
}

function toCell(value: unknown): string | number | boolean | null {
  if (value == null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value ?? null
  }
  return JSON.stringify(value)
}

function rowsFromData(data: unknown): FlatRow[] {
  if (Array.isArray(data)) return data.map((item) => flatten(item))
  if (isRecord(data)) return [flatten(data)]
  return [{ value: toCell(data) }]
}

function downloadText(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

function recordCount(data: unknown) {
  if (Array.isArray(data)) return data.length
  if (isRecord(data)) return Object.keys(data).length
  return data == null ? 0 : 1
}

function previewRows(data: unknown) {
  return rowsFromData(data).slice(0, 8)
}

function TablePreview({ data }: { data: unknown }) {
  const rows = previewRows(data)
  const headers = useMemo(
    () => Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 8),
    [rows],
  )

  if (rows.length === 0 || headers.length === 0) {
    return <p className="px-4 py-8 text-center text-[13px] text-rail-steelLight">No records returned.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12.5px]">
        <thead>
          <tr className="text-left text-rail-steelLight border-b border-rail-line">
            {headers.map((header) => (
              <th key={header} className="px-3 py-2 font-medium whitespace-nowrap">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-rail-line last:border-0 hover:bg-rail-fog/60">
              {headers.map((header) => (
                <td key={header} className="px-3 py-2 text-rail-steel whitespace-nowrap max-w-[260px] truncate">
                  {String(row[header] ?? '-')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function CloudDataPage() {
  const [sections, setSections] = useState<CloudDataEndpoint[]>([])
  const [loading, setLoading] = useState(true)
  const [exportingTms, setExportingTms] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const data = await getCloudDataEndpoints()
      setSections(data)
      setError(null)
    } catch {
      setError('Could not load cloud data. Please check that the backend service is running.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function downloadAllJson() {
    const payload = {
      exportedAt: new Date().toISOString(),
      apiBaseUrl: API_BASE,
      endpoints: sections.reduce<Record<string, unknown>>((bundle, section) => {
        bundle[section.key] = {
          label: section.label,
          path: section.path,
          data: section.data,
        }
        return bundle
      }, {}),
    }
    downloadText('uabams-cloud-data-snapshot.json', JSON.stringify(payload, null, 2), 'application/json')
  }

  async function handleTmsExport() {
    setExportingTms(true)
    try {
      await downloadTmsExport(30)
    } finally {
      setExportingTms(false)
    }
  }

  return (
    <>
      <Topbar title="Cloud Data" subtitle="One place to review API data and download cloud snapshots" />

      <div className="p-6 space-y-5">
        {error && (
          <div className="panel p-4 text-[13px] text-status-critical border-status-critical/30 bg-status-critical/5">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="panel p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-md bg-rail-blue/10 text-rail-blue flex items-center justify-center">
                <Database size={19} />
              </div>
              <div>
                <p className="label-eyebrow">Cloud source</p>
                <p className="font-display text-[18px] text-rail-navy">Live API data</p>
              </div>
            </div>
            <p className="mt-3 text-[12.5px] text-rail-steel leading-relaxed break-all">
              {API_BASE}
            </p>
          </div>

          <div className="panel p-4">
            <p className="label-eyebrow">Loaded datasets</p>
            <p className="mt-2 font-display text-[28px] leading-none text-rail-navy">
              {loading ? '--' : sections.length}
            </p>
            <p className="mt-2 text-[12.5px] text-rail-steelLight">
              Dashboard, alerts, thresholds, calibration, gateways and delivery audits.
            </p>
          </div>

          <div className="panel p-4 flex flex-wrap content-start gap-2">
            <button
              onClick={load}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md border border-rail-line bg-white px-3 py-2 text-[12.5px] font-medium text-rail-steel hover:border-rail-blue/50 disabled:opacity-60"
            >
              <RefreshCcw size={14} />
              {loading ? 'Refreshing...' : 'Refresh'}
            </button>
            <button
              onClick={downloadAllJson}
              disabled={loading || sections.length === 0}
              className="inline-flex items-center gap-2 rounded-md bg-rail-blue px-3 py-2 text-[12.5px] font-medium text-white hover:bg-rail-blueDark disabled:opacity-60"
            >
              <FileJson size={14} />
              Download JSON
            </button>
            <button
              onClick={handleTmsExport}
              disabled={exportingTms}
              className="inline-flex items-center gap-2 rounded-md border border-rail-line bg-white px-3 py-2 text-[12.5px] font-medium text-rail-steel hover:border-rail-blue/50 disabled:opacity-60"
            >
              <Download size={14} />
              {exportingTms ? 'Preparing...' : 'TMS ZIP'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {(loading ? CLOUD_DATA_ENDPOINTS : sections).map((section) => {
            const data = 'data' in section ? section.data : []
            return (
              <div key={section.key} className="panel overflow-hidden">
                <div className="panel-header">
                  <div>
                    <p className="font-display font-medium text-[14px] text-rail-navy">{section.label}</p>
                    <p className="text-[11.5px] text-rail-steelLight break-all">
                      {API_BASE}{section.path}
                    </p>
                  </div>
                  <span className="label-eyebrow">{loading ? '--' : `${recordCount(data)} record(s)`}</span>
                </div>
                {loading ? (
                  <p className="px-4 py-8 text-center text-[13px] text-rail-steelLight">Loading...</p>
                ) : (
                  <>
                    <TablePreview data={data} />
                    <div className="flex items-center gap-2 px-4 py-3 border-t border-rail-line bg-rail-fog/35">
                      <button
                        onClick={() => downloadText(
                          `uabams-${section.key}.json`,
                          JSON.stringify(data, null, 2),
                          'application/json',
                        )}
                        className="inline-flex items-center gap-2 rounded-md border border-rail-line bg-white px-3 py-1.5 text-[12px] font-medium text-rail-steel hover:border-rail-blue/50"
                      >
                        <FileJson size={13} />
                        JSON
                      </button>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </>
  )
}
