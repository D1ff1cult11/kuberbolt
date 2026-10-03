import { useState, useEffect } from 'react';

interface Provider {
  service_name?: string;
  name?: string;
  nostr_pubkey?: string;
  agent_pubkey?: string;
  provider_id?: string;
  price_sats?: number;
  category?: string;
}

export default function Discover() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchProviders();
  }, []);

  async function fetchProviders() {
    setLoading(true);
    setError('');
    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const category = import.meta.env.VITE_PROVIDER_CATEGORY || 'text-summarization';
      const res = await fetch(`${apiUrl}/api/providers?category=${encodeURIComponent(category)}`);
      if (res.ok) {
        const data = await res.json();
        setProviders(data.items || []);
      } else {
        throw new Error(`Provider search failed (${res.status})`);
      }
    } catch (err) {
      setProviders([]);
      setError(err instanceof Error ? err.message : 'Could not reach the provider directory.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Discover Providers</h1>
          <p className="page-subtitle">Find AI compute providers on the Nostr network</p>
        </div>
        <button className="btn btn-outline" onClick={fetchProviders}>↻ Refresh</button>
      </div>

      {error && <div className="banner banner-warning">⚠️ {error}</div>}

      {loading ? (
        <div className="glass-panel empty-state">
          <div className="empty-state-icon">🔍</div>
          <p>Searching Nostr network...</p>
        </div>
      ) : (
        <div className="card-grid">
          {providers.map((p) => {
            const pubkey = p.nostr_pubkey || p.agent_pubkey || p.provider_id || '';
            const title = p.service_name || p.name || 'AI Service';
            return (
              <div key={pubkey || title} className="glass-panel provider-card">
                <div>
                  <div className="provider-name">{title}</div>
                  <div className="provider-pubkey">
                    {pubkey ? `${pubkey.slice(0, 24)}...` : 'Unknown Identity'}
                  </div>
                  <span className="badge badge-success">● Available</span>
                </div>
                <div className="provider-footer">
                  <span className="provider-price">⚡ {p.price_sats ?? 'Price unavailable'}{p.price_sats != null ? ' sats/req' : ''}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
