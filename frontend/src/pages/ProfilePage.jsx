import React from 'react';
import { Activity, ArrowLeft, Check, Save, UserRound } from 'lucide-react';

import ChatDataBackground from '../components/ChatDataBackground.jsx';

const EMPTY_PROFILE = {
  display_name: '',
  username: '',
  full_name: '',
  age: '',
  role_title: '',
  company: '',
  avatar_url: '',
  bio: '',
};

export default function ProfilePage({
  apiStatus,
  navigate,
  onSaveProfile,
  profile,
  user,
}) {
  const [draft, setDraft] = React.useState(EMPTY_PROFILE);
  const [error, setError] = React.useState('');
  const [isSaving, setIsSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    setDraft({
      display_name: profile?.display_name ?? '',
      username: profile?.username ?? '',
      full_name: profile?.full_name ?? '',
      age: profile?.age ?? '',
      role_title: profile?.role_title ?? '',
      company: profile?.company ?? '',
      avatar_url: profile?.avatar_url ?? '',
      bio: profile?.bio ?? '',
    });
  }, [profile]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setSaved(false);
    setIsSaving(true);

    try {
      await onSaveProfile({
        ...draft,
        age: draft.age === '' ? null : Number(draft.age),
      });
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1800);
    } catch (err) {
      setError(err.message || 'Could not update profile.');
    } finally {
      setIsSaving(false);
    }
  }

  function updateField(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  const initials = (draft.display_name || draft.full_name || user?.email || 'BA')
    .slice(0, 2)
    .toUpperCase();

  return (
    <section className="profile-page" aria-label="Profile settings">
      <ChatDataBackground />

      <header className="profile-topbar">
        <button className="topbar-icon" type="button" onClick={() => navigate('/chat')} title="Back to chat">
          <ArrowLeft size={18} />
        </button>
        <button className="profile-brand" type="button" onClick={() => navigate('/')}>
          <Activity size={19} />
          <strong>Baboon Analyst</strong>
        </button>
        <div className={`chat-status ${apiStatus}`} aria-live="polite">
          <span />
          <strong>{apiStatus === 'online' ? 'Connected' : apiStatus}</strong>
        </div>
      </header>

      <main className="profile-content">
        <div className="profile-heading">
          <span>
            <UserRound size={16} />
            Account Profile
          </span>
          <h1>Personal research workspace</h1>
        </div>

        <form className="profile-form" onSubmit={handleSubmit}>
          <section className="profile-avatar-panel" aria-label="Profile image preview">
            <div className="profile-avatar">
              {draft.avatar_url ? (
                <img src={draft.avatar_url} alt="" />
              ) : (
                <span>{initials}</span>
              )}
            </div>
            <div>
              <h2>{draft.display_name || draft.full_name || 'Your profile'}</h2>
              <p>{user?.email}</p>
            </div>
          </section>

          <div className="profile-grid">
            <label>
              <span>Display name</span>
              <input
                value={draft.display_name}
                onChange={(event) => updateField('display_name', event.target.value)}
                placeholder="Jane Analyst"
              />
            </label>

            <label>
              <span>Username</span>
              <input
                value={draft.username}
                onChange={(event) => updateField('username', event.target.value)}
                placeholder="jane_analyst"
                pattern="[A-Za-z0-9_]{3,32}"
              />
            </label>

            <label>
              <span>Full name</span>
              <input
                value={draft.full_name}
                onChange={(event) => updateField('full_name', event.target.value)}
                placeholder="Jane Smith"
              />
            </label>

            <label>
              <span>Age</span>
              <input
                value={draft.age}
                onChange={(event) => updateField('age', event.target.value)}
                placeholder="29"
                type="number"
                min="13"
                max="130"
              />
            </label>

            <label>
              <span>Role</span>
              <input
                value={draft.role_title}
                onChange={(event) => updateField('role_title', event.target.value)}
                placeholder="Investor, analyst, founder..."
              />
            </label>

            <label>
              <span>Company</span>
              <input
                value={draft.company}
                onChange={(event) => updateField('company', event.target.value)}
                placeholder="Optional"
              />
            </label>
          </div>

          <label className="profile-wide-field">
            <span>Avatar image URL</span>
            <input
              value={draft.avatar_url}
              onChange={(event) => updateField('avatar_url', event.target.value)}
              placeholder="https://..."
              type="url"
            />
          </label>

          <label className="profile-wide-field">
            <span>Bio</span>
            <textarea
              value={draft.bio}
              onChange={(event) => updateField('bio', event.target.value)}
              placeholder="How you use Baboon Analyst, what you research, or notes for collaborators."
              rows={5}
            />
          </label>

          {error && <p className="auth-error">{error}</p>}

          <div className="profile-actions">
            <button type="button" className="ghost-action" onClick={() => navigate('/chat')}>
              Back to Chat
            </button>
            <button className="auth-submit" type="submit" disabled={isSaving}>
              {saved ? <Check size={16} /> : <Save size={16} />}
              <span>{saved ? 'Saved' : isSaving ? 'Saving...' : 'Save Profile'}</span>
            </button>
          </div>
        </form>
      </main>
    </section>
  );
}
