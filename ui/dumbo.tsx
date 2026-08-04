import DumboChat from "@extensions/dumbo/ui/pages/dumbo_chat";
import DumboConfig from "@extensions/dumbo/ui/pages/dumbo_config";
import DumboMemory from "@extensions/dumbo/ui/pages/dumbo_memory";
import DumboSetup from "@extensions/dumbo/ui/pages/dumbo_setup";
import { useEffect } from "react";

interface Portfolio {
  name: string;
  portfolio_id: string;
  orgs: Record<string, Org>;
  tools: Record<string, Tool>;
}

interface Org {
  name: string;
  org_id: string;
  tools: string[];
}

interface Tool {
  name: string;
  handle: string;
}

export default function Dumbo({
  portfolio,
  org,
  tool,
  section,
  tree,
  onNavigate,
}: {
  portfolio: string;
  org: string;
  tool: string;
  section?: string;
  tree?: { portfolios: Record<string, Portfolio> };
  onNavigate?: (path: string) => void;
}) {
  useEffect(() => {
    if (!section && onNavigate) {
      onNavigate(`/${portfolio}/${org}/${tool}/chat`);
    }
  }, [section, portfolio, org, tool, onNavigate]);

  if (!section) {
    return null;
  }

  return (
    <div className="flex min-h-screen w-full flex-col bg-muted/40">
      <div className="flex flex-col sm:gap-2 sm:pl-2">
        {section === "chat" && (
          <DumboChat
            portfolio={portfolio}
            org={org}
            tool={tool}
            tree={tree}
            onNavigate={onNavigate ?? (() => {})}
          />
        )}
        {section === "config" && (
          <DumboConfig portfolio={portfolio} org={org} tool={tool} />
        )}
        {section === "setup" && (
          <DumboSetup portfolio={portfolio} org={org} tool={tool} />
        )}
        {section === "memory" && (
          <DumboMemory portfolio={portfolio} org={org} tool={tool} />
        )}
      </div>
    </div>
  );
}
