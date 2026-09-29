export default function Dashboard() {
  return (
    <div>
      <h1 style={{ marginBottom: '32px' }}>Kuberbolt Dashboard</h1>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
        
        <div className="glass-panel">
          <h3>Network Status</h3>
          <p style={{ color: 'var(--success-color)', fontWeight: 'bold' }}>🟢 Online (Regtest)</p>
          <p>Connected to 1 Relay</p>
        </div>

        <div className="glass-panel">
          <h3>Active Pods</h3>
          <p style={{ fontSize: '2rem', margin: '12px 0', fontWeight: 'bold' }}>0</p>
          <p style={{ opacity: 0.7 }}>Use deploy-pod.sh to spin up agents.</p>
        </div>

        <div className="glass-panel">
          <h3>Total Transacted</h3>
          <p style={{ fontSize: '2rem', margin: '12px 0', fontWeight: 'bold' }}>0 <span style={{fontSize: '1rem'}}>sats</span></p>
          <p style={{ opacity: 0.7 }}>0 invoices settled</p>
        </div>

      </div>
    </div>
  );
}
