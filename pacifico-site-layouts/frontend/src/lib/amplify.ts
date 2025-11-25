/**
 * AWS Amplify configuration for Cognito authentication
 */
import { Amplify } from 'aws-amplify';
import { config } from './config';

export function configureAmplify() {
  // Validate config before configuring
  if (!config.cognito.userPoolId || !config.cognito.clientId || !config.cognito.region) {
    console.error('Cognito configuration missing!', {
      userPoolId: config.cognito.userPoolId ? '✓ set' : '✗ MISSING',
      clientId: config.cognito.clientId ? '✓ set' : '✗ MISSING',
      region: config.cognito.region ? '✓ set' : '✗ MISSING',
    });
    console.error(
      'Make sure .env.development has VITE_COGNITO_USER_POOL_ID, VITE_COGNITO_CLIENT_ID, and VITE_AWS_REGION'
    );
    return;
  }

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.cognito.userPoolId,
        userPoolClientId: config.cognito.clientId,
      },
    },
  });

  // Log successful configuration in development
  if (import.meta.env.DEV) {
    console.log('Amplify configured with User Pool:', config.cognito.userPoolId);
  }
}

