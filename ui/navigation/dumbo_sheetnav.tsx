import { Brain, EllipsisVertical, MessagesSquare, Settings, Settings2, SlidersHorizontal } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { useState } from "react";

interface ToolMenuProps {
  portfolio: string;
  org: string;
  tool?: string;
  section?: string;
  onNavigate: (path: string) => void;
}

export default function DumboSheetNav({
  portfolio,
  org,
  tool,
  section,
  onNavigate,
}: ToolMenuProps) {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="icon" variant="outline" className="sm:hidden">
          <EllipsisVertical className="h-5 w-5" />
          <span className="sr-only">Toggle Menu</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="sm:max-w-xs">
        <nav className="grid gap-6 text-lg font-medium">
          <button
            onClick={() => {
              setOpen(false);
              onNavigate("/home");
            }}
            className="group flex h-11 w-11 shrink-0 items-center justify-center gap-2 md:h-8 md:w-8 md:text-base"
          >
            <img
              src={`${import.meta.env.VITE_WL_LOGO}`}
              className="ml-auto h-12 w-12"
              alt="Logo"
            />
            <span className="sr-only">Logo</span>
          </button>

          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/chat`);
            }}
            className={
              section === "chat"
                ? "flex items-center gap-4 px-2.5 text-foreground"
                : "flex items-center gap-4 px-2.5 text-muted-foreground hover:text-foreground"
            }
          >
            <MessagesSquare color="#6366f1" className="h-5 w-5" />
            Chat
          </button>

          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/config`);
            }}
            className={
              section === "config"
                ? "flex items-center gap-4 px-2.5 text-foreground"
                : "flex items-center gap-4 px-2.5 text-muted-foreground hover:text-foreground"
            }
          >
            <Settings2 color="#20a4c5" className="h-5 w-5" />
            Config
          </button>

          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/setup`);
            }}
            className={
              section === "setup"
                ? "flex items-center gap-4 px-2.5 text-foreground"
                : "flex items-center gap-4 px-2.5 text-muted-foreground hover:text-foreground"
            }
          >
            <SlidersHorizontal color="#8b5cf6" className="h-5 w-5" />
            Setup
          </button>

          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/memory`);
            }}
            className={
              section === "memory"
                ? "flex items-center gap-4 px-2.5 text-foreground"
                : "flex items-center gap-4 px-2.5 text-muted-foreground hover:text-foreground"
            }
          >
            <Brain color="#f59e0b" className="h-5 w-5" />
            Memory
          </button>

          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/settings`);
            }}
            className="flex items-center gap-4 px-2.5 text-muted-foreground hover:text-foreground"
          >
            <Settings className="h-5 w-5" />
            Settings
          </button>
        </nav>
      </SheetContent>
    </Sheet>
  );
}
