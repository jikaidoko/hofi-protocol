'use client';
import { useState } from 'react';
import TaskProposalForm from '../components/TaskProposal';
import TenzoEvaluationCard from '../components/TenzoEvaluation';
import HolonStats from '../components/HolonStats';
import WalletConnect from '../components/WalletConnect';
import { getAuthToken } from '../lib/tenzo-api';
import type { TenzoEvaluation } from '../lib/tenzo-api';

export default function Dashboard() {
  const [token, setToken] = useState('');
  const [wallet, setWallet] = useState('');
  const [evaluation, setEvaluation] = useState<TenzoEvaluation | null>(null);

  const login = async () => {
    const t = await getAuthToken('HoFi2026Admin!');
    setToken(t);
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 p-6">
      <header className="max-w-4xl mx-auto mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-green-800">HoFi Protocol</h1>
          <p className="text-green-600 italic">The act of caring is the yield.</p>
        </div>
        <WalletConnect onConnect={setWallet} />
      </header>
      <div className="max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
        {!token ? (
          <div className="col-span-2 text-center">
            <button onClick={login}
              className="bg-green-600 text-white px-6 py-3 rounded-xl hover:bg-green-700">
              Conectar con Tenzo Agent
            </button>
          </div>
        ) : (
          <>
            <TaskProposalForm token={token} onResult={setEvaluation} />
            <div className="space-y-4">
              <TenzoEvaluationCard evaluation={evaluation} />
              <HolonStats token={token} />
            </div>
          </>
        )}
      </div>
    </main>
  );
}
