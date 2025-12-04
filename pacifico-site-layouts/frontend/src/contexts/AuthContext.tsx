/**
 * Authentication context for managing user state
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import {
  signIn,
  signUp,
  signOut,
  getCurrentUser,
  confirmSignUp,
  type SignInInput,
  type SignUpInput,
} from 'aws-amplify/auth';
import type { AuthState, User } from '../types';
import { demoLogin as apiDemoLogin, getDemoToken, clearDemoToken } from '../lib/api';

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<{ needsConfirmation: boolean }>;
  confirmRegistration: (email: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  demoLogin: () => Promise<void>;
  isDemo: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

async function checkAuthState(setState: (state: AuthState & { isDemo: boolean }) => void) {
  // First check for demo token
  const demoToken = getDemoToken();
  if (demoToken) {
    // Restore demo user from localStorage
    const storedUser = localStorage.getItem('demo_user');
    if (storedUser) {
      try {
        const user = JSON.parse(storedUser) as User;
        setState({ user, isAuthenticated: true, isLoading: false, isDemo: true });
        return;
      } catch {
        // Invalid stored user, clear and continue
        clearDemoToken();
        localStorage.removeItem('demo_user');
      }
    }
  }
  
  // Otherwise try Cognito
  try {
    const cognitoUser = await getCurrentUser();
    const user: User = {
      id: cognitoUser.userId,
      email: cognitoUser.signInDetails?.loginId || '',
      name: cognitoUser.username,
    };
    setState({ user, isAuthenticated: true, isLoading: false, isDemo: false });
  } catch {
    setState({ user: null, isAuthenticated: false, isLoading: false, isDemo: false });
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState & { isDemo: boolean }>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
    isDemo: false,
  });

  // Check for existing session on mount
  useEffect(() => {
    checkAuthState(setState);
  }, []);

  async function login(email: string, password: string) {
    const input: SignInInput = { username: email, password };
    const result = await signIn(input);
    
    if (result.isSignedIn) {
      await checkAuthState(setState);
    } else if (result.nextStep?.signInStep === 'CONFIRM_SIGN_UP') {
      throw new Error('Please confirm your email address first');
    }
  }

  const register = async (email: string, password: string, name?: string) => {
    const input: SignUpInput = {
      username: email,
      password,
      options: {
        userAttributes: {
          email,
          ...(name && { name }),
        },
      },
    };
    
    const result = await signUp(input);
    return { needsConfirmation: !result.isSignUpComplete };
  };

  const confirmRegistration = async (email: string, code: string) => {
    await confirmSignUp({ username: email, confirmationCode: code });
  };

  const logout = async () => {
    // Clear demo token if in demo mode
    if (state.isDemo) {
      clearDemoToken();
      localStorage.removeItem('demo_user');
    } else {
      await signOut();
    }
    setState({ user: null, isAuthenticated: false, isLoading: false, isDemo: false });
  };

  const demoLogin = async () => {
    setState(prev => ({ ...prev, isLoading: true }));
    try {
      const response = await apiDemoLogin();
      // Store user for session restoration
      localStorage.setItem('demo_user', JSON.stringify(response.user));
      setState({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
        isDemo: true,
      });
    } catch (error) {
      setState(prev => ({ ...prev, isLoading: false }));
      throw error;
    }
  };

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        register,
        confirmRegistration,
        logout,
        demoLogin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

