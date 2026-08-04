import { CircleHelp } from "lucide-react";
import { useEffect, useState } from "react";

import DialogPutWide from "@/components/console/dialog-put-wide";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatBlueprintFieldValue } from "@/lib/blueprint-field-display";
import { PORTFOLIO_SCOPE_ORG } from "@/lib/sort-entities";

const SINGLETON_ID = "00000000-0000-0000-0000-000000000000";
const CONFIG_NAME = "dumbo_config";

interface BlueprintField {
  name: string;
  label?: string;
  hint?: string;
  widget?: string;
  order?: number | string;
}

interface Blueprint {
  label?: string;
  fields?: BlueprintField[];
  rich?: Record<string, Record<string, string>>;
  sources?: Record<string, string>;
}

interface FieldDictionary {
  [key: string]: BlueprintField;
}

interface ConfigData {
  _modified?: string;
  [key: string]: unknown;
}

interface DumboConfigProps {
  portfolio: string;
  org: string;
  tool: string;
}

export default function DumboConfig({ portfolio, org }: DumboConfigProps) {
  const [data, setData] = useState<ConfigData>({});
  const [blueprint, setBlueprint] = useState<Blueprint>({});
  const [fieldsDictionary, setFieldsDictionary] = useState<FieldDictionary>({});
  const [refresh, setRefresh] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiBase = import.meta.env.VITE_API_URL;
  const authHeaders = {
    Authorization: `Bearer ${sessionStorage.accessToken}`,
  };
  const configPath = `${apiBase}/_data/${portfolio}/${org}/${CONFIG_NAME}/${SINGLETON_ID}`;

  useEffect(() => {
    const fetchBlueprint = async () => {
      try {
        const res = await fetch(`${apiBase}/_blueprint/irma/${CONFIG_NAME}`, {
          method: "GET",
          headers: authHeaders,
        });
        if (!res.ok) {
          setError("Could not load dumbo_config blueprint");
          return;
        }
        setBlueprint(await res.json());
      } catch {
        setError("Could not load dumbo_config blueprint");
      }
    };

    void fetchBlueprint();
  }, [apiBase]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(configPath, {
          method: "GET",
          headers: authHeaders,
        });
        if (!res.ok) {
          setError("Could not load dumbo_config — run Install first");
          setData({});
          return;
        }
        setData(await res.json());
        setError(null);
      } catch {
        setError("Could not load dumbo_config");
      }
    };

    void fetchData();
  }, [configPath, refresh, org]);

  useEffect(() => {
    const dictionary: FieldDictionary = {};
    blueprint.fields?.forEach((field) => {
      dictionary[field.name] = field;
    });
    setFieldsDictionary(dictionary);
  }, [blueprint]);

  const refreshAction = () => {
    setRefresh((prev) => !prev);
  };

  return (
    <Card className="mx-auto w-full overflow-hidden sm:w-3/4">
      <CardHeader>
        <CardTitle>Configuration</CardTitle>
        <p className="text-xs text-muted-foreground">
          Org scope: <span className="font-mono">{org}</span>
          {org === PORTFOLIO_SCOPE_ORG
            ? " — portfolio-wide defaults shared across orgs"
            : " — settings for this org only"}
        </p>
      </CardHeader>

      <CardContent className="flex max-h-[70vh] flex-col gap-12 overflow-y-auto p-6 text-sm">
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : null}

        <div className="grid gap-3">
          {Object.entries(data)
            .sort(([keyA], [keyB]) => {
              const orderA = Number(fieldsDictionary[keyA]?.order ?? Number.MAX_SAFE_INTEGER);
              const orderB = Number(fieldsDictionary[keyB]?.order ?? Number.MAX_SAFE_INTEGER);
              return orderA - orderB;
            })
            .map(([key, value]) =>
              fieldsDictionary[key]?.widget !== "image" && !key.startsWith("_") ? (
                <Card key={key}>
                  <CardHeader>
                    <div className="text-muted-foreground">
                      {fieldsDictionary[key]?.label ?? key}
                    </div>
                  </CardHeader>
                  <CardContent className="group flex items-center justify-between">
                    <span className="flex items-center gap-1">
                      <DialogPutWide
                        selectedKey={key}
                        selectedValue={value}
                        refreshUp={refreshAction}
                        blueprint={blueprint}
                        title="Edit attribute"
                        instructions={fieldsDictionary[key]?.hint ?? ""}
                        path={configPath}
                        method="PUT"
                      />
                      <span className="whitespace-pre-wrap">
                        {formatBlueprintFieldValue(value, key, blueprint)}
                      </span>
                    </span>
                  </CardContent>
                  {fieldsDictionary[key]?.hint ? (
                    <CardFooter>
                      <span className="flex flex-row items-center gap-5">
                        <CircleHelp className="h-3 w-3" />
                        <div className="text-xs">{fieldsDictionary[key]?.hint}</div>
                      </span>
                    </CardFooter>
                  ) : null}
                </Card>
              ) : null,
            )}
        </div>
      </CardContent>

      <CardFooter className="flex flex-row items-center border-t bg-muted/50 px-6 py-3">
        <div className="text-xs text-muted-foreground">
          Last updated{" "}
          {data._modified ? (
            <time dateTime={String(data._modified)}>{String(data._modified)}</time>
          ) : (
            "—"
          )}
        </div>
      </CardFooter>
    </Card>
  );
}
