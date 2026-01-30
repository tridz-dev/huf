"use client";

import { cn } from "@/lib/utils";
import { ResponsiveBar } from "@nivo/bar";
import { ResponsiveLine } from "@nivo/line";
import { ResponsivePie } from "@nivo/pie";
import { ResponsiveRadar } from "@nivo/radar";
import { ResponsiveHeatMap } from "@nivo/heatmap";
import { ResponsiveSankey } from "@nivo/sankey";
import { ResponsiveTreeMap } from "@nivo/treemap";
import { ResponsiveSunburst } from "@nivo/sunburst";
import { ResponsiveChord } from "@nivo/chord";
import { ResponsiveCalendar } from "@nivo/calendar";
import { Download, Table } from "lucide-react";
import { useRef, useState, useCallback } from "react";
import {
  Artifact,
  ArtifactHeader,
  ArtifactTitle,
  ArtifactActions,
  ArtifactAction,
  ArtifactContent,
} from "./artifact";

// Chart component registry
const CHART_COMPONENTS: Record<string, React.ComponentType<any>> = {
  bar: ResponsiveBar,
  line: ResponsiveLine,
  pie: ResponsivePie,
  radar: ResponsiveRadar,
  heatmap: ResponsiveHeatMap,
  sankey: ResponsiveSankey,
  treemap: ResponsiveTreeMap,
  sunburst: ResponsiveSunburst,
  chord: ResponsiveChord,
  calendar: ResponsiveCalendar,
};

export type ChartType = keyof typeof CHART_COMPONENTS;

// Default theme that matches shadcn/ui
const defaultTheme = {
  background: "transparent",
  text: {
    fontFamily: "inherit",
    fontSize: 11,
    fill: "hsl(var(--foreground))",
  },
  axis: {
    domain: {
      line: {
        stroke: "hsl(var(--border))",
        strokeWidth: 1,
      },
    },
    ticks: {
      line: {
        stroke: "hsl(var(--border))",
        strokeWidth: 1,
      },
      text: {
        fill: "hsl(var(--muted-foreground))",
      },
    },
    legend: {
      text: {
        fill: "hsl(var(--foreground))",
        fontSize: 12,
      },
    },
  },
  grid: {
    line: {
      stroke: "hsl(var(--border))",
      strokeOpacity: 0.5,
    },
  },
  tooltip: {
    container: {
      background: "hsl(var(--popover))",
      color: "hsl(var(--popover-foreground))",
      fontSize: 12,
      borderRadius: 6,
      boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
      padding: "8px 12px",
    },
  },
  legends: {
    text: {
      fill: "hsl(var(--muted-foreground))",
    },
  },
};

// Default margins
const defaultMargin = { top: 40, right: 80, bottom: 60, left: 60 };

export interface ChartConfig {
  type: string;
  title: string;
  data: any;
  config?: Record<string, any>;
}

export interface ChartArtifactProps {
  chart: ChartConfig;
  className?: string;
}

export function ChartArtifact({ chart, className }: ChartArtifactProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [showData, setShowData] = useState(false);

  const ChartComponent = CHART_COMPONENTS[chart.type];

  const handleExportPNG = useCallback(async () => {
    const svg = chartRef.current?.querySelector("svg");
    if (!svg) return;

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const svgData = new XMLSerializer().serializeToString(svg);
    const img = new Image();

    const svgBlob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);

    img.onload = () => {
      canvas.width = img.width * 2;
      canvas.height = img.height * 2;
      ctx?.scale(2, 2);
      ctx?.drawImage(img, 0, 0);

      const pngUrl = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = pngUrl;
      a.download = `${chart.title.toLowerCase().replace(/\s+/g, "-")}.png`;
      a.click();
      URL.revokeObjectURL(url);
    };

    img.src = url;
  }, [chart.title]);

  if (!ChartComponent) {
    return (
      <Artifact className={className}>
        <ArtifactHeader>
          <ArtifactTitle>Unsupported Chart Type</ArtifactTitle>
        </ArtifactHeader>
        <ArtifactContent>
          <p className="text-muted-foreground">
            Chart type "{chart.type}" is not supported.
          </p>
        </ArtifactContent>
      </Artifact>
    );
  }

  // Merge config with defaults
  const chartProps = {
    data: chart.data,
    margin: defaultMargin,
    theme: defaultTheme,
    animate: true,
    motionConfig: "gentle",
    ...chart.config,
  };

  return (
    <Artifact className={cn("min-h-[400px]", className)}>
      <ArtifactHeader>
        <div className="flex items-center gap-2">
          <ArtifactTitle>{chart.title}</ArtifactTitle>
          <span className="text-xs text-muted-foreground capitalize">({chart.type})</span>
        </div>
        <ArtifactActions>
          <ArtifactAction
            icon={Table}
            tooltip="View Data"
            onClick={() => setShowData(!showData)}
          />
          <ArtifactAction
            icon={Download}
            tooltip="Export PNG"
            onClick={handleExportPNG}
          />
        </ArtifactActions>
      </ArtifactHeader>
      <ArtifactContent className="p-0">
        {showData ? (
          <div className="p-4 overflow-auto max-h-[400px]">
            <pre className="text-xs font-mono bg-muted p-4 rounded-md overflow-auto">
              {JSON.stringify(chart.data, null, 2)}
            </pre>
          </div>
        ) : (
          <div ref={chartRef} className="h-[400px] w-full">
            <ChartComponent {...chartProps} />
          </div>
        )}
      </ArtifactContent>
    </Artifact>
  );
}

// Helper function to check if a tool result is a chart
export function isChartResult(result: any): result is ChartConfig {
  return (
    result &&
    typeof result === "object" &&
    result._render === "chart" &&
    typeof result.type === "string" &&
    result.data !== undefined
  );
}
