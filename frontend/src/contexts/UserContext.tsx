import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { auth } from '@/lib/frappe-sdk';

// interface User {
//   name: string;
//   email?: string;
//   full_name?: string;
// }

type LoggedInUser = string;

interface UserContextType {
  user: LoggedInUser | null;
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

export function UserProvider({ children }: UserProviderProps) {
  const [user, setUser] = useState<LoggedInUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const checkAuth = async () => {
    try {
      setIsLoading(true);
      const loggedUser = await auth.getLoggedInUser();
      if (loggedUser) {
        setUser(loggedUser);
      } else {
        setUser(null);
        // Redirect to login with return URL
        const redirectTo = encodeURIComponent(HOME_URL);
        window.location.href = `${LOGIN_URL}${redirectTo}#login`;
      }
    } catch (error) {
      console.error('Error checking authentication:', error);
      setUser(null);
      // Redirect to login on error
      const redirectTo = encodeURIComponent(HOME_URL);
      window.location.href = `${LOGIN_URL}${redirectTo}#login`;
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

