import DumboRingExplorer, { type DumboRingTab } from "./dumbo_ring_explorer";

const MEMORY_TABS: DumboRingTab[] = [
  {
    id: "summaries",
    ring: "dumbo_summaries",
    label: "Summaries",
    hint: "Episodic digests and session summaries accumulated over time.",
  },
  {
    id: "beliefs",
    ring: "dumbo_beliefs",
    label: "Beliefs",
    hint: "Long-term facts and preferences the agent retains across sessions.",
  },
  {
    id: "approvals",
    ring: "dumbo_approvals",
    label: "Approvals",
    readonly: true,
    hint: "HITL proposals and resolutions for write tools (created by the agent; view-only here).",
  },
];

interface DumboMemoryProps {
  portfolio: string;
  org: string;
  tool: string;
}

export default function DumboMemory({ portfolio, org, tool }: DumboMemoryProps) {
  return (
    <DumboRingExplorer
      portfolio={portfolio}
      org={org}
      tool={tool}
      title="Agent memory"
      description="Documents that grow as Dumbo runs: episodic summaries, long-term beliefs, and pending or resolved HITL approvals."
      tabs={MEMORY_TABS}
      defaultTab="summaries"
    />
  );
}
