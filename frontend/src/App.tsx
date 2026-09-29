import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Register from './pages/Register';
import Discover from './pages/Discover';
import './index.css';

function App() {
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  return (
    <Router>
      <div className="app-container">
        <nav className="navbar glass-panel" style={{ margin: '16px', borderRadius: '16px' }}>
          <div style={{ fontWeight: 'bold', fontSize: '1.2rem', letterSpacing: '1px' }}>
            ⚡ Kuberbolt
          </div>
          <div className="nav-links">
            <Link to="/">Dashboard</Link>
            <Link to="/register">Register Agent</Link>
            <Link to="/discover">Discover</Link>
          </div>
          <button className="theme-toggle" onClick={toggleTheme}>
            {theme === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode'}
          </button>
        </nav>

        <main style={{ padding: '0 32px', maxWidth: '1200px', margin: '0 auto' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/register" element={<Register />} />
            <Route path="/discover" element={<Discover />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
