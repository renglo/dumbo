import { useMemo } from "react";
import { Download, MessagesSquare, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import DialogPost from "@/components/console/dialog-post";

interface TreeStructure {
  portfolios: {
    [key: string]: {
      name: string;
      portfolio_id: string;
      orgs: object;
      teams: object;
      tools: object;
    };
  };
  user_id: string;
}

interface OnboardingProps {
  tree: TreeStructure;
}

export default function DumboOnboarding({ tree }: OnboardingProps) {
  const installBlueprint = useMemo(() => {
    const portfolioDict: Record<string, string> = {};
    if (tree?.portfolios) {
      Object.entries(tree.portfolios).forEach(([portfolioId, portfolio]) => {
        portfolioDict[portfolioId] = portfolio.name;
      });
    }

    return {
      label: "Dumbo Onboardings",
      fields: [
        {
          name: "portfolio",
          label: "Portfolio",
          hint: "Portfolio this extension should belong to:",
          layer: "0",
          options: portfolioDict,
          widget: "select",
          required: true,
        },
      ],
    };
  }, [tree]);

  const portfolioField = installBlueprint.fields?.find((field) => field.name === "portfolio");
  const hasPortfolioOptions =
    !!portfolioField?.options && Object.keys(portfolioField.options).length > 0;

  const refreshAction = () => {};

  return (
    <Card className="group relative overflow-hidden border-border bg-card transition-all hover:border-accent/50 hover:shadow-lg hover:shadow-accent/5">
      <div className="absolute right-3 top-3">
        <Badge className="bg-accent text-accent-foreground">Verified</Badge>
      </div>
      <CardContent className="p-5">
        <div className="mb-4 flex items-start gap-4">
          <MessagesSquare size={68} className="text-indigo-500" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate font-semibold text-foreground">Dumbo</h3>
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              Flat LangGraph smart-model harness with tool allowlists, HITL approvals, and session memory.
            </p>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-1.5">
          <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
            langgraph
          </span>
          <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
            hitl
          </span>
          <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
            agents
          </span>
        </div>

        <div className="flex items-center justify-between border-t border-border pt-4">
          <div className="flex items-center gap-4">
            <div className="text-xs text-muted-foreground">by Renglo</div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Download className="h-3.5 w-3.5" />
              Included
            </div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Star className="h-3.5 w-3.5 fill-amber-500 text-amber-500" />
              Extension
            </div>
          </div>
          {hasPortfolioOptions ? (
            <DialogPost
              refreshUp={refreshAction}
              blueprint={installBlueprint}
              title="Activate your portfolio"
              instructions="Select the portfolio where Dumbo should be installed:"
              path={`${import.meta.env.VITE_API_URL}/_schd/run/dumbo/dumbo_onboardings`}
              method="POST"
              buttontext="Install"
            />
          ) : (
            <div className="text-xs font-medium text-red-500">Create a portfolio first</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
