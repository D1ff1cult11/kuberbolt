import { useState } from 'react';
import { KeyDisplay } from '../components/KeyDisplay';

export default function Register() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    role: 'merchant',
    displayName: '',
    nodePubkey: '',
    serviceName: '',
    priceSats: 100
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const payload = {
      role: formData.role,
      display_name: formData.displayName,
      lightning: {
        node_pubkey: formData.nodePubkey
      },
      ...(formData.role === 'merchant' && {
        service: {
          service_name: formData.serviceName,
          category: 'compute',
          price_sats: Number(formData.priceSats),
          price_unit: 'per_request'
        }
      })
    };

    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/agents/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        setResult(data);
      } else {
        alert('Error: ' + JSON.stringify(data));
      }
    } catch (err) {
      alert('Failed to register agent');
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <div>
        <h2 style={{ textAlign: 'center', marginBottom: '32px' }}>Registration Successful! 🎉</h2>
        <KeyDisplay pubkey={result.agent_pubkey} privkey={result.agent_privkey} nsec={result.agent_nsec} />
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ maxWidth: '600px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '24px' }}>Register New Agent</h2>
      <form onSubmit={handleSubmit}>
        <div>
          <label style={{ display: 'block', marginBottom: '8px' }}>Agent Name</label>
          <input className="input-field" value={formData.displayName} onChange={e => setFormData({...formData, displayName: e.target.value})} required placeholder="e.g. Trading Bot Alpha" />
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: '8px' }}>Lightning Node Pubkey</label>
          <input className="input-field" value={formData.nodePubkey} onChange={e => setFormData({...formData, nodePubkey: e.target.value})} required placeholder="02abcd..." />
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: '8px' }}>Role</label>
          <select className="input-field" value={formData.role} onChange={e => setFormData({...formData, role: e.target.value})}>
            <option value="merchant">Merchant (Provides Services)</option>
            <option value="client">Client (Consumes Services)</option>
          </select>
        </div>

        {formData.role === 'merchant' && (
          <div style={{ padding: '16px', background: 'rgba(0,0,0,0.1)', borderRadius: '8px', marginBottom: '16px' }}>
            <h4 style={{ marginTop: 0 }}>Service Details</h4>
            <label style={{ display: 'block', marginBottom: '8px' }}>Service Name</label>
            <input className="input-field" value={formData.serviceName} onChange={e => setFormData({...formData, serviceName: e.target.value})} required placeholder="e.g. LLM Inference" />
            
            <label style={{ display: 'block', marginBottom: '8px' }}>Price (Sats)</label>
            <input className="input-field" type="number" value={formData.priceSats} onChange={e => setFormData({...formData, priceSats: Number(e.target.value)})} required />
          </div>
        )}

        <button type="submit" className="btn" style={{ width: '100%', padding: '14px', fontSize: '16px' }} disabled={loading}>
          {loading ? 'Registering...' : 'Register Agent'}
        </button>
      </form>
    </div>
  );
}
