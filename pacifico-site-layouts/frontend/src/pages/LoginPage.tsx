/**
 * Login page with support for unverified account confirmation
 */
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { resendSignUpCode } from 'aws-amplify/auth';
import './AuthPages.css';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // Confirmation flow for unverified accounts
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [confirmCode, setConfirmCode] = useState('');
  const [resendMessage, setResendMessage] = useState('');
  
  const { login, confirmRegistration } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: Location })?.from?.pathname || '/projects';

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to sign in';
      
      // Check if account needs confirmation
      if (message.includes('confirm') || message.includes('not confirmed')) {
        setNeedsConfirmation(true);
        setError('');
      } else {
        setError(message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await confirmRegistration(email, confirmCode);
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to confirm account');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendCode = async () => {
    try {
      setResendMessage('');
      await resendSignUpCode({ username: email });
      setResendMessage('A new code has been sent to your email.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resend code');
    }
  };

  // Show confirmation form if account needs verification
  if (needsConfirmation) {
    return (
      <div className="auth-page">
        <div className="auth-container">
          <div className="auth-header">
            <h1>Confirm your account</h1>
            <p>Enter the verification code sent to <strong>{email}</strong></p>
          </div>

          <form onSubmit={handleConfirm} className="auth-form">
            {error && <div className="auth-error">{error}</div>}
            {resendMessage && <div className="auth-success">{resendMessage}</div>}
            
            <div className="form-group">
              <label htmlFor="code">Confirmation code</label>
              <input
                id="code"
                type="text"
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value)}
                placeholder="123456"
                required
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
              />
            </div>

            <button type="submit" className="auth-submit" disabled={isLoading}>
              {isLoading ? 'Confirming...' : 'Confirm Account'}
            </button>
          </form>

          <div className="auth-footer-actions">
            <button type="button" className="link-button" onClick={handleResendCode}>
              Resend code
            </button>
            <span className="divider">·</span>
            <button 
              type="button" 
              className="link-button" 
              onClick={() => setNeedsConfirmation(false)}
            >
              Back to login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-header">
          <h1>Welcome back</h1>
          <p>Sign in to your account to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}
          
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              autoComplete="current-password"
            />
          </div>

          <button type="submit" className="auth-submit" disabled={isLoading}>
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="auth-footer">
          Don't have an account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  );
}
