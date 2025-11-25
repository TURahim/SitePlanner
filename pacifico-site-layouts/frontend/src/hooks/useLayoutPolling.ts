/**
 * Custom hook for polling layout generation status (C-05)
 * 
 * Polls the /api/layouts/{id}/status endpoint every few seconds
 * until the layout is completed or failed.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { getLayoutStatus, getLayout } from '../lib/api';
import type { LayoutStatusResponse, LayoutDetail } from '../types';

export interface UseLayoutPollingOptions {
  /** Polling interval in milliseconds (default: 2000ms) */
  interval?: number;
  /** Callback when layout is completed */
  onComplete?: (status: LayoutStatusResponse) => void;
  /** Callback when layout fails */
  onError?: (error: string) => void;
}

export interface UseLayoutPollingResult {
  /** Current layout status */
  status: LayoutStatusResponse | null;
  /** Whether polling is active */
  isPolling: boolean;
  /** Start polling for a layout */
  startPolling: (layoutId: string) => void;
  /** Stop polling */
  stopPolling: () => void;
  /** Error message if any */
  error: string | null;
  /** Elapsed time since polling started (in seconds) */
  elapsedTime: number;
  /** Full layout data (fetched when completed) */
  layoutData: LayoutDetail | null;
}

const DEFAULT_INTERVAL = 2000; // 2 seconds

export function useLayoutPolling(
  options: UseLayoutPollingOptions = {}
): UseLayoutPollingResult {
  const {
    interval = DEFAULT_INTERVAL,
    onComplete,
    onError,
  } = options;

  const [layoutId, setLayoutId] = useState<string | null>(null);
  const [status, setStatus] = useState<LayoutStatusResponse | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [layoutData, setLayoutData] = useState<LayoutDetail | null>(null);
  
  // Refs for cleanup
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const elapsedIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number | null>(null);

  // Cleanup function
  const cleanup = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (elapsedIntervalRef.current) {
      clearInterval(elapsedIntervalRef.current);
      elapsedIntervalRef.current = null;
    }
  }, []);

  // Stop polling
  const stopPolling = useCallback(() => {
    cleanup();
    setIsPolling(false);
  }, [cleanup]);

  // Fetch full layout data when completed
  const fetchLayoutData = useCallback(async (id: string) => {
    try {
      const data = await getLayout(id);
      setLayoutData(data);
    } catch (err) {
      console.error('Failed to fetch layout data:', err);
    }
  }, []);

  // Poll for status
  const pollStatus = useCallback(async () => {
    if (!layoutId) return;

    try {
      const response = await getLayoutStatus(layoutId);
      setStatus(response);
      setError(null);

      // Check if completed or failed
      if (response.status === 'completed') {
        stopPolling();
        onComplete?.(response);
        // Fetch full layout data
        fetchLayoutData(layoutId);
      } else if (response.status === 'failed') {
        stopPolling();
        const errorMsg = response.error_message || 'Layout generation failed';
        setError(errorMsg);
        onError?.(errorMsg);
      }
    } catch (err) {
      console.error('Failed to poll layout status:', err);
      // Don't stop polling on network errors - could be temporary
    }
  }, [layoutId, stopPolling, onComplete, onError, fetchLayoutData]);

  // Start polling
  const startPolling = useCallback((id: string) => {
    // Reset state
    setLayoutId(id);
    setStatus(null);
    setError(null);
    setElapsedTime(0);
    setLayoutData(null);
    setIsPolling(true);
    startTimeRef.current = Date.now();

    // Initial poll immediately
    getLayoutStatus(id)
      .then((response) => {
        setStatus(response);
        if (response.status === 'completed') {
          setIsPolling(false);
          onComplete?.(response);
          fetchLayoutData(id);
        } else if (response.status === 'failed') {
          setIsPolling(false);
          const errorMsg = response.error_message || 'Layout generation failed';
          setError(errorMsg);
          onError?.(errorMsg);
        }
      })
      .catch((err) => {
        console.error('Initial poll failed:', err);
      });
  }, [onComplete, onError, fetchLayoutData]);

  // Set up polling interval
  useEffect(() => {
    if (!isPolling || !layoutId) return;

    // Poll at regular intervals
    intervalRef.current = setInterval(pollStatus, interval);

    // Update elapsed time every second
    elapsedIntervalRef.current = setInterval(() => {
      if (startTimeRef.current) {
        setElapsedTime(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    }, 1000);

    return cleanup;
  }, [isPolling, layoutId, interval, pollStatus, cleanup]);

  // Cleanup on unmount
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  return {
    status,
    isPolling,
    startPolling,
    stopPolling,
    error,
    elapsedTime,
    layoutData,
  };
}

/**
 * Format elapsed time as MM:SS
 */
export function formatElapsedTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

