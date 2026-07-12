import { ProviderStatusPanel } from "@/components/analysis/provider-status-panel";
import { ProviderBillingPanel } from "@/components/settings/provider-billing-panel";
import { Panel } from "@/components/ui/panel";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <section className="max-w-5xl space-y-4">
        <p className="eyebrow">Settings</p>
        <h1 className="page-title">
          Keep the desk ready without turning setup into another dashboard.
        </h1>
        <p className="page-intro">
          OpenAI, Grok, and search are the core path. Premium access and FRED remain optional and
          should never block the rest of the workflow.
        </p>
      </section>

      <ProviderBillingPanel />

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <ProviderStatusPanel />
        <Panel className="p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Optional setup</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">Premium and macro extras</h3>
          </div>
          <div className="mt-4 space-y-4 text-sm leading-7 text-ink/70">
            <p>
              Premium retrieval stays off by default. The desk should still work cleanly without a
              saved browser session.
            </p>
            <p>
              When you decide to enable premium fetches, the backend looks for a Playwright
              session-state file from the root env setup instead of asking the UI to handle login.
            </p>
            <p>
              FRED is optional as well. Add it when you want richer macro data, not because the
              rest of the app depends on it.
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
