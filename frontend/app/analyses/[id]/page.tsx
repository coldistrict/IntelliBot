import { AnalysisDetailClient } from "@/components/analysis/analysis-detail-client";

type AnalysisDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function AnalysisDetailPage({ params }: AnalysisDetailPageProps) {
  const { id } = await params;
  return <AnalysisDetailClient analysisId={id} />;
}
