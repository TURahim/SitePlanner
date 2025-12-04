/**
 * Application configuration from environment variables
 */
export const config = {
  // API - Default to AWS ALB when no env var is set
  apiUrl: import.meta.env.VITE_API_URL || 'http://pacifico-layouts-dev-alb-980890644.us-east-1.elb.amazonaws.com',
  
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

