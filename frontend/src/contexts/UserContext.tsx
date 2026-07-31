import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { auth, db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

interface User {
  name: string;
  email?: string;
  full_name?: string;
  user_image?: string;
}

interface UserContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const UserContext = createContext<UserContextType | undefined>(undefined);
const HOME_URL = '/huf';
const LOGIN_URL = '/login?redirect-to=';

interface UserProviderProps {
  children: ReactNode;
}

function getSessionUserId(): string | null {
  // 1. Server-rendered boot data
  const bootUser = (window as unknown as { frappe?: { boot?: { user?: { name?: string } } } }).frappe?.boot?.user?.name;
  if (bootUser && bootUser !== 'Guest') {
    return bootUser;
  }
  // 2. Standard Frappe 'user_id' cookie (used by official Frappe apps like CRM/Raven)
  try {
    const cookies = new URLSearchParams(document.cookie.split('; ').join('&'));
    const cookieUser = cookies.get('user_id');
    if (cookieUser && cookieUser !== 'Guest') {
      return decodeURIComponent(cookieUser);
    }
  } catch {
    // Ignore parsing errors
  }
  return null;
}

export function UserProvider({ children }: UserProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUserDetails = async (userId: string): Promise<User | null> => {
    try {
      const userDoc = await db.getDoc(doctype.User, userId);
      return {
        name: userDoc.name || userId,
        email: userDoc.email,
        full_name: userDoc.full_name || userDoc.name,
        user_image: userDoc.user_image,
      };
    } catch (error) {
      console.error('Error fetching user details:', error);
      // Return basic user info if fetch fails
      return {
        name: userId,
        full_name: userId,
      };
    }
  };

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  /**
   * A single blip on this endpoint (cold worker, cache clear, brief network
   * hiccup) must not be treated the same as an actual logged-out session —
   * that was forcing a hard redirect to /login on a still-valid cookie.
   * Retry a couple of times before concluding the user is really signed out.
   */
  const RETRY_DELAYS_MS = [400, 1200];

  const getLoggedInUserWithRetry = async (): Promise<string | null> => {
    let lastError: unknown;
    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
      try {
        return await auth.getLoggedInUser();
      } catch (error) {
        lastError = error;
        if (attempt < RETRY_DELAYS_MS.length) {
          await sleep(RETRY_DELAYS_MS[attempt]);
        }
      }
    }
    throw lastError;
  };

  const redirectToLogin = () => {
    // Preserve where the user was headed so login can bounce them back.
    const currentPath = window.location.pathname + window.location.search;
    const redirectTo = encodeURIComponent(currentPath || HOME_URL);
    window.location.href = `${LOGIN_URL}${redirectTo}#login`;
  };

  const checkAuth = async () => {
    try {
      setIsLoading(true);
      // Fast path: server-rendered boot data or the standard Frappe
      // 'user_id' cookie, no network round-trip. Falls back to the API
      // (with retries — see getLoggedInUserWithRetry) only when neither is
      // available, e.g. on a fresh tab load before boot data is present.
      let loggedUserId = getSessionUserId();
      if (!loggedUserId) {
        try {
          const apiUser = await getLoggedInUserWithRetry();
          if (apiUser && apiUser !== 'Guest') {
            loggedUserId = apiUser;
          }
        } catch {
          loggedUserId = null;
        }
      }

      if (loggedUserId) {
        const userDetails = await fetchUserDetails(loggedUserId);
        setUser(userDetails);
      } else {
        setUser(null);
        redirectToLogin();
      }
    } catch (error) {
      console.error('Error checking authentication:', error);
      setUser(null);
      redirectToLogin();
    } finally {
      setIsLoading(false);
    }
  };

  const refreshUser = async () => {
    await checkAuth();
  };

  const logout = async () => {
    try {
      await auth.logout();
      setUser(null);
      const redirectTo = encodeURIComponent(HOME_URL);
      window.location.href = `${LOGIN_URL}${redirectTo}#login`;
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const value: UserContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    logout,
    refreshUser,
  };

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
}

