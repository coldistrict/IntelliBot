import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisDetailClient } from "@/components/analysis/analysis-detail-client";
import { fetchAnalysis, fetchAnalysisProgress } from "@/lib/api";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchAnalysis: vi.fn(),
    fetchAnalysisProgress: vi.fn(),
    rerunAnalysis: vi.fn(),
  };
});

describe("AnalysisDetailClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("renders the memo layout, social timeline, and inspector", async () => {
    vi.mocked(fetchAnalysis).mockResolvedValue({
      request: {
        id: 1,
        mode: "manual",
        input_type: "custom_claim",
        input_text: "Will the Fed cut rates by June?",
        market_id: null,
        template_requested: "macro_policy",
        template_selected: "macro_policy",
        status: "complete",
        current_stage: "complete",
        error_message: null,
        started_at: "2026-04-06T12:00:00Z",
        completed_at: "2026-04-06T12:01:00Z",
        created_at: "2026-04-06T12:00:00Z",
        updated_at: "2026-04-06T12:01:00Z",
        latest_recommendation_label: "analysis_only",
        latest_confidence_label: "medium",
        review_count: 0,
        progress_percent: 100,
        current_stage_label: "Complete",
        current_stage_note: "The analysis has finished and the brief is ready to inspect.",
        display_summary: "Will the Fed cut rates by June? currently screens at YES 58% / NO 42%.",
        qualitative_label: "leans_yes",
      },
      market: null,
      latest_rule_parse: {
        question_text: "Will the Fed cut rates by June?",
        event: "Will the Fed cut rates by June?",
        entity_names: ["Fed"],
        action: "cut",
        claim_family: "macro_policy",
        yes_condition: "YES if the Fed cuts rates by June.",
        no_condition: "NO if the Fed does not cut rates by June.",
        deadline_text: "June 2026",
        resolution_definition: "Resolves YES if the Fed cuts by June.",
        directional_scoring_policy: {
          allowed_roles: ["outcome", "direct_support", "direct_contradiction", "commentary"],
        },
        official_resolution_source: null,
        official_domains: ["federalreserve.gov"],
        ambiguity_flags: [],
        clarity_score: 0.72,
        resolution_risk: 0.28,
        suitable_for_auto: false,
        template_detected: "macro_policy",
      },
      latest_run: {
        id: 10,
        request_id: 1,
        market_id: null,
        rule_parse_id: 2,
        template_selected: "macro_policy",
        market_mid_prob: null,
        yes_exec_price: null,
        no_exec_price: null,
        priced_in_risk_label: "medium",
        numeric_estimate_available: true,
        numeric_estimate_reason: null,
        qualitative_label: "leans_yes",
        p_hat: 0.58,
        p_low: 0.46,
        p_high: 0.69,
        confidence_label: "medium",
        recommendation_label: "analysis_only",
        why_wrong_summary: "This could be wrong if inflation re-accelerates.",
        final_summary: "The current brief leans modestly toward a June cut, but with meaningful uncertainty.",
        created_at: "2026-04-06T12:01:00Z",
      },
      recommendation: {
        recommendation_label: "analysis_only",
        confidence_label: "medium",
        edge_yes: null,
        edge_no: null,
        rationale_json: {},
      },
      progress: {
        current_stage: "complete",
        current_label: "Complete",
        current_note: "The analysis has finished and the brief is ready to inspect.",
        completed_count: 10,
        total_count: 10,
        percent_complete: 100,
        last_updated_at: "2026-04-06T12:01:00Z",
        stages: [],
      },
      audit: {
        rule_interpretation: {
          template: "macro_policy",
          claim_family: "macro_policy",
          action: "cut",
          yes_condition: "YES if the Fed cuts rates by June.",
          no_condition: "NO if the Fed does not cut rates by June.",
          deadline_text: "June 2026",
          resolution_definition: "Resolves YES if the Fed cuts by June.",
          clarity_score: 0.72,
          resolution_risk: 0.28,
        },
        source_lanes: {
          official: 1,
          news: 1,
          premium: 0,
          live_social: 1,
          manual_social: 0,
          manual_input: 0,
          total: 3,
          contributing_sources: 2,
        },
        social_modifier: {
          consensus_label: "bullish",
          consensus_strength: "strong",
          narrative_phase: "emerging",
          summary: "X sentiment is constructive but not euphoric.",
        },
        probability: {
          numeric_estimate_available: true,
          numeric_estimate_reason: null,
          prior_probability: 0.5,
          prior_logit: 0,
          non_social_evidence: 0.15,
          raw_social_evidence: 0.05,
          capped_social_evidence: 0.05,
          total_evidence: 0.2,
          p_hat: 0.58,
        },
        uncertainty: {
          base_uncertainty: 0.15,
          total_uncertainty: 0.23,
          p_low: 0.46,
          p_high: 0.69,
          adjustments: [
            {
              key: "resolution_risk",
              label: "Resolution risk",
              amount: 0.04,
              note: "Higher resolution risk adds uncertainty to the final range.",
            },
          ],
        },
        recommendation_math: {
          yes_exec_price: null,
          no_exec_price: null,
          friction_buffer: 0.02,
          edge_yes: null,
          edge_no: null,
          chosen_label: "analysis_only",
          note: "No market was linked, so this run remains analysis-only.",
        },
        confidence: {
          final_label: "medium",
          reason: "The setup has support but still carries meaningful policy uncertainty.",
        },
        factor_contributions: [
          {
            factor_id: 1,
            fact_claim_id: 1,
            source_title: "Reuters",
            source_kind: "news",
            source_tier: "reputable_news",
            stance: "yes",
            strength: "medium",
            evidence_role: "direct_support",
            used_in_scoring: true,
            exclusion_reason: null,
            directness: "direct",
            verifier_status: "supported",
            source_weight: 0.2,
            freshness_multiplier: 1,
            uniqueness_multiplier: 1,
            template_multiplier: 0.7,
            final_weight: 0.12,
            signed_contribution: 0.12,
            rationale: "Cooling data is making earlier easing more plausible.",
          },
        ],
      },
      presentation: {
        headline: "Will the Fed cut rates by June?",
        thesis: "Current read: YES 58% / NO 42% with medium confidence.",
        status_note: "The analysis has finished and the brief is ready to inspect.",
        brief_sections: {
          what_it_means: "The current brief leans modestly toward a June cut, but with meaningful uncertainty.",
          why_yes: [
            {
              factor_id: 1,
              source_id: 90,
              passage_id: 801,
              title: "Cooling data is making earlier easing more plausible.",
              note: "Reuters · direct support · signed weight +0.1200",
              evidence_role: "direct_support",
              source_title: "Reuters",
              signed_weight: 0.12,
            },
          ],
          why_no: [
            {
              factor_id: 2,
              source_id: 90,
              passage_id: 801,
              title: "Officials still sound patient on inflation risks.",
              note: "Reuters · direct contradiction · signed weight -0.0400",
              evidence_role: "direct_contradiction",
              source_title: "Reuters",
              signed_weight: -0.04,
            },
          ],
          context: [
            {
              factor_id: 3,
              source_id: 90,
              passage_id: 801,
              title: "Traders have already moved toward an earlier cut path.",
              note: "Reuters · commentary · Background, timing, and sentiment facts are contextual only.",
              evidence_role: "commentary",
              source_title: "Reuters",
              signed_weight: null,
            },
          ],
          caveats: "This could be wrong if inflation re-accelerates.",
        },
        artifact_statuses: [
          { key: "rule_parse", label: "Rules interpreted", status: "complete", note: "Rules parsed.", available: true },
          { key: "retrieval", label: "Sources grounded", status: "complete", note: "Sources grounded.", available: true },
          { key: "social_intelligence", label: "Social intelligence", status: "complete", note: "Live X complete.", available: true },
          { key: "factor_mapping", label: "Factors scored", status: "complete", note: "Factors ready.", available: true },
          { key: "brief_generation", label: "Brief written", status: "complete", note: "Brief written.", available: true },
          { key: "audit", label: "Audit ready", status: "complete", note: "Inspector ready.", available: true },
        ],
      },
      display_summary: "Will the Fed cut rates by June? currently screens at YES 58% / NO 42%.",
      last_updated_at: "2026-04-06T12:01:00Z",
      social_intel_summary: {
        id: 5,
        analysis_run_id: 10,
        consensus_label: "bullish",
        consensus_strength: "strong",
        narrative_phase: "emerging",
        summary: "Trusted macro accounts are leaning toward a June cut, while broad X sentiment is turning constructive rather than euphoric.",
        key_themes: ["fed path", "jobs data"],
        trusted_accounts_count: 1,
        broad_posts_sampled: 18,
        created_at: "2026-04-06T12:01:00Z",
      },
      sources: [
        {
          id: 90,
          title: "Reuters",
          url: "https://www.reuters.com/world/us/fed-cut-june-2026",
          domain: "reuters.com",
          source_kind: "news",
          source_tier: "reputable_news",
          excerpt: "Reuters reported that softer labor data is reopening the path toward a June cut.",
          published_at: "2026-04-06T11:40:00Z",
          is_paywalled: false,
          metadata_json: {},
        },
        {
          id: 100,
          title: "Nick Timiraos (@NickTimiraos)",
          url: "https://x.com/NickTimiraos/status/123",
          domain: "x.com",
          source_kind: "live_social",
          source_tier: "high_trust_social",
          excerpt: "He notes that recent data is pulling the market toward a faster easing path.",
          published_at: "2026-04-06T11:50:00Z",
          is_paywalled: false,
          metadata_json: {
            handle: "NickTimiraos",
            display_name: "Nick Timiraos",
            trust_reason: "Widely followed WSJ Fed reporter with a strong track record on policy signaling.",
            relevance_reason: "Frequently breaks Fed-related developments and is directly relevant to rate-cut pricing.",
            trust_confidence: 0.93,
          },
        },
      ],
      documents: [
        {
          id: 501,
          analysis_run_id: 10,
          source_id: 90,
          canonical_url: "https://www.reuters.com/world/us/fed-cut-june-2026",
          title: "Reuters",
          domain: "reuters.com",
          extractor: "trafilatura",
          word_count: 842,
          fetched_at: "2026-04-06T11:55:00Z",
          created_at: "2026-04-06T11:55:00Z",
        },
      ],
      passages: [
        {
          id: 801,
          analysis_run_id: 10,
          source_id: 90,
          document_id: 501,
          passage_index: 1,
          relevance_score: 2.75,
          text: "Fresh labor-market softening is reopening the path toward a June rate cut, according to traders and economists cited by Reuters.",
          created_at: "2026-04-06T11:55:00Z",
        },
      ],
      trusted_social_sources: [
        {
          id: 100,
          title: "Nick Timiraos (@NickTimiraos)",
          url: "https://x.com/NickTimiraos/status/123",
          domain: "x.com",
          source_kind: "live_social",
          source_tier: "high_trust_social",
          excerpt: "He notes that recent data is pulling the market toward a faster easing path.",
          published_at: "2026-04-06T11:50:00Z",
          is_paywalled: false,
          metadata_json: {
            handle: "NickTimiraos",
            display_name: "Nick Timiraos",
            trust_reason: "Widely followed WSJ Fed reporter with a strong track record on policy signaling.",
            relevance_reason: "Frequently breaks Fed-related developments and is directly relevant to rate-cut pricing.",
            trust_confidence: 0.93,
          },
        },
      ],
      fact_claims: [],
      factors: [],
      reviews: [],
    } as never);

    render(<AnalysisDetailClient analysisId="1" />);

    await waitFor(() => {
      expect(screen.getByText(/what this means/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/current read: yes 58% \/ no 42% with medium confidence/i)).toBeInTheDocument();
    expect(screen.getByText(/trusted accounts and narrative context/i)).toBeInTheDocument();
    expect(screen.getByText(/broader x consensus/i)).toBeInTheDocument();
    expect(
      screen.getByText(/broader x discussion currently reads as bullish with strong conviction in an emerging phase/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/18 posts/i)).toBeInTheDocument();
    expect(screen.getByText(/fed path/i)).toBeInTheDocument();
    expect(screen.getByText(/nick timiraos/i)).toBeInTheDocument();
    expect(screen.getByText(/ranked grounding passages/i)).toBeInTheDocument();
    expect(screen.getByText(/relevance 2.75/i)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /inspect/i })[0]);

    await waitFor(() => {
      expect(fetchAnalysis).toHaveBeenCalledTimes(2);
    });

    expect(screen.getByRole("dialog", { name: /how this was calculated/i })).toBeInTheDocument();
    expect(screen.getAllByText(/factor details/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/source grounding/i)).not.toHaveLength(0);
  });

  it("shows direct yes/no probabilities even for legacy qualitative-only runs", async () => {
    vi.mocked(fetchAnalysis).mockResolvedValue({
      request: {
        id: 22,
        mode: "manual",
        input_type: "custom_claim",
        input_text: "Will the supreme court side with Trump EO on birthright citizenship?",
        market_id: null,
        template_requested: "legal_case",
        template_selected: "legal_case",
        status: "complete",
        current_stage: "complete",
        error_message: null,
        started_at: "2026-04-09T04:00:00Z",
        completed_at: "2026-04-09T04:00:40Z",
        created_at: "2026-04-09T04:00:00Z",
        updated_at: "2026-04-09T04:00:40Z",
        latest_recommendation_label: "analysis_only",
        latest_confidence_label: "low",
        review_count: 0,
        progress_percent: 100,
        current_stage_label: "Complete",
        current_stage_note: "Analysis complete. The research brief and audit are ready.",
        display_summary:
          "Will the supreme court side with Trump EO on birthright citizenship? currently screens at YES 43% / NO 57%.",
        qualitative_label: "mixed",
      },
      market: null,
      latest_rule_parse: {
        question_text: "Will the supreme court side with Trump EO on birthright citizenship?",
        event: "Supreme Court birthright citizenship case",
        entity_names: ["Supreme Court", "Trump"],
        action: "side with",
        claim_family: "legal_case",
        yes_condition:
          "YES if the court upholds, allows, or lets Trump's executive order on birthright citizenship take effect on the merits.",
        no_condition:
          "NO if the court blocks, strikes down, invalidates, or rules against Trump's executive order on birthright citizenship on the merits.",
        deadline_text: null,
        resolution_definition: "Resolves on the merits of the executive order challenge.",
        directional_scoring_policy: {
          allowed_roles: ["outcome", "direct_support", "direct_contradiction", "commentary"],
        },
        official_resolution_source: null,
        official_domains: ["supremecourt.gov"],
        ambiguity_flags: [],
        clarity_score: 0.68,
        resolution_risk: 0.32,
        suitable_for_auto: false,
        template_detected: "legal_case",
      },
      latest_run: {
        id: 30,
        request_id: 22,
        market_id: null,
        rule_parse_id: 8,
        template_selected: "legal_case",
        market_mid_prob: null,
        yes_exec_price: null,
        no_exec_price: null,
        priced_in_risk_label: "high",
        numeric_estimate_available: false,
        numeric_estimate_reason: "net directional evidence is still below the numeric threshold",
        qualitative_label: "mixed",
        p_hat: 0.43,
        p_low: 0.31,
        p_high: 0.55,
        confidence_label: "low",
        recommendation_label: "analysis_only",
        why_wrong_summary: "This could be wrong if the court reaches the merits faster than expected.",
        final_summary:
          "Will the supreme court side with Trump EO on birthright citizenship? currently screens at YES 43% / NO 57%.",
        created_at: "2026-04-09T04:00:40Z",
      },
      recommendation: {
        recommendation_label: "analysis_only",
        confidence_label: "low",
        edge_yes: null,
        edge_no: null,
        rationale_json: {
          reason: "No executable market prices were available for edge evaluation.",
        },
      },
      progress: {
        current_stage: "complete",
        current_label: "Complete",
        current_note: "Analysis complete. The research brief and audit are ready.",
        completed_count: 10,
        total_count: 10,
        percent_complete: 100,
        last_updated_at: "2026-04-09T04:00:40Z",
        stages: [],
      },
      audit: {
        rule_interpretation: {
          template: "legal_case",
          claim_family: "legal_case",
          action: "side with",
          yes_condition:
            "YES if the court upholds, allows, or lets Trump's executive order on birthright citizenship take effect on the merits.",
          no_condition:
            "NO if the court blocks, strikes down, invalidates, or rules against Trump's executive order on birthright citizenship on the merits.",
          deadline_text: null,
          resolution_definition: "Resolves on the merits of the executive order challenge.",
          clarity_score: 0.68,
          resolution_risk: 0.32,
        },
        source_lanes: {
          official: 1,
          news: 2,
          premium: 0,
          live_social: 0,
          manual_social: 0,
          manual_input: 1,
          total: 4,
          contributing_sources: 2,
        },
        social_modifier: null,
        probability: {
          numeric_estimate_available: false,
          numeric_estimate_reason: "net directional evidence is still below the numeric threshold",
          prior_probability: null,
          prior_logit: null,
          non_social_evidence: -0.07,
          raw_social_evidence: 0,
          capped_social_evidence: 0,
          total_evidence: -0.07,
          p_hat: 0.43,
        },
        uncertainty: {
          base_uncertainty: 0.14,
          total_uncertainty: 0.24,
          p_low: 0.31,
          p_high: 0.55,
          adjustments: [],
        },
        recommendation_math: {
          yes_exec_price: null,
          no_exec_price: null,
          friction_buffer: null,
          edge_yes: null,
          edge_no: null,
          chosen_label: "analysis_only",
          note: "No executable market prices were available for edge evaluation.",
        },
        confidence: {
          final_label: "low",
          reason: "The run stayed qualitative-only with limited directional evidence.",
        },
        factor_contributions: [],
      },
      presentation: {
        headline: "Will the supreme court side with Trump EO on birthright citizenship?",
        thesis: "Current read: YES 43% / NO 57% with low confidence.",
        status_note: "Analysis complete. The research brief and audit are ready.",
        brief_sections: {
          what_it_means:
            "Will the supreme court side with Trump EO on birthright citizenship? currently screens at YES 43% / NO 57%.",
          why_yes: [],
          why_no: [],
          context: [],
          caveats: "This could be wrong if the court reaches the merits faster than expected.",
        },
        artifact_statuses: [
          { key: "rule_parse", label: "Rules interpreted", status: "complete", note: "Rules parsed.", available: true },
        ],
      },
      display_summary:
        "Will the supreme court side with Trump EO on birthright citizenship? currently screens at YES 43% / NO 57%.",
      last_updated_at: "2026-04-09T04:00:40Z",
      social_intel_summary: null,
      sources: [],
      documents: [],
      passages: [],
      trusted_social_sources: [],
      fact_claims: [],
      factors: [],
      reviews: [],
    } as never);

    render(<AnalysisDetailClient analysisId="22" />);

    await waitFor(() => {
      expect(screen.getByText(/current read: yes 43% \/ no 57% with low confidence/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/most likely: no/i)).toBeInTheDocument();
    expect(screen.getByText(/model yes read/i)).toBeInTheDocument();
    expect(screen.getByText(/model no read/i)).toBeInTheDocument();
    expect(screen.getByText(/polymarket prior/i)).toBeInTheDocument();
    expect(screen.getAllByText("43%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("57%").length).toBeGreaterThan(0);
    expect(screen.queryByText("31% - 55%")).not.toBeInTheDocument();
    expect(screen.queryByText(/numeric estimate withheld/i)).not.toBeInTheDocument();
  });

  it("explains missing probability clearly when no directional read exists", async () => {
    vi.mocked(fetchAnalysis).mockResolvedValue({
      request: {
        id: 30,
        mode: "manual",
        input_type: "custom_claim",
        input_text: "Will the war in Iran automatically restart after the cease fire?",
        market_id: null,
        template_requested: "generic_manual",
        template_selected: "generic_manual",
        status: "complete",
        current_stage: "complete",
        error_message: null,
        started_at: "2026-04-18T18:10:06Z",
        completed_at: "2026-04-18T18:10:20Z",
        created_at: "2026-04-18T18:10:06Z",
        updated_at: "2026-04-18T18:10:20Z",
        latest_recommendation_label: "analysis_only",
        latest_confidence_label: "low",
        review_count: 0,
        progress_percent: 100,
        current_stage_label: "Complete",
        current_stage_note: "Analysis complete. The research brief and audit are ready.",
        display_summary:
          "Will the war in Iran automatically restart after the cease fire? currently reads as insufficient basis.",
        qualitative_label: "insufficient_basis",
      },
      market: null,
      latest_rule_parse: {
        question_text: "Will the war in Iran automatically restart after the cease fire?",
        event: "Will the war in Iran automatically restart after the cease fire?",
        entity_names: ["Iran"],
        action: "restart",
        claim_family: "generic_manual",
        yes_condition: "YES if the war in Iran automatically restart after the cease fire happens.",
        no_condition: "NO if the war in Iran automatically restart after the cease fire does not happen.",
        deadline_text: null,
        resolution_definition: "Will the war in Iran automatically restart after the cease fire?",
        directional_scoring_policy: {
          allowed_roles: ["outcome", "direct_support", "direct_contradiction"],
        },
        official_resolution_source: null,
        official_domains: [],
        ambiguity_flags: [],
        clarity_score: 0.68,
        resolution_risk: 0.32,
        suitable_for_auto: false,
        template_detected: "generic_manual",
      },
      latest_run: {
        id: 40,
        request_id: 30,
        market_id: null,
        rule_parse_id: 18,
        template_selected: "generic_manual",
        market_mid_prob: null,
        yes_exec_price: null,
        no_exec_price: null,
        priced_in_risk_label: "high",
        numeric_estimate_available: false,
        numeric_estimate_reason: "there are fewer than two scored directional factors",
        qualitative_label: "insufficient_basis",
        p_hat: null,
        p_low: null,
        p_high: null,
        confidence_label: "low",
        recommendation_label: "analysis_only",
        why_wrong_summary: "This could still change if stronger direct evidence appears.",
        final_summary:
          "Will the war in Iran automatically restart after the cease fire? currently reads as insufficient basis.",
        created_at: "2026-04-18T18:10:20Z",
      },
      recommendation: {
        recommendation_label: "analysis_only",
        confidence_label: "low",
        edge_yes: null,
        edge_no: null,
        rationale_json: {
          reason: "there are fewer than two scored directional factors",
        },
      },
      progress: {
        current_stage: "complete",
        current_label: "Complete",
        current_note: "Analysis complete. The research brief and audit are ready.",
        completed_count: 11,
        total_count: 11,
        percent_complete: 100,
        last_updated_at: "2026-04-18T18:10:20Z",
        stages: [],
      },
      audit: {
        rule_interpretation: {
          template: "generic_manual",
          claim_family: "generic_manual",
          action: "restart",
          yes_condition: "YES if the war in Iran automatically restart after the cease fire happens.",
          no_condition: "NO if the war in Iran automatically restart after the cease fire does not happen.",
          deadline_text: null,
          resolution_definition: "Will the war in Iran automatically restart after the cease fire?",
          clarity_score: 0.68,
          resolution_risk: 0.32,
        },
        source_lanes: {
          official: 0,
          news: 4,
          premium: 0,
          live_social: 0,
          manual_social: 0,
          manual_input: 1,
          total: 5,
          contributing_sources: 0,
        },
        social_modifier: null,
        probability: {
          numeric_estimate_available: false,
          numeric_estimate_reason: "there are fewer than two scored directional factors",
          prior_probability: null,
          prior_logit: null,
          non_social_evidence: 0,
          raw_social_evidence: 0,
          capped_social_evidence: 0,
          total_evidence: 0,
          p_hat: null,
        },
        uncertainty: {
          base_uncertainty: 0.2,
          total_uncertainty: 0.4,
          p_low: null,
          p_high: null,
          adjustments: [],
        },
        recommendation_math: {
          yes_exec_price: null,
          no_exec_price: null,
          friction_buffer: null,
          edge_yes: null,
          edge_no: null,
          chosen_label: "analysis_only",
          note: "No market was linked, so this run remains analysis-only.",
        },
        confidence: {
          final_label: "low",
          reason: "The run stayed qualitative-only with no scored directional factors.",
        },
        factor_contributions: [],
      },
      presentation: {
        headline: "Will the war in Iran automatically restart after the cease fire?",
        thesis: "Current read: insufficient basis with low confidence.",
        status_note: "Analysis complete. The research brief and audit are ready.",
        brief_sections: {
          what_it_means:
            "Will the war in Iran automatically restart after the cease fire? currently reads as insufficient basis.",
          why_yes: [],
          why_no: [],
          context: [],
          caveats: "This could still change if stronger direct evidence appears.",
        },
        artifact_statuses: [
          { key: "rule_parse", label: "Rules interpreted", status: "complete", note: "Rules parsed.", available: true },
        ],
      },
      display_summary:
        "Will the war in Iran automatically restart after the cease fire? currently reads as insufficient basis.",
      last_updated_at: "2026-04-18T18:10:20Z",
      social_intel_summary: null,
      sources: [],
      documents: [],
      passages: [],
      trusted_social_sources: [],
      fact_claims: [],
      factors: [],
      reviews: [],
    } as never);

    render(<AnalysisDetailClient analysisId="30" />);

    await waitFor(() => {
      expect(screen.getByText(/current read: insufficient basis with low confidence/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/no directional read yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no linked polymarket market was available, and the available evidence did not form a directional read yet/i)).toBeInTheDocument();
    expect(screen.getByText(/^Probability$/i)).toBeInTheDocument();
    expect(screen.getByText(/^No estimate$/i)).toBeInTheDocument();
    expect(screen.getByText(/qualitative read: insufficient basis\./i)).toBeInTheDocument();
    expect(screen.getByText(/why no estimate/i)).toBeInTheDocument();
    expect(screen.getByText(/there are fewer than two scored directional factors/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Analysis Only$/i)).not.toBeInTheDocument();
  });

  it("renders running-state placeholders inside the memo layout", async () => {
    vi.mocked(fetchAnalysis).mockResolvedValue({
      request: {
        id: 2,
        mode: "manual",
        input_type: "custom_claim",
        input_text: "Will SCOTUS strike down Trump's birthright citizenship EO?",
        market_id: null,
        template_requested: "legal_case",
        template_selected: "legal_case",
        status: "running",
        current_stage: "retrieval",
        error_message: null,
        started_at: "2026-04-06T12:00:00Z",
        completed_at: null,
        created_at: "2026-04-06T12:00:00Z",
        updated_at: "2026-04-06T12:00:20Z",
        latest_recommendation_label: null,
        latest_confidence_label: null,
        review_count: 0,
        progress_percent: 36,
        current_stage_label: "Retrieval",
        current_stage_note: "Searching official and news sources.",
        display_summary: "Analysis in progress. Searching official and news sources.",
        qualitative_label: null,
      },
      market: null,
      latest_rule_parse: {
        question_text: "Will SCOTUS strike down Trump's birthright citizenship EO?",
        event: "SCOTUS birthright citizenship case",
        entity_names: ["SCOTUS", "Trump"],
        action: "strike down",
        claim_family: "legal_case",
        yes_condition: "YES if SCOTUS strikes down the executive order.",
        no_condition: "NO if SCOTUS upholds or allows the executive order.",
        deadline_text: null,
        resolution_definition: "Resolves YES if the Court invalidates the EO on the merits.",
        directional_scoring_policy: {},
        official_resolution_source: null,
        official_domains: ["supremecourt.gov"],
        ambiguity_flags: [],
        clarity_score: 0.71,
        resolution_risk: 0.31,
        suitable_for_auto: false,
        template_detected: "legal_case",
      },
      latest_run: null,
      recommendation: null,
      progress: {
        current_stage: "retrieval",
        current_label: "Retrieval",
        current_note: "Searching official and news sources.",
        completed_count: 3,
        total_count: 11,
        percent_complete: 36,
        last_updated_at: "2026-04-06T12:00:20Z",
        stages: [],
      },
      audit: null,
      presentation: {
        headline: "Will SCOTUS strike down Trump's birthright citizenship EO?",
        thesis: "The memo is still assembling. Partial artifacts will unlock as each stage finishes.",
        status_note: "Searching official and news sources.",
        brief_sections: {
          what_it_means: "Analysis in progress. Searching official and news sources.",
          why_yes: [],
          why_no: [],
          context: [],
          caveats: "The read can still change as new official information arrives.",
        },
        artifact_statuses: [
          { key: "rule_parse", label: "Rules interpreted", status: "complete", note: "Rules parsed.", available: true },
          { key: "retrieval", label: "Sources grounded", status: "running", note: "Searching official and news sources.", available: false },
          { key: "social_intelligence", label: "Social intelligence", status: "pending", note: "Waiting.", available: false },
          { key: "factor_mapping", label: "Factors scored", status: "pending", note: "Waiting.", available: false },
          { key: "brief_generation", label: "Brief written", status: "pending", note: "Waiting.", available: false },
          { key: "audit", label: "Audit ready", status: "pending", note: "The audit inspector unlocks once scored factors are ready.", available: false },
        ],
      },
      display_summary: "Analysis in progress. Searching official and news sources.",
      last_updated_at: "2026-04-06T12:00:20Z",
      social_intel_summary: null,
      sources: [],
      documents: [],
      passages: [],
      trusted_social_sources: [],
      fact_claims: [],
      factors: [],
      reviews: [],
    } as never);

    render(<AnalysisDetailClient analysisId="2" />);

    await waitFor(() => {
      expect(screen.getByText(/the memo is still assembling/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/factors being scored/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/sources grounded/i)).not.toHaveLength(0);
    expect(screen.getByText(/analysis-only run/i)).toBeInTheDocument();
  });

  it("polls lightweight progress while active and refetches full detail when the run completes", async () => {
    vi.mocked(fetchAnalysis)
      .mockResolvedValueOnce({
        request: {
          id: 3,
          mode: "manual",
          input_type: "custom_claim",
          input_text: "Will an approval happen this week?",
          market_id: null,
          template_requested: "official_event",
          template_selected: "official_event",
          status: "running",
          current_stage: "retrieval",
          error_message: null,
          started_at: "2026-04-06T12:00:00Z",
          completed_at: null,
          created_at: "2026-04-06T12:00:00Z",
          updated_at: "2026-04-06T12:00:10Z",
          latest_recommendation_label: null,
          latest_confidence_label: null,
          review_count: 0,
          progress_percent: 36,
          current_stage_label: "Retrieval",
          current_stage_note: "Gathering sources.",
          display_summary: "Analysis in progress. Gathering sources.",
          qualitative_label: null,
        },
        market: null,
        latest_rule_parse: null,
        latest_run: null,
        recommendation: null,
        progress: {
          current_stage: "retrieval",
          current_label: "Retrieval",
          current_note: "Gathering sources.",
          completed_count: 3,
          total_count: 11,
          percent_complete: 36,
          last_updated_at: "2026-04-06T12:00:10Z",
          stages: [],
        },
        audit: null,
        presentation: {
          headline: "Will an approval happen this week?",
          thesis: "The memo is still assembling. Partial artifacts will unlock as each stage finishes.",
          status_note: "Gathering sources.",
          brief_sections: {
            what_it_means: "Analysis in progress. Gathering sources.",
            why_yes: [],
            why_no: [],
            context: [],
            caveats: "The read can still change as new information arrives.",
          },
          artifact_statuses: [],
        },
        display_summary: "Analysis in progress. Gathering sources.",
        last_updated_at: "2026-04-06T12:00:10Z",
        social_intel_summary: null,
        sources: [],
        documents: [],
        passages: [],
        trusted_social_sources: [],
        fact_claims: [],
        factors: [],
        reviews: [],
      } as never)
      .mockResolvedValueOnce({
        request: {
          id: 3,
          mode: "manual",
          input_type: "custom_claim",
          input_text: "Will an approval happen this week?",
          market_id: null,
          template_requested: "official_event",
          template_selected: "official_event",
          status: "complete",
          current_stage: "complete",
          error_message: null,
          started_at: "2026-04-06T12:00:00Z",
          completed_at: "2026-04-06T12:01:00Z",
          created_at: "2026-04-06T12:00:00Z",
          updated_at: "2026-04-06T12:01:00Z",
          latest_recommendation_label: "analysis_only",
          latest_confidence_label: "medium",
          review_count: 0,
          progress_percent: 100,
          current_stage_label: "Complete",
          current_stage_note: "Analysis complete.",
          display_summary: "The analysis finished.",
          qualitative_label: "leans_yes",
        },
        market: null,
        latest_rule_parse: null,
        latest_run: null,
        recommendation: null,
        progress: {
          current_stage: "complete",
          current_label: "Complete",
          current_note: "Analysis complete.",
          completed_count: 11,
          total_count: 11,
          percent_complete: 100,
          last_updated_at: "2026-04-06T12:01:00Z",
          stages: [],
        },
        audit: null,
        presentation: {
          headline: "Will an approval happen this week?",
          thesis: "The memo is ready.",
          status_note: "Analysis complete.",
          brief_sections: {
            what_it_means: "The analysis finished.",
            why_yes: [],
            why_no: [],
            context: [],
            caveats: "The read can still change as new information arrives.",
          },
          artifact_statuses: [
            { key: "brief_generation", label: "Brief written", status: "complete", note: "Ready.", available: true },
          ],
        },
        display_summary: "The analysis finished.",
        last_updated_at: "2026-04-06T12:01:00Z",
        social_intel_summary: null,
        sources: [],
        documents: [],
        passages: [],
        trusted_social_sources: [],
        fact_claims: [],
        factors: [],
        reviews: [],
      } as never);

    vi.mocked(fetchAnalysisProgress).mockResolvedValue({
      request: {
        id: 3,
        mode: "manual",
        input_type: "custom_claim",
        input_text: "Will an approval happen this week?",
        market_id: null,
        template_requested: "official_event",
        template_selected: "official_event",
        status: "complete",
        current_stage: "complete",
        error_message: null,
        started_at: "2026-04-06T12:00:00Z",
        completed_at: "2026-04-06T12:01:00Z",
        created_at: "2026-04-06T12:00:00Z",
        updated_at: "2026-04-06T12:01:00Z",
        latest_recommendation_label: "analysis_only",
        latest_confidence_label: "medium",
        review_count: 0,
        progress_percent: 100,
        current_stage_label: "Complete",
        current_stage_note: "Analysis complete.",
        display_summary: "The analysis finished.",
        qualitative_label: "leans_yes",
      },
      progress: {
        current_stage: "complete",
        current_label: "Complete",
        current_note: "Analysis complete.",
        completed_count: 11,
        total_count: 11,
        percent_complete: 100,
        last_updated_at: "2026-04-06T12:01:00Z",
        stages: [],
      },
      presentation: {
        artifact_statuses: [
          { key: "brief_generation", label: "Brief written", status: "complete", note: "Ready.", available: true },
        ],
      },
      last_updated_at: "2026-04-06T12:01:00Z",
    } as never);

    await act(async () => {
      render(<AnalysisDetailClient analysisId="3" />);
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText(/the memo is still assembling/i)).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 2100));
    });

    await waitFor(() => {
      expect(fetchAnalysisProgress).toHaveBeenCalledWith("3");
    });

    await waitFor(() => {
      expect(fetchAnalysis).toHaveBeenCalledTimes(2);
    });
  }, 10000);
});
