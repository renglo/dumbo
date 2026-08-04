import { Brain, MessagesSquare, Settings2, SlidersHorizontal } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface ToolMenuProps {
  portfolio: string;
  org: string;
  tool?: string;
  section?: string;
  onNavigate: (path: string) => void;
}

export default function DumboSideNav({
  portfolio,
  org,
  tool,
  section,
  onNavigate,
}: ToolMenuProps) {
  const base = `/${portfolio}/${org}/${tool}`;
  const activeClass =
    "group flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-full bg-gray-200 text-lg font-semibold text-muted-foreground md:h-12 md:w-12 md:text-base";
  const idleClass =
    "flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:text-foreground md:h-8 md:w-8";

  return (
    <nav
      className={
        !org || org === "settings"
          ? "hidden"
          : "flex flex-col items-center gap-1 px-1 sm:py-4"
      }
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex flex-col items-center">
              <button
                type="button"
                onClick={() => onNavigate(`${base}/chat`)}
                className={section === "chat" ? activeClass : idleClass}
              >
                <MessagesSquare className="h-5 w-5" color="#6366f1" />
                <span className="sr-only">Chat</span>
              </button>
              <span className="text-xxs">Chat</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="right">Dumbo agent chat</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex flex-col items-center">
              <button
                type="button"
                onClick={() => onNavigate(`${base}/config`)}
                className={section === "config" ? activeClass : idleClass}
              >
                <Settings2 className="h-5 w-5" color="#20a4c5" />
                <span className="sr-only">Config</span>
              </button>
              <span className="text-xxs">Config</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="right">Extension configuration</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex flex-col items-center">
              <button
                type="button"
                onClick={() => onNavigate(`${base}/setup`)}
                className={section === "setup" ? activeClass : idleClass}
              >
                <SlidersHorizontal className="h-5 w-5" color="#8b5cf6" />
                <span className="sr-only">Setup</span>
              </button>
              <span className="text-xxs">Setup</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="right">Profiles, skills, and gates</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex flex-col items-center">
              <button
                type="button"
                onClick={() => onNavigate(`${base}/memory`)}
                className={section === "memory" ? activeClass : idleClass}
              >
                <Brain className="h-5 w-5" color="#f59e0b" />
                <span className="sr-only">Memory</span>
              </button>
              <span className="text-xxs">Memory</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="right">Summaries, beliefs, and approvals</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </nav>
  );
}
