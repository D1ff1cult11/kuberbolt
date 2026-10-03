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

const DEMO_PROVIDERS: Provider[] = [
  { service_name: 'LLM Inference (GPT-4)', agent_pubkey: 'npub1q8k2fy5lmf7gqr4zctaw...', price_sats: 50, category: 'compute' },
  { service_name: 'Image Generation (SDXL)', agent_pubkey: 'npub1xh9n3jk2p5wlsrvt6aq...', price_sats: 200, category: 'compute' },
  { service_name: 'Code Review Agent', agent_pubkey: 'npub1d4r7kmz8f3q9vwnyp2c...', price_sats: 100, category: 'compute' },
  { service_name: 'Speech-to-Text (Whisper)', agent_pubkey: 'npub1m7g5ht4k2wcfnpj8rd6...', price_sats: 75, category: 'compute' },
];

export default function Discover() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [isDemo, setIsDemo] = useState(false);

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    setLoading(true);
    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${apiUrl}/api/providers?category=text-summarization`);
      if (res.ok) {
        const data = await res.json();
        const items = data.items || [];
        if (items.length > 0) {
          setProviders(items);
          setIsDemo(false);
        } else {
          setProviders(DEMO_PROVIDERS);
          setIsDemo(true);
        }
      } else {
        throw new Error('API error');
      }
    } catch {
      setProviders(DEMO_PROVIDERS);
      setIsDemo(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Discover Providers</h1>
          <p className="page-subtitle">Find AI compute providers on the Nostr network</p>
        </div>
        <button className="btn btn-outline" onClick={fetchProviders}>↻ Refresh</button>
      </div>

      {isDemo && (
        <div className="banner banner-info">
          ℹ️ <span><strong>Demo Mode</strong> — Showing sample providers. Connect a backend to query real Nostr relays.</span>
        </div>
      )}

      {loading ? (
        <div className="glass-panel empty-state">
          <div className="empty-state-icon">🔍</div>
          <p>Searching Nostr network...</p>
        </div>
      ) : (
        <div className="card-grid">
          {providers.map((p, i) => {
            const pubkey = p.nostr_pubkey || p.agent_pubkey || p.provider_id || '';
            const title = p.service_name || p.name || 'AI Service';
            return (
              <div key={i} className="glass-panel provider-card">
                <div>
                  <div className="provider-name">{title}</div>
                  <div className="provider-pubkey">
                    {pubkey ? `${pubkey.slice(0, 24)}...` : 'Unknown Identity'}
                  </div>
                  <span className="badge badge-success">● Available</span>
                </div>
                <div className="provider-footer">
                  <span className="provider-price">⚡ {p.price_sats ?? 100} sats/req</span>
                  <button className="btn btn-sm">Connect</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
