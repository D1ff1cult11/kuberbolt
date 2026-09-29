import { useState, useEffect } from 'react';

export default function Discover() {
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    setLoading(true);
    try {
      // Mock API call or real API depending on backend status
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/providers?category=compute`);
      if (res.ok) {
        const data = await res.json();
        setProviders(data.items || []);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <h1>Discover Providers</h1>
        <button className="btn" onClick={fetchProviders}>Refresh</button>
      </div>

      {loading ? (
        <p>Searching Nostr network...</p>
      ) : providers.length === 0 ? (
        <div className="glass-panel" style={{ textAlign: 'center', padding: '48px' }}>
          <p style={{ fontSize: '1.2rem', opacity: 0.7 }}>No compute providers found on the network.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
          {providers.map((p, i) => (
            <div key={i} className="glass-panel">
              <h3>{p.service_name}</h3>
              <p style={{ opacity: 0.8, fontSize: '0.9rem' }}>Provider: {p.agent_pubkey.slice(0, 8)}...</p>
              <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 'bold', color: 'var(--primary-color)' }}>{p.price_sats} sats / req</span>
                <button className="btn" style={{ padding: '6px 12px', fontSize: '14px' }}>Connect</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
