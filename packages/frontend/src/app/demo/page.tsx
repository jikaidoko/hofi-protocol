'use client';
export default function DemoPage() {
  const items = [
    { label: 'Agente Tenzo', desc: 'IA arbitro de justicia comunitaria', icon: 'AI' },
    { label: 'HoCa Token',   desc: 'Token de cuidado (Sepolia)',         icon: 'TK' },
    { label: 'GenLayer ISC', desc: 'Oraculos IA descentralizados',       icon: 'GL' },
  ];
  return (
    <main className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
      <div className="max-w-2xl text-center space-y-6">
        <h1 className="text-5xl font-bold text-green-400">HoFi</h1>
        <p className="text-2xl italic text-gray-300">The act of caring is the yield.</p>
        <div className="grid grid-cols-3 gap-4 mt-8">
          {items.map(item => (
            <div key={item.label} className="bg-gray-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-green-400 mb-2">{item.icon}</div>
              <h3 className="font-bold text-green-400">{item.label}</h3>
              <p className="text-sm text-gray-400">{item.desc}</p>
            </div>
          ))}
        </div>
        <a href="/" className="inline-block mt-6 bg-green-600 text-white px-8 py-3 rounded-xl hover:bg-green-700">
          Abrir Dashboard
        </a>
      </div>
    </main>
  );
}
