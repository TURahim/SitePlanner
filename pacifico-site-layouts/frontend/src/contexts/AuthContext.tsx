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

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<{ needsConfirmation: boolean }>;
  confirmRegistration: (email: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

async function checkAuthState(setState: (state: AuthState) => void) {
  try {
    const cognitoUser = await getCurrentUser();
    const user: User = {
      id: cognitoUser.userId,
      email: cognitoUser.signInDetails?.loginId || '',
      name: cognitoUser.username,
    };
    setState({ user, isAuthenticated: true, isLoading: false });
  } catch {
    setState({ user: null, isAuthenticated: false, isLoading: false });
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
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
    await signOut();
    setState({ user: null, isAuthenticated: false, isLoading: false });
  };

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        register,
        confirmRegistration,
        logout,
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

