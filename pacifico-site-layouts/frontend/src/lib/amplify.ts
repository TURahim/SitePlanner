/**
 * AWS Amplify configuration for Cognito authentication
 */
import { Amplify } from '@aws-amplify/core';
import { config } from './config';

export function configureAmplify() {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.cognito.userPoolId,
        userPoolClientId: config.cognito.clientId,
      },
    },
  });
}

