"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  AnalysisDetail,
  AnalysisProgressPayload,
  fetchAnalysis,
  fetchAnalysisProgress,
  rerunAnalysis,
} from "@/lib/api";

function mergeProgressIntoDetail(
  detail: AnalysisDetail,
  progressPayload: AnalysisProgressPayload,
): AnalysisDetail {
  return {
    ...detail,
    request: progressPayload.request,
    progress: progressPayload.progress,
    presentation: {
      ...detail.presentation,
      artifact_statuses: progressPayload.presentation.artifact_statuses ?? [],
    },
    last_updated_at: progressPayload.last_updated_at ?? null,
  };
}

export function useAnalysisDetail(analysisId: string) {
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRerunning, setIsRerunning] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadDetail = useCallback(async () => {
    try {
      const payload = await fetchAnalysis(analysisId);
      if (!mountedRef.current) {
        return;
      }
      setDetail(payload);
      setError(null);
    } catch (loadError) {
      if (!mountedRef.current) {
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Unable to load analysis.");
    }
  }, [analysisId]);

  const loadProgress = useCallback(async () => {
    try {
      const payload = await fetchAnalysisProgress(analysisId);
      if (!mountedRef.current) {
        return;
      }

      setDetail((current) => (current ? mergeProgressIntoDetail(current, payload) : current));
      setError(null);

      if (payload.request.status === "complete" || payload.request.status === "failed") {
        await loadDetail();
      }
    } catch (loadError) {
      if (!mountedRef.current) {
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Unable to refresh analysis progress.");
    }
  }, [analysisId, loadDetail]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    if (!detail || ["complete", "failed"].includes(detail.request.status)) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadProgress();
    }, 2000);

    return () => {
      window.clearInterval(interval);
    };
  }, [detail?.request.status, loadProgress]);

  async function handleRerun() {
    setIsRerunning(true);
    try {
      await rerunAnalysis(analysisId);
      await loadDetail();
      setError(null);
    } catch (rerunError) {
      setError(rerunError instanceof Error ? rerunError.message : "Unable to rerun analysis.");
    } finally {
      setIsRerunning(false);
    }
  }

  return {
    detail,
    error,
    isRerunning,
    handleRerun,
    refreshDetail: () => loadDetail(),
  };
}
