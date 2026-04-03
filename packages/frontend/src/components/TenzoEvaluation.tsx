'use client';
import type { TenzoEvaluation } from '../lib/tenzo-api';

interface Props { evaluation: TenzoEvaluation | null; }

export default function TenzoEvaluationCard({ evaluation }: Props) {
  if (!evaluation) return null;
  const ok = evaluation.aprobada;
  return (
    <div className={`p-6 rounded-xl shadow border-2 ${ok ? 'border-green-500 bg-green-50' : 'border-red-400 bg-red-50'}`}>
      <h2 className="text-xl font-bold mb-2">{ok ? 'Tarea Aprobada' : 'Tarea Rechazada'}</h2>
      {ok && <p className="text-3xl font-bold text-green-700">{evaluation.recompensa_hoca} HoCa</p>}
      <div className="mt-2 flex gap-2 flex-wrap">
        {evaluation.clasificacion.map(tag => (
          <span key={tag} className="bg-green-200 text-green-800 px-2 py-1 rounded-full text-sm">{tag}</span>
        ))}
      </div>
      <p className="mt-3 text-gray-600 italic text-sm">{evaluation.razonamiento}</p>
    </div>
  );
}
