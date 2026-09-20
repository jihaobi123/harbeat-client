import type { Report } from './data'
const BASE = '/api/analysis-lab'
export async function call<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, options)
  const body = await response.json().catch(() => null)
  if (!response.ok || body === null) throw new Error(typeof body?.detail === 'string' ? body.detail : '分析服务未连接，请检查服务和转发链路')
  return body
}
export const post = <T>(path: string, value: unknown) => call<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })
export const getReport = (id: string) => call<Report>(`/reports/${encodeURIComponent(id)}`)

export async function loadWorkspace(onReports:(items:any[])=>void,onJobs:(tasks:any[])=>void){
  const [items,tasks]=await Promise.all([
    call<any[]>('/reports').then(items=>{onReports(items);return items}),
    call<any[]>('/jobs').then(tasks=>{onJobs(tasks);return tasks}),
  ])
  return {items,tasks}
}
