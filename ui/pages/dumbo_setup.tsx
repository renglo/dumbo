import DumboRingExplorer, { type DumboRingTab } from "./dumbo_ring_explorer";

const SETUP_TABS: DumboRingTab[] = [
  {
    id: "profiles",
    ring: "dumbo_profiles",
    label: "Profiles",
    hint: "Agent identities, tool allowlists, supervisor/delegatable flags, and write-tool HITL lists.",
  },
  {
    id: "skills",
    ring: "dumbo_skills",
    label: "Skills",
    hint: "JIT playbooks injected when trigger keywords appear in the user message.",
  },
  {
    id: "gates",
    ring: "dumbo_gates",
    label: "Gates",
    hint: "Optional grounding and policy gates applied during the agent loop.",
  },
];

interface DumboSetupProps {
  portfolio: string;
  org: string;
  tool: string;
}

export default function DumboSetup({ portfolio, org, tool }: DumboSetupProps) {
  return (
    <DumboRingExplorer
      portfolio={portfolio}
      org={org}
      tool={tool}
      title="Agent setup"
      description="Configure how Dumbo behaves: profiles define who the agent is and which tools it may call; skills add contextual instructions; gates enforce policies."
      tabs={SETUP_TABS}
      defaultTab="profiles"
    />
  );
}
