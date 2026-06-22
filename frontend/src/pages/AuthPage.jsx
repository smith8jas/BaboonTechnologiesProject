import React from 'react';
import { Activity, ArrowRight, Mail, ShieldCheck } from 'lucide-react';

import FinancialNetworkBackground from '../components/FinancialNetworkBackground.jsx';

export default function AuthPage({ mode, navigate, onSignIn, onSignUp }) {
  const isSignup = mode === 'signup';
  const [displayName, setDisplayName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [error, setError] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [password, setPassword] = React.useState('');
  const [signupSent, setSignupSent] = React.useState(false);

  React.useEffect(() => {
    setError('');
    setIsSubmitting(false);
    setSignupSent(false);
  }, [mode]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      if (isSignup) {
        const data = await onSignUp({ displayName, email, password });
        if (data?.session) {
          navigate('/chat');
          return;
        }
        setSignupSent(true);
      } else {
        await onSignIn({ email, password });
        navigate('/chat');
      }
    } catch (err) {
      setError(err.message || 'Authentication failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <FinancialNetworkBackground />

      <button className="auth-brand" type="button" onClick={() => navigate('/')}>
        <span className="brand-mark" aria-hidden="true">
          <Activity size={22} strokeWidth={2.4} />
        </span>
        <span>Baboon Analyst</span>
      </button>

      <section className="auth-panel" aria-label={isSignup ? 'Create account' : 'Sign in'}>
        <div className="auth-copy">
          <span className="auth-kicker">
            <ShieldCheck size={16} />
            Secure research workspace
          </span>
          <h1>{isSignup ? 'Create your analyst account' : 'Welcome back'}</h1>
          <p>
            Save research threads, keep agent context tied to your account, and return to
            prior company analyses whenever you need them.
          </p>
        </div>

        {signupSent ? (
          <div className="auth-confirmation">
            <Mail size={24} />
            <h2>Check your email</h2>
            <p>
              Supabase sent a confirmation link to <strong>{email}</strong>. Confirm it,
              then sign in here.
            </p>
            <button
              className="auth-confirmation-action"
              type="button"
              onClick={() => {
                setSignupSent(false);
                navigate('/login');
              }}
            >
              Go to Sign In
              <ArrowRight size={16} />
            </button>
          </div>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            {isSignup && (
              <label>
                <span>Name</span>
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Jane Analyst"
                  autoComplete="name"
                />
              </label>
            )}

            <label>
              <span>Email</span>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                type="email"
                autoComplete="email"
                required
              />
            </label>

            <label>
              <span>Password</span>
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Minimum 6 characters"
                type="password"
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                minLength={6}
                required
              />
            </label>

            {error && <p className="auth-error">{error}</p>}

            <button className="auth-submit" type="submit" disabled={isSubmitting}>
              <span>{isSubmitting ? 'Working...' : isSignup ? 'Create Account' : 'Sign In'}</span>
              <ArrowRight size={16} />
            </button>

            <p className="auth-switch">
              {isSignup ? 'Already have an account?' : 'New here?'}
              <button type="button" onClick={() => navigate(isSignup ? '/login' : '/signup')}>
                {isSignup ? 'Sign in' : 'Create one'}
              </button>
            </p>
          </form>
        )}
      </section>
    </main>
  );
}
