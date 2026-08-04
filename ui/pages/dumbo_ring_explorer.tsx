import ToolDataCRUD from "@renglo/data/pages/tool_data_crud";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PORTFOLIO_SCOPE_ORG } from "@/lib/sort-entities";

export type DumboRingTab = {
  id: string;
  ring: string;
  label: string;
  readonly?: boolean;
  hint?: string;
};

interface DumboRingExplorerProps {
  portfolio: string;
  org: string;
  tool: string;
  title: string;
  description: string;
  tabs: DumboRingTab[];
  defaultTab?: string;
}

export default function DumboRingExplorer({
  portfolio,
  org,
  tool,
  title,
  description,
  tabs,
  defaultTab,
}: DumboRingExplorerProps) {
  const initial = defaultTab ?? tabs[0]?.id ?? "";

  return (
    <Card className="mx-auto w-full overflow-hidden sm:w-[95%] lg:w-11/12">
      <CardHeader className="space-y-1">
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
        <p className="text-xs text-muted-foreground">
          Org scope: <span className="font-mono">{org}</span>
          {org === PORTFOLIO_SCOPE_ORG
            ? " — portfolio-wide documents"
            : " — documents for this org"}
        </p>
      </CardHeader>
      <CardContent className="p-4 pt-0 sm:p-6 sm:pt-0">
        <Tabs defaultValue={initial} className="w-full">
          <TabsList className="mb-4 flex h-auto w-full flex-wrap justify-start gap-1">
            {tabs.map((tab) => (
              <TabsTrigger key={tab.id} value={tab.id} className="text-xs sm:text-sm">
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {tabs.map((tab) => (
            <TabsContent key={tab.id} value={tab.id} className="mt-0">
              {tab.hint ? (
                <p className="mb-3 text-sm text-muted-foreground">{tab.hint}</p>
              ) : null}
              <ToolDataCRUD
                readonly={tab.readonly ?? false}
                portfolio={portfolio}
                org={org}
                tool={tool}
                ring={tab.ring}
              />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}
