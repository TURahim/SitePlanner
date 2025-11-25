/**
 * Main application layout with header and navigation
 */
import { Link, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './Layout.css';

export function Layout() {
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="header-content">
          <Link to="/" className="logo-link">
            <div className="logo">
              <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 7l6-4 6 4 6-4v14l-6 4-6-4-6 4V7z" />
                <path d="M9 3v14" />
                <path d="M15 7v14" />
              </svg>
              <span className="logo-text">Pacifico</span>
            </div>
          </Link>
          
          <nav className="nav-links">
            {isAuthenticated ? (
              <>
                <Link to="/projects" className="nav-link">Projects</Link>
                <div className="user-menu">
                  <span className="user-email">{user?.email}</span>
                  <button onClick={handleLogout} className="btn-logout">
                    Sign Out
                  </button>
                </div>
              </>
            ) : (
              <>
                <Link to="/login" className="nav-link">Sign In</Link>
                <Link to="/signup" className="btn-primary">Get Started</Link>
              </>
            )}
          </nav>
        </div>
      </header>
      
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

