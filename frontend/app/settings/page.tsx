import { ProviderStatusPanel } from "@/components/analysis/provider-status-panel";
import { Panel } from "@/components/ui/panel";

export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <section className="max-w-5xl space-y-4">
        <p className="text-[10px] uppercase tracking-[0.28em] text-ember/76">Settings</p>
        <h2 className="max-w-4xl font-serif text-5xl leading-[0.98] text-ink md:text-6xl">
          Keep the desk ready without turning setup into another dashboard.
        </h2>
        <p className="max-w-3xl text-base leading-8 text-ink/68">
          OpenAI, Grok, and search are the core path. Premium access and FRED remain optional and
          should never block the rest of the workflow.
        </p>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <ProviderStatusPanel />
        <Panel className="p-6">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Optional setup</p>
            <h3 className="mt-2 font-serif text-2xl text-ink">Premium and macro extras</h3>
          </div>
          <div className="mt-5 space-y-4 text-sm leading-7 text-ink/64">
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
