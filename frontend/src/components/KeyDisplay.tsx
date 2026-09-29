interface KeyDisplayProps {
  pubkey: string;
  privkey: string;
  nsec: string;
}

export const KeyDisplay = ({ pubkey, privkey, nsec }: KeyDisplayProps) => {
  const downloadKeyFile = () => {
    const data = JSON.stringify({ npub: pubkey, privkey, nsec }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kuberbolt-agent-keys-${pubkey.slice(0, 8)}.json`;
    a.click();
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  return (
    <div className="glass-panel" style={{ maxWidth: '600px', margin: '0 auto' }}>
      <div className="warning-banner">
        ⚠️ SAVE YOUR PRIVATE KEY NOW. It will never be shown again!
      </div>
      
      <div style={{ marginBottom: '24px' }}>
        <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>Public Key (npub)</label>
        <div className="code-block">{pubkey}</div>
        <button className="btn" style={{ fontSize: '12px', padding: '6px 12px' }} onClick={() => copyToClipboard(pubkey)}>Copy</button>
      </div>

      <div style={{ marginBottom: '24px' }}>
        <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold', color: 'var(--danger-color)' }}>Secret Key (nsec)</label>
        <div className="code-block">{nsec}</div>
        <button className="btn" style={{ fontSize: '12px', padding: '6px 12px', background: 'var(--danger-color)' }} onClick={() => copyToClipboard(nsec)}>Copy Secret</button>
      </div>

      <div style={{ marginTop: '32px', textAlign: 'center' }}>
        <button className="btn" onClick={downloadKeyFile} style={{ width: '100%', padding: '16px', fontSize: '16px' }}>
          ⬇️ Download Key File (.json)
        </button>
      </div>
    </div>
  );
};
