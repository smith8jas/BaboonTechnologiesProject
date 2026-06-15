import React from 'react';

import { hasSupabaseConfig, supabase } from './supabaseClient.js';

const AuthContext = React.createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return undefined;
    }

    let mounted = true;

    supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session ?? null);
        setLoading(false);
      }
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });

    return () => {
      mounted = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  const value = React.useMemo(
    () => ({
      accessToken: session?.access_token ?? null,
      isConfigured: hasSupabaseConfig,
      isAuthenticated: Boolean(session?.user),
      loading,
      session,
      user: session?.user ?? null,
      async signIn({ email, password }) {
        if (!supabase) {
          throw new Error('Supabase is not configured.');
        }
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        return data;
      },
      async signOut() {
        if (!supabase) {
          return;
        }
        const { error } = await supabase.auth.signOut();
        if (error) throw error;
      },
      async signUp({ email, password, displayName }) {
        if (!supabase) {
          throw new Error('Supabase is not configured.');
        }
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: {
              display_name: displayName,
            },
          },
        });
        if (error) throw error;
        return data;
      },
    }),
    [loading, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider.');
  }
  return context;
}
