/**
 * Application configuration from environment variables
 */
export const config = {
  // API
  apiUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  
  // Cognito
  cognito: {
    userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
    clientId: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
    region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
  },
} as const;

// Validate required config in production
if (import.meta.env.PROD) {
  if (!config.cognito.userPoolId) {
    console.error('Missing VITE_COGNITO_USER_POOL_ID');
  }
  if (!config.cognito.clientId) {
    console.error('Missing VITE_COGNITO_CLIENT_ID');
  }
}

