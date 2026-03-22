'use client';
import { useEffect, useState } from 'react';
import { getProtocolStats } from '../lib/tenzo-api';

interface Props { token: string; }

export default function HolonStats({ token }: Props) {
  const [stats, setStats] = useState<any>(null);
  useEffect(() => {
    if (token) getProtocolStats(token).then(setStats).catch(console.error);
  }, [token]);

  if (!stats) return <div className="text-gray-500">Cargando estadisticas...</div>;
  return (
    <div className="p-6 bg-white rounded-xl shadow">
      <h2 className="text-xl font-bold text-green-700 mb-4">Stats del Holon</h2>
      <pre className="text-sm bg-gray-100 p-3 rounded overflow-auto">
        {JSON.stringify(stats, null, 2)}
      </pre>
    </div>
  );
}
