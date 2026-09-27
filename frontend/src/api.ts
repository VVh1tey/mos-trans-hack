import type { Scenario, ScenarioParameters, Settings, Snapshot, SimulationStatus } from './types';
// All demo data comes from HTTP. A real backend can implement the same contract.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(15000);
  const response = await fetch(`/api/dashboard${path}`, { ...init, signal: init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Сервис ответил ${response.status}`);
  }
  return response.json() as Promise<T>;
}
export const api = {
  simulation: (signal?: AbortSignal) => request<SimulationStatus>('/simulation', { signal }),
  controlSimulation: (action: 'start' | 'stop' | 'reset' | 'speed', speed?: number) => request<SimulationStatus>('/simulation', { method: 'POST', body: JSON.stringify({ action, speed }) }),
  snapshot: (routeId: string | null, direction: number, period: number, signal?: AbortSignal) => request<Snapshot>(`${routeId ? `/routes/${encodeURIComponent(routeId)}` : ''}?direction=${direction}&period=${period}`, { signal }),
  saveSettings: (settings: Settings) => request<Settings>('/settings', { method: 'POST', body: JSON.stringify(settings) }),
  scenario: (routeId: string, parameters: ScenarioParameters) => request<Scenario>(`/routes/${encodeURIComponent(routeId)}/scenario`, { method: 'POST', body: JSON.stringify(parameters) }),
};
