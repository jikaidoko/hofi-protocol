'use client';
import { useState } from 'react';
import { evaluateTask } from '../lib/tenzo-api';
import type { TaskProposal, TenzoEvaluation } from '../lib/tenzo-api';

const CATEGORIAS = [
  'cuidado_ninos','cocina_comunal','limpieza_espacios',
  'taller_educativo','mantenimiento','jardineria','salud_comunitaria',
];

interface Props { token: string; onResult: (r: TenzoEvaluation) => void; }

export default function TaskProposalForm({ token, onResult }: Props) {
  const [form, setForm] = useState<TaskProposal>({
    titulo: '', descripcion: '', categoria: 'cuidado_ninos',
    duracion_horas: 1, holon_id: 'holon-piloto',
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try { onResult(await evaluateTask(token, form)); }
    catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-6 bg-white rounded-xl shadow">
      <h2 className="text-xl font-bold text-green-700">Proponer Tarea Comunitaria</h2>
      <input className="w-full border rounded p-2" placeholder="Titulo"
        value={form.titulo} onChange={e => setForm({...form, titulo: e.target.value})} required />
      <textarea className="w-full border rounded p-2" placeholder="Descripcion"
        value={form.descripcion} onChange={e => setForm({...form, descripcion: e.target.value})} required />
      <select className="w-full border rounded p-2" value={form.categoria}
        onChange={e => setForm({...form, categoria: e.target.value})}>
        {CATEGORIAS.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <input type="number" className="w-full border rounded p-2" placeholder="Duracion (horas)"
        value={form.duracion_horas} min={0.5} step={0.5}
        onChange={e => setForm({...form, duracion_horas: parseFloat(e.target.value)})} required />
      <button type="submit" disabled={loading}
        className="w-full bg-green-600 text-white py-2 rounded hover:bg-green-700 disabled:opacity-50">
        {loading ? 'Evaluando con Tenzo...' : 'Enviar al Tenzo'}
      </button>
    </form>
  );
}
