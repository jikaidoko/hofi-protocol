'use client';
import { useState } from 'react';

interface Props { onConnect: (address: string) => void; }

export default function WalletConnect({ onConnect }: Props) {
  const [address, setAddress] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const connect = async () => {
    if (typeof window.ethereum === 'undefined') {
      alert('MetaMask no detectado.');
      return;
    }
    setLoading(true);
    try {
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
      setAddress(accounts[0]);
      onConnect(accounts[0]);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  return address ? (
    <div className="flex items-center gap-2 text-green-700">
      <span className="w-2 h-2 bg-green-500 rounded-full inline-block"></span>
      <span className="font-mono text-sm">{address.slice(0,6)}...{address.slice(-4)}</span>
    </div>
  ) : (
    <button onClick={connect} disabled={loading}
      className="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700 disabled:opacity-50">
      {loading ? 'Conectando...' : 'Conectar MetaMask'}
    </button>
  );
}
