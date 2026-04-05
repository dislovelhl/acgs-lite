import { useCallback, useEffect, useRef, useState } from "react";

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** Generic hook for async API calls with auto-refresh and error backoff. */
export function useApi<T>(
  fetcher: () => Promise<T>,
  refreshIntervalMs = 0,
): UseApiState<T> & { refresh: () => void } {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: true,
    error: null,
  });
  const mountedRef = useRef(true);
  const consecutiveErrorsRef = useRef(0);

  const refresh = useCallback(() => {
    setState((prev) => ({ ...prev, loading: !prev.data, error: null }));
    fetcher()
      .then((data) => {
        if (mountedRef.current) {
          consecutiveErrorsRef.current = 0;
          setState({ data, loading: false, error: null });
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          consecutiveErrorsRef.current++;
          setState((prev) => ({
            data: prev.data,
            loading: false,
            error: err instanceof Error ? err.message : String(err),
          }));
        }
      });
  }, [fetcher]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();

    let interval: ReturnType<typeof setInterval> | undefined;
    if (refreshIntervalMs > 0) {
      interval = setInterval(() => {
        // Back off exponentially on consecutive errors (max 60s)
        const backoff = Math.min(
          refreshIntervalMs * 2 ** consecutiveErrorsRef.current,
          60_000,
        );
        if (backoff <= refreshIntervalMs) {
          refresh();
        }
        // If backed off, skip this tick — the interval itself keeps running
        // so we re-check next tick.
      }, refreshIntervalMs);
    }
    return () => {
      mountedRef.current = false;
      if (interval) clearInterval(interval);
    };
  }, [refresh, refreshIntervalMs]);

  return { ...state, refresh };
}
