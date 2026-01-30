# Better Charts Implementation Plan

> Based on analysis of [nivo](https://github.com/plouc/nivo) and [ai-elements](https://github.com/vercel/ai-elements) source code.

## Current State

| Feature | Status | Location |
|---------|--------|----------|
| Recharts | UI components built (unused) | `frontend/src/components/ui/chart.tsx` |
| ai-elements | Full suite (29 components) | `frontend/src/components/ai-elements/` |
| Artifact component | Ready | `ai-elements/artifact.tsx` |
| Tool component | Ready | `ai-elements/tool.tsx` |
| Image component | Working | `ai-elements/image.tsx` |
| Web Preview | Built, not integrated | `ai-elements/web-preview.tsx` |

## Goal

Integrate **nivo** charts into HUF chat using the existing ai-elements patterns, supporting:
- 12+ chart types: bar, line, pie, radar, heatmap, sankey, treemap, etc.
- Both static (SVG) and interactive (React) rendering
- AI-driven chart generation via tool calling
- Export functionality (PNG, SVG, data)

---

## Nivo Architecture (from source analysis)

### Package Structure
```
@nivo/core          - Core utilities, ResponsiveWrapper, hooks
@nivo/theming       - Theme system and defaults
@nivo/colors        - Color schemes (nivo, paired, category10, etc.)
@nivo/static        - Server-side rendering with Joi validation
@nivo/express       - Express.js HTTP API router

Chart packages:
@nivo/bar           - Bar charts (grouped/stacked, horizontal/vertical)
@nivo/line          - Line charts
@nivo/pie           - Pie and donut charts
@nivo/radar         - Radar/spider charts
@nivo/heatmap       - Heatmaps
@nivo/sankey        - Sankey diagrams
@nivo/treemap       - Treemaps
@nivo/sunburst      - Sunburst charts
@nivo/chord         - Chord diagrams
@nivo/calendar      - Calendar heatmaps
@nivo/circle-packing - Circle packing
@nivo/icicle        - Icicle charts
```

### Key Files from Nivo
```
nivo/packages/static/src/renderer.ts      - renderChart() function for SSR
nivo/packages/static/src/mappings/        - Chart type definitions with Joi schemas
nivo/packages/express/src/index.ts        - Express router implementation
```

### renderChart Function (from `renderer.ts`)
```typescript
import { renderToStaticMarkup } from 'react-dom/server'

const staticProps = {
    animate: false,
    isInteractive: false,
    renderWrapper: false,
    theme: {},
}

export const renderChart = ({ type, props }, override) => {
    const chart = chartsMapping[type]
    const mergedProps = {
        ...staticProps,
        ...chart.defaults,
        ...props,
        ...pick(override, chart.runtimeProps || []),
    }
    const rendered = renderToStaticMarkup(createElement(chart.component, mergedProps))
    return `<?xml version="1.0" ?>${rendered}`
}
```

### Chart Mapping Pattern (from `mappings/bar.ts`)
```typescript
export const barMapping = {
    component: Bar,
    schema: Joi.object().keys({
        width: dimensions.width,
        height: dimensions.height,
        margin: dimensions.margin,
        data: custom.array().min(1).required(),
        indexBy: Joi.string().required(),
        keys: Joi.array().sparse(false).min(1).unique().required(),
        groupMode: Joi.any().valid('grouped', 'stacked'),
        layout: Joi.any().valid('horizontal', 'vertical'),
        colors: ordinalColors,
        // ... more
    }),
    runtimeProps: ['width', 'height', 'colors', 'groupMode'],
    defaults: {
        margin: { top: 40, right: 50, bottom: 40, left: 50 },
    },
}
```

### Supported Chart Types (from `mappings/index.ts`)
```typescript
export const chartsMapping = {
    bar: barMapping,
    circle_packing: circlePackingMapping,
    calendar: calendarMapping,
    chord: chordMapping,
    heatmap: heatmapMapping,
    icicle: icicleMapping,
    line: lineMapping,
    pie: pieMapping,
    radar: radarMapping,
    sankey: sankeyMapping,
    sunburst: sunburstMapping,
    treemap: treemapMapping,
}
```

---

## ai-elements Architecture (from source analysis)

### Artifact Pattern (from `artifact.tsx`)
```tsx
<Artifact>                          // flex flex-col overflow-hidden rounded-lg border
  <ArtifactHeader>                  // flex items-center justify-between border-b bg-muted/50
    <ArtifactTitle>Chart Title</ArtifactTitle>
    <ArtifactActions>
      <ArtifactAction icon={Download} tooltip="Export PNG" onClick={...} />
    </ArtifactActions>
    <ArtifactClose onClick={...} />
  </ArtifactHeader>
  <ArtifactContent>                 // flex-1 overflow-auto p-4
    {/* Chart content here */}
  </ArtifactContent>
</Artifact>
```

### Tool Pattern (from `tool.tsx`)
```tsx
<Tool>                              // Collapsible with border
  <ToolHeader
    title="generate-chart"
    type="dynamic-tool"
    state="output-available"        // input-streaming, output-available, output-error
    toolName="generate-chart"
  />
  <ToolContent>
    <ToolInput input={{ type: "bar", data: [...] }} />
    <ToolOutput output={<ChartComponent />} />  // Accepts ReactElement!
  </ToolContent>
</Tool>
```

**Key insight from `tool.tsx:148`:** ToolOutput can render React elements directly:
```typescript
if (typeof output === "object" && !isValidElement(output)) {
  Output = <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />
} else if (typeof output === "string") {
  Output = <CodeBlock code={output} language="json" />
}
// Otherwise renders: <div>{output as ReactNode}</div>
```

---

## Implementation Plans

### Plan A: Interactive React Charts via Tool Output (Recommended)

**Overview:** Use nivo React components directly in the frontend, rendered inside Tool or Artifact components.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                      Backend Tool                               │
├─────────────────────────────────────────────────────────────────┤
│  @tool generate_chart(type, data, config) -> dict              │
│  Returns JSON config that frontend interprets                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend                                   │
├─────────────────────────────────────────────────────────────────┤
│  ChatWindow detects tool result with chart config               │
│  Renders <ChartArtifact> with nivo React component              │
│  Full interactivity (hover, click, animations)                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Backend Implementation

**File: `huf/ai/tools/chart_tool.py`**
```python
from agents import tool
from typing import Literal

CHART_TYPES = Literal[
    "bar", "line", "pie", "radar", "heatmap",
    "sankey", "treemap", "sunburst", "chord", "calendar"
]

@tool
def generate_chart(
    chart_type: CHART_TYPES,
    title: str,
    data: list[dict],
    config: dict = None
) -> dict:
    """
    Generate a data visualization chart.

    Use this tool when the user wants to visualize data as a chart.

    Args:
        chart_type: Type of chart to generate
            - bar: Compare values across categories
            - line: Show trends over time
            - pie: Show proportions of a whole
            - radar: Compare multiple variables
            - heatmap: Show intensity across two dimensions
            - sankey: Show flow between nodes
            - treemap: Show hierarchical data as nested rectangles
            - sunburst: Show hierarchical data as concentric rings
            - chord: Show relationships between entities
            - calendar: Show values over calendar days
        title: Descriptive title for the chart
        data: Chart data. Format varies by chart type:
            - bar: [{"category": "A", "value1": 10, "value2": 20}, ...]
            - line: [{"id": "series1", "data": [{"x": "Jan", "y": 100}, ...]}, ...]
            - pie: [{"id": "slice1", "label": "Slice 1", "value": 30}, ...]
            - radar: [{"category": "A", "series1": 80, "series2": 60}, ...]
            - heatmap: [{"id": "row1", "data": [{"x": "col1", "y": 50}, ...]}, ...]
            - sankey: {"nodes": [...], "links": [...]}
            - treemap: {"name": "root", "children": [...]}
            - chord: [[n, n, ...], ...] (matrix format)
        config: Optional configuration overrides (colors, margins, legends, etc.)

    Returns:
        Chart configuration for frontend rendering
    """
    # Default configurations per chart type
    defaults = {
        "bar": {
            "keys": _extract_numeric_keys(data),
            "indexBy": _find_index_key(data),
            "groupMode": "grouped",
            "layout": "vertical",
            "colors": {"scheme": "nivo"},
            "enableLabel": True,
            "labelSkipWidth": 12,
            "labelSkipHeight": 12,
        },
        "line": {
            "xScale": {"type": "point"},
            "yScale": {"type": "linear", "min": "auto", "max": "auto"},
            "curve": "monotoneX",
            "pointSize": 10,
            "pointBorderWidth": 2,
            "useMesh": True,
            "enableSlices": "x",
        },
        "pie": {
            "innerRadius": 0.5,
            "padAngle": 0.7,
            "cornerRadius": 3,
            "activeOuterRadiusOffset": 8,
            "arcLinkLabelsSkipAngle": 10,
            "arcLabelsSkipAngle": 10,
            "colors": {"scheme": "nivo"},
        },
        "radar": {
            "indexBy": "category",
            "keys": _extract_numeric_keys(data),
            "maxValue": "auto",
            "curve": "linearClosed",
            "fillOpacity": 0.25,
            "dotSize": 8,
        },
        "heatmap": {
            "colors": {
                "type": "sequential",
                "scheme": "blues",
            },
            "emptyColor": "#555555",
        },
    }

    base_config = defaults.get(chart_type, {})
    merged_config = {**base_config, **(config or {})}

    return {
        "type": chart_type,
        "title": title,
        "data": data,
        "config": merged_config,
        "_render": "chart",  # Signal to frontend this is a chart
    }


def _extract_numeric_keys(data: list[dict]) -> list[str]:
    """Extract keys with numeric values from first data item."""
    if not data:
        return []
    first = data[0]
    return [k for k, v in first.items() if isinstance(v, (int, float))]


def _find_index_key(data: list[dict]) -> str:
    """Find the likely index/category key."""
    if not data:
        return "id"
    first = data[0]
    for key in ["id", "name", "category", "label", "index"]:
        if key in first:
            return key
    # Return first string key
    for k, v in first.items():
        if isinstance(v, str):
            return k
    return list(first.keys())[0]
```

#### Frontend Implementation

**File: `frontend/src/components/ai-elements/chart-artifact.tsx`**
```tsx
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
import { Download, Table, Maximize2 } from "lucide-react";
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
const CHART_COMPONENTS = {
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
} as const;

type ChartType = keyof typeof CHART_COMPONENTS;

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
  type: ChartType;
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

  const handleExportSVG = useCallback(() => {
    const svg = chartRef.current?.querySelector("svg");
    if (!svg) return;

    const svgData = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${chart.title.toLowerCase().replace(/\s+/g, "-")}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }, [chart.title]);

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
        <ArtifactTitle>{chart.title}</ArtifactTitle>
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
            <pre className="text-xs">
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
```

**Update `frontend/src/components/chat/ChatWindow.tsx`:**
```tsx
import { ChartArtifact } from "@/components/ai-elements/chart-artifact";

// In message rendering, detect chart tool output:
{tool.result?._render === "chart" && (
  <ChartArtifact chart={tool.result} />
)}
```

#### Package Dependencies

```bash
npm install @nivo/core @nivo/bar @nivo/line @nivo/pie @nivo/radar \
  @nivo/heatmap @nivo/sankey @nivo/treemap @nivo/sunburst @nivo/chord @nivo/calendar
```

**Bundle size consideration:** ~200-400KB gzipped for all packages. Can use dynamic imports:
```tsx
const ChartComponent = lazy(() =>
  import(`@nivo/${chart.type}`).then(m => ({ default: m[`Responsive${capitalize(chart.type)}`] }))
);
```

---

### Plan B: Server-Side Rendering with @nivo/static

**Overview:** Use nivo's `renderChart` function on the backend to generate static SVGs. No frontend nivo dependencies.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                   Python Backend + Node Worker                  │
├─────────────────────────────────────────────────────────────────┤
│  1. Python tool receives chart request                          │
│  2. Calls Node.js subprocess with @nivo/static                  │
│  3. Node renders SVG using renderChart()                        │
│  4. Returns SVG string or base64                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend                                   │
├─────────────────────────────────────────────────────────────────┤
│  Displays SVG in <Image> component (existing)                   │
│  No nivo packages needed on frontend                            │
└─────────────────────────────────────────────────────────────────┘
```

#### Node.js Chart Renderer

**File: `huf/chart-renderer/index.js`**
```javascript
#!/usr/bin/env node
const { renderChart } = require('@nivo/static');

// Read JSON config from stdin
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  try {
    const config = JSON.parse(input);
    const svg = renderChart({
      type: config.type,
      props: {
        width: config.width || 800,
        height: config.height || 500,
        data: config.data,
        ...config.props,
      }
    }, {});

    console.log(JSON.stringify({ svg }));
  } catch (error) {
    console.log(JSON.stringify({ error: error.message }));
    process.exit(1);
  }
});
```

**File: `huf/chart-renderer/package.json`**
```json
{
  "name": "huf-chart-renderer",
  "private": true,
  "dependencies": {
    "@nivo/static": "^0.87.0"
  }
}
```

#### Python Integration

**File: `huf/ai/tools/chart_tool.py`**
```python
import subprocess
import json
import base64
from agents import tool

