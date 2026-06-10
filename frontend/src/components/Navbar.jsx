import React from 'react';
import { Activity, ArrowRight, Circle, LogOut, Moon, Sun, UserRound } from 'lucide-react';

import { navItems } from '../data/landingContent.js';

export default function Navbar({
  apiStatus,
  isAuthenticated,
  navigate,
  onOpenProfile,
  onSignOut,
  onToggleTheme,
  theme,
  user,
}) {
  return (
    <header className="navbar">
      <button className="nav-brand" type="button" onClick={() => navigate('/')}>
        <span className="brand-mark" aria-hidden="true">
          <Activity size={22} strokeWidth={2.4} />
        </span>
        <span>Baboon Analyst</span>
      </button>

      <nav aria-label="Landing sections">
        {navItems.map((item) => (
          <button key={item.path} type="button" onClick={() => navigate(item.path)}>
            {item.label}
          </button>
        ))}
      </nav>

      <div className="nav-actions">
        <button
          className="theme-toggle"
          type="button"
          onClick={onToggleTheme}
          title="Toggle light / dark mode"
          aria-label="Toggle color theme"
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <div className={`status-pill ${apiStatus}`} aria-live="polite">
          <Circle size={9} fill="currentColor" strokeWidth={0} />
          <span>{apiStatus}</span>
        </div>
        {isAuthenticated ? (
          <>
            <button className="account-action" type="button" onClick={onOpenProfile} title={user?.email || 'Profile'}>
              <UserRound size={15} />
              <span>Profile</span>
            </button>
            <button className="account-action" type="button" onClick={onSignOut} title="Sign out">
              <LogOut size={15} />
              <span>Sign Out</span>
            </button>
          </>
        ) : (
          <button className="account-action" type="button" onClick={() => navigate('/login')}>
            <span>Sign In</span>
          </button>
        )}
        <button className="nav-cta" type="button" onClick={() => navigate('/chat')}>
          <span>Start Analysis</span>
          <ArrowRight size={16} />
        </button>
      </div>
    </header>
  );
}
