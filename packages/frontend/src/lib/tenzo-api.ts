// HoFi - Cliente API del Agente Tenzo

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export interface TaskProposal {
  titulo: string;
  descripcion: string;
  categoria: string;
  duracion_horas: number;
  holon_id: string;
}

export interface TenzoEvaluation {
  modo: string;
  aprobada: boolean;
  recompensa_hoca: number;
  clasificacion: string[];
  razonamiento: string;
}

export async function getAuthToken(password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'tenzo-admin', password }),
  });
  const data = await res.json();
  return data.access_token;
}

export async function evaluateTask(token: string, task: TaskProposal): Promise<TenzoEvaluation> {
  const res = await fetch(`${API_BASE}/evaluar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(task),
  });
  return res.json();
}

export async function getProtocolStats(token: string) {
  const res = await fetch(`${API_BASE}/protocol/stats`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.json();
}

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}