@tool
def generate_chart(chart_type: str, title: str, data: list, config: dict = None) -> dict:
    """Generate a chart image using nivo."""

    chart_config = {
        "type": chart_type,
        "width": config.get("width", 800) if config else 800,
        "height": config.get("height", 500) if config else 500,
        "data": data,
        "props": config or {},
    }

    # Call Node.js renderer
    result = subprocess.run(
        ["node", "huf/chart-renderer/index.js"],
        input=json.dumps(chart_config),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return {"error": result.stderr}

    response = json.loads(result.stdout)
    if "error" in response:
        return {"error": response["error"]}

    # Return as base64 for Image component
    svg_bytes = response["svg"].encode('utf-8')
    return {
        "title": title,
        "image": f"data:image/svg+xml;base64,{base64.b64encode(svg_bytes).decode()}",
        "_render": "image",
    }
```

---

### Plan C: Nivo HTTP API Server (External Service)

**Overview:** Run nivo's Express server as a microservice, call it from Python.

**Based on:** `nivo/packages/express/src/index.ts`

#### Nivo Server Setup

**File: `huf/services/chart-api/app.js`**
```javascript
const express = require('express');
const { nivo } = require('@nivo/express');

const app = express();
app.use(express.json({ limit: '10mb' }));

// Mount nivo router at /nivo
app.use('/nivo', nivo);

// Health check
app.get('/health', (req, res) => res.json({ status: 'ok' }));

const PORT = process.env.CHART_API_PORT || 3030;
app.listen(PORT, () => {
  console.log(`Chart API running on port ${PORT}`);
});
```

#### Docker Setup

**File: `huf/services/chart-api/Dockerfile`**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
EXPOSE 3030
CMD ["node", "app.js"]
```

#### Python Client

```python
import requests
import frappe

CHART_API_URL = frappe.conf.get("chart_api_url", "http://localhost:3030")

@tool
def generate_chart(chart_type: str, title: str, data: list, config: dict = None) -> dict:
    """Generate chart via nivo HTTP API."""

    payload = {
        "width": config.get("width", 800) if config else 800,
        "height": config.get("height", 500) if config else 500,
        "data": data,
        **(config or {}),
    }

    # POST to nivo API - creates chart and returns ID + URL
    response = requests.post(
        f"{CHART_API_URL}/nivo/charts/{chart_type}",
        json=payload,
    )

    if response.status_code != 201:
        return {"error": response.text}

    result = response.json()

    # Fetch the rendered SVG
    svg_response = requests.get(result["url"])

    return {
        "title": title,
        "svg": svg_response.text,
        "_render": "svg",
    }
```

---

### Plan D: Hybrid - Interactive + Static Export

**Overview:** Combine Plan A (interactive) with Plan B (static export) for best of both worlds.

**Features:**
1. **Default:** Interactive React charts with full nivo features
2. **Export:** Generate static SVG/PNG via @nivo/static on demand
3. **Fallback:** Static rendering for email/sharing

#### Implementation

**Frontend ChartArtifact with export:**
```tsx
export function ChartArtifact({ chart }: ChartArtifactProps) {
  const handleExport = async (format: 'svg' | 'png') => {
    // Call backend to generate static version
    const response = await fetch('/api/chart/export', {
      method: 'POST',
      body: JSON.stringify({
        type: chart.type,
        data: chart.data,
        config: chart.config,
        format,
      }),
    });

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chart.${format}`;
    a.click();
  };

  return (
    <Artifact>
      {/* ... header with export buttons ... */}
      <ArtifactContent>
        <ResponsiveChart {...chartProps} />
      </ArtifactContent>
    </Artifact>
  );
}
```

---

## Comparison Matrix

| Aspect | Plan A (React) | Plan B (Static) | Plan C (HTTP API) | Plan D (Hybrid) |
|--------|---------------|-----------------|-------------------|-----------------|
| **Interactivity** | Full | None | None | Full |
| **Frontend deps** | @nivo/* | None | None | @nivo/* |
| **Backend deps** | None | Node subprocess | Node service | Both |
| **Bundle size** | +200-400KB | 0 | 0 | +200-400KB |
| **Animations** | Yes | No | No | Yes |
| **Export quality** | Client-side | High (server) | High (server) | Highest |
| **Complexity** | Low | Medium | High | Medium |
| **Infrastructure** | None | Node runtime | Docker service | Node runtime |
| **Time to implement** | 3-5 days | 4-6 days | 5-7 days | 6-8 days |

---

## Recommended Approach

### Phase 1: Plan A (Interactive React Charts) - 3-5 days

**Why:**
- Fastest to implement
- Best user experience (interactive)
- Uses existing ai-elements patterns (Artifact, Tool)
- No additional infrastructure
- nivo bundle size is acceptable for a chat app

**Implementation order:**
1. Install nivo packages
2. Create `ChartArtifact` component
3. Create `generate_chart` tool
4. Update ChatWindow to detect chart output
5. Add client-side export (PNG/SVG)

### Phase 2: Add Static Export (Plan D) - 2-3 days

**After Phase 1:**
1. Add Node.js chart renderer
2. Create `/api/chart/export` endpoint
3. Add high-quality export buttons

### Phase 3: Polish - 1-2 days

1. Theme integration with shadcn/ui
2. Responsive sizing
3. Error handling and fallbacks
4. Documentation

---

## Data Format Reference

### Bar Chart
```json
{
  "type": "bar",
  "data": [
    { "country": "USA", "sales": 100, "profit": 50 },
    { "country": "UK", "sales": 80, "profit": 30 }
  ],
  "config": {
    "keys": ["sales", "profit"],
    "indexBy": "country"
  }
}
```

### Line Chart
```json
{
  "type": "line",
  "data": [
    {
      "id": "Revenue",
      "data": [
        { "x": "Jan", "y": 100 },
        { "x": "Feb", "y": 150 }
      ]
    }
  ]
}
```

### Pie Chart
```json
{
  "type": "pie",
  "data": [
    { "id": "React", "label": "React", "value": 40 },
    { "id": "Vue", "label": "Vue", "value": 30 },
    { "id": "Angular", "label": "Angular", "value": 30 }
  ]
}
```

### Sankey
```json
{
  "type": "sankey",
  "data": {
    "nodes": [
      { "id": "Source A" },
      { "id": "Target B" }
    ],
    "links": [
      { "source": "Source A", "target": "Target B", "value": 100 }
    ]
  }
}
```

### Treemap
```json
{
  "type": "treemap",
  "data": {
    "name": "root",
    "children": [
      { "name": "Category A", "value": 100 },
      {
        "name": "Category B",
        "children": [
          { "name": "Sub B1", "value": 50 },
          { "name": "Sub B2", "value": 30 }
        ]
      }
    ]
  }
}
```

---

## Files to Create/Modify

### New Files
```
frontend/src/components/ai-elements/chart-artifact.tsx   # Chart component
huf/ai/tools/chart_tool.py                              # Backend tool
huf/chart-renderer/index.js                             # Optional: static renderer
huf/chart-renderer/package.json
```

### Modified Files
```
frontend/src/components/chat/ChatWindow.tsx             # Detect chart output
frontend/package.json                                   # Add @nivo/* deps
huf/ai/agent_manager.py                                 # Register tool
```

---

## References

- [Nivo Source - Static Renderer](/.research/nivo/packages/static/src/renderer.ts)
- [Nivo Source - Express Router](/.research/nivo/packages/express/src/index.ts)
- [Nivo Source - Chart Mappings](/.research/nivo/packages/static/src/mappings/)
- [ai-elements Source - Artifact](/.research/ai-elements/packages/elements/src/artifact.tsx)
- [ai-elements Source - Tool](/.research/ai-elements/packages/elements/src/tool.tsx)
- [Nivo Documentation](https://nivo.rocks/)
- [Nivo GitHub](https://github.com/plouc/nivo)
