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

  const checkAuth = async () => {
    try {
      setIsLoading(true);
      const loggedUserId = await auth.getLoggedInUser();
      if (loggedUserId) {
        const userDetails = await fetchUserDetails(loggedUserId);
        setUser(userDetails);
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

