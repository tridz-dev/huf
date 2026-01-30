# Better Charts Implementation Plan

## Current State

| Feature | Status |
|---------|--------|
| Mermaid charts | Infrastructure only (not rendering) |
| Recharts | UI components built (`/frontend/src/components/ui/chart.tsx`) |
| ai-elements | Full suite including Artifact, Image, WebPreview |
| Image generation | Working (via `generatedImage` field + socket events) |
| Web preview | Component built, not integrated in chat |
| Streamdown | Markdown renderer (no diagram support) |

## Goal

Add rich, interactive data visualization using **nivo** charts to the chat interface, supporting:
- Pie, Bar, Line, Area, Heatmap, Radar, Sankey, and more
- Both static (image) and interactive (React component) rendering
- AI-driven chart generation via tool calling

---

## Proposed Approaches

### Approach 1: Nivo HTTP API + Image Artifact (Fastest MVP)

**Overview:** Use nivo's server-side rendering HTTP API to generate chart images, display them as image artifacts in chat.

```
User Request → AI generates chart config → POST to nivo.rocks/api → PNG/SVG returned → Display as Image
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         Backend (Python)                        │
├─────────────────────────────────────────────────────────────────┤
│  1. New Tool: generate_chart                                    │
│     - Input: chart_type, data, config                           │
│     - Calls: https://nivo.rocks/api/charts/{type}               │
│     - Output: base64 image or URL                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (React)                           │
├─────────────────────────────────────────────────────────────────┤
│  2. Extend ChatWindow to handle kind="Chart"                    │
│     - Similar to current Image handling                         │
│     - Uses existing <Image> component for display               │
│     - Optional: Download as PNG/SVG                             │
└─────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Fastest to implement (2-3 days)
- No new frontend dependencies
- Uses existing Image artifact infrastructure
- Works with current socket event system
- Charts render identically every time

**Cons:**
- No interactivity (hover, click, zoom)
- Depends on external nivo.rocks API (rate limits, availability)
- Limited customization vs. React components

**Implementation Steps:**

1. **Backend Tool** (`huf/ai/sdk_tools.py`):
```python
@tool
def generate_chart(
    chart_type: str,  # pie, bar, line, area, heatmap, etc.
    data: list[dict],
    config: dict = None
) -> str:
    """Generate a chart image using nivo."""
    url = f"https://nivo.rocks/api/charts/{chart_type}"
    payload = {
        "width": config.get("width", 800),
        "height": config.get("height", 600),
        "data": data,
        **config
    }
    response = requests.post(url, json=payload)
    # Return base64 encoded image
    return base64.b64encode(response.content).decode()
```

2. **Register tool in agent** (`huf/ai/agent_manager.py`)

3. **Frontend handling** in `ChatWindow.tsx`:
```typescript
{message.kind === 'Chart' && (
  <Image
    src={message.generatedChart}
    alt="Generated chart"
    showDownloadButton={true}
  />
)}
```

**Effort:** ~2-3 days

---

### Approach 2: Self-Hosted Nivo API + Chart Artifact

**Overview:** Run nivo's server-side rendering locally (or on your server) for better reliability and no rate limits.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    New Microservice (Node.js)                   │
├─────────────────────────────────────────────────────────────────┤
│  Nivo Chart Server                                              │
│  - Express/Fastify API                                          │
│  - Routes: POST /charts/:type                                   │
│  - Uses: @nivo/core, @nivo/pie, @nivo/bar, etc.                │
│  - Uses: @nivo/api (official server utilities)                  │
│  - Returns: SVG or PNG (via puppeteer/canvas)                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (Python/Frappe)                    │
├─────────────────────────────────────────────────────────────────┤
│  Tool: generate_chart → calls local chart server                │
└─────────────────────────────────────────────────────────────────┘
```

**Nivo Server Setup:**

```javascript
// chart-server/index.js
const express = require('express');
const { renderChart } = require('@nivo/api');
const { Pie } = require('@nivo/pie');
const { Bar } = require('@nivo/bar');

const app = express();
app.use(express.json());

const CHART_COMPONENTS = {
  pie: Pie,
  bar: Bar,
  line: Line,
  // ... more
};

app.post('/charts/:type', async (req, res) => {
  const { type } = req.params;
  const Component = CHART_COMPONENTS[type];

  const svg = await renderChart({
    component: Component,
    props: req.body,
  });

  res.type('image/svg+xml').send(svg);
});

app.listen(3001);
```

**Pros:**
- Full control over rendering
- No external API dependencies
- No rate limits
- Can cache rendered charts
- Supports all nivo customization options

**Cons:**
- Requires additional service deployment
- More infrastructure to maintain
- Still no interactivity

**Effort:** ~4-5 days

---

### Approach 3: Interactive React Charts via Artifact (Best UX)

**Overview:** Render nivo React components directly in the frontend within an Artifact container, enabling full interactivity.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (Python)                           │
├─────────────────────────────────────────────────────────────────┤
│  Tool: generate_chart                                           │
│  - Returns JSON config (not image)                              │
│  - Stored in message.chart_config                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (React)                           │
├─────────────────────────────────────────────────────────────────┤
│  New Component: ChartArtifact                                   │
│  - Receives chart_config from message                           │
│  - Dynamically renders nivo component                           │
│  - Full interactivity (hover, tooltips, legends)                │
│  - Export buttons (PNG, SVG, CSV data)                          │
└─────────────────────────────────────────────────────────────────┘
```

**New Components:**

```typescript
// frontend/src/components/ai-elements/chart-artifact.tsx

import { ResponsivePie } from '@nivo/pie';
import { ResponsiveBar } from '@nivo/bar';
import { ResponsiveLine } from '@nivo/line';
// ... more imports

const CHART_COMPONENTS = {
  pie: ResponsivePie,
  bar: ResponsiveBar,
  line: ResponsiveLine,
  area: ResponsiveAreaBump,
  heatmap: ResponsiveHeatMap,
  radar: ResponsiveRadar,
  sankey: ResponsiveSankey,
  treemap: ResponsiveTreeMap,
};

interface ChartArtifactProps {
  type: keyof typeof CHART_COMPONENTS;
  data: any[];
  config?: Record<string, any>;
}

export function ChartArtifact({ type, data, config }: ChartArtifactProps) {
  const ChartComponent = CHART_COMPONENTS[type];

  return (
    <Artifact>
      <ArtifactHeader>
        <ArtifactTitle>{type.charAt(0).toUpperCase() + type.slice(1)} Chart</ArtifactTitle>
        <ArtifactActions>
          <ArtifactAction
            icon={Download}
            tooltip="Export PNG"
            onClick={handleExportPng}
          />
          <ArtifactAction
            icon={Code}
            tooltip="View Data"
            onClick={handleViewData}
          />
        </ArtifactActions>
      </ArtifactHeader>
      <ArtifactContent className="h-[400px]">
        <ChartComponent
          data={data}
          {...config}
          // Common defaults
          margin={{ top: 40, right: 80, bottom: 80, left: 80 }}
          animate={true}
          motionConfig="gentle"
        />
      </ArtifactContent>
    </Artifact>
  );
}
```

**Integration in ChatWindow.tsx:**

```typescript
{message.kind === 'Chart' && message.chartConfig && (
  <ChartArtifact
    type={message.chartConfig.type}
    data={message.chartConfig.data}
    config={message.chartConfig.config}
  />
)}
```

**Backend Tool:**

```python
@tool
def generate_chart(
    chart_type: Literal["pie", "bar", "line", "area", "heatmap", "radar", "sankey", "treemap"],
    data: list[dict],
    title: str = None,
    config: dict = None
) -> dict:
    """
    Generate an interactive chart.

    Args:
        chart_type: Type of chart (pie, bar, line, area, heatmap, radar, sankey, treemap)
        data: Chart data in nivo format
        title: Optional chart title
        config: Optional chart configuration (colors, margins, legends, etc.)

    Returns:
        Chart configuration to be rendered by the frontend
    """
    return {
        "type": chart_type,
        "data": data,
        "title": title,
        "config": config or {}
    }
```

**Pros:**
- Full interactivity (hover, tooltips, click events)
- Smooth animations via react-spring
- Responsive sizing
- Supports all nivo features (patterns, gradients, theming)
- No external API calls
- Export to multiple formats

**Cons:**
- Larger frontend bundle (nivo packages)
- More complex implementation
- Need to handle chart config validation

**Package Additions:**
```bash
npm install @nivo/core @nivo/pie @nivo/bar @nivo/line @nivo/heatmap @nivo/radar @nivo/sankey @nivo/treemap
```

**Effort:** ~5-7 days

---

### Approach 4: Hybrid - Interactive + Static Fallback (Recommended)

**Overview:** Combine Approaches 2 and 3. Render interactive charts by default, with static image fallback for export/sharing.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                      Message with Chart                         │
├─────────────────────────────────────────────────────────────────┤
│  message.chartConfig = {                                        │
│    type: "pie",                                                 │
│    data: [...],                                                 │
│    config: {...},                                               │
│    staticImage?: "base64..." // Optional pre-rendered           │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
        ┌───────────────────┐   ┌───────────────────┐
        │ Interactive Mode  │   │   Static Mode     │
        │ (Default)         │   │   (Export/Share)  │
        ├───────────────────┤   ├───────────────────┤
        │ <ChartArtifact>   │   │ <Image>           │
        │ with nivo React   │   │ from staticImage  │
        └───────────────────┘   └───────────────────┘
```

**Features:**

1. **Interactive by default** - Full nivo React rendering
2. **Static on demand** - Generate image for:
   - Export/download
   - Share via link
   - Email embedding
   - Low-bandwidth mode
3. **Lazy generation** - Static image only created when needed

**Implementation:**

```typescript
// ChartArtifact with dual mode
export function ChartArtifact({ type, data, config, staticImage }: ChartArtifactProps) {
  const [mode, setMode] = useState<'interactive' | 'static'>('interactive');
  const chartRef = useRef<HTMLDivElement>(null);

  const handleExport = async () => {
    if (staticImage) {
      downloadImage(staticImage);
    } else {
      // Client-side export using html2canvas or svg serialization
      const svg = chartRef.current?.querySelector('svg');
      if (svg) {
        const svgData = new XMLSerializer().serializeToString(svg);
        downloadSvg(svgData);
      }
    }
  };

  return (
    <Artifact>
      <ArtifactHeader>
        <ArtifactTitle>{title}</ArtifactTitle>
        <ArtifactActions>
          <ArtifactAction
            icon={mode === 'interactive' ? Image : Activity}
            tooltip={mode === 'interactive' ? 'Static View' : 'Interactive View'}
            onClick={() => setMode(m => m === 'interactive' ? 'static' : 'interactive')}
          />
          <ArtifactAction icon={Download} tooltip="Export" onClick={handleExport} />
        </ArtifactActions>
      </ArtifactHeader>
      <ArtifactContent className="h-[400px]" ref={chartRef}>
        {mode === 'interactive' ? (
          <ChartComponent data={data} {...config} />
        ) : (
          <Image src={staticImage} alt="Chart" />
        )}
      </ArtifactContent>
    </Artifact>
  );
}
```

**Effort:** ~7-10 days

---

### Approach 5: WebPreview + Sandboxed Chart Editor (Most Flexible)

**Overview:** Use the existing WebPreview component to render a sandboxed chart editor/viewer with full nivo capabilities.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                       Chart Viewer App                          │
│              (Separate static site or iframe src)               │
├─────────────────────────────────────────────────────────────────┤
│  - Receives chart config via postMessage or URL params         │
│  - Full nivo installation                                       │
│  - Interactive editing capabilities                             │
│  - Export functionality built-in                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                    Embedded in WebPreview
                                │
┌─────────────────────────────────────────────────────────────────┐
│                      ChatWindow                                  │
├─────────────────────────────────────────────────────────────────┤
│  <WebPreview                                                    │
│    defaultUrl={`/chart-viewer?config=${encodedConfig}`}         │
│  />                                                             │
└─────────────────────────────────────────────────────────────────┘
```

**Chart Viewer App:**

```typescript
// chart-viewer/src/App.tsx (separate build target or static site)
function ChartViewer() {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    // Receive config via URL or postMessage
    const params = new URLSearchParams(window.location.search);
    const configStr = params.get('config');
    if (configStr) {
      setConfig(JSON.parse(decodeURIComponent(configStr)));
    }

    window.addEventListener('message', (e) => {
      if (e.data.type === 'CHART_CONFIG') {
        setConfig(e.data.config);
      }
    });
  }, []);

  if (!config) return <Loading />;

  const ChartComponent = CHART_COMPONENTS[config.type];

  return (
    <div className="w-full h-screen">
      <ChartComponent data={config.data} {...config.config} />
    </div>
  );
}
```

**Pros:**
- Complete isolation (security)
- Full nivo capabilities
- Can include chart editor UI
- WebPreview already built
- Could reuse nivo.rocks storybook or similar

**Cons:**
- Requires separate app deployment
- More complex message passing
- Potential iframe limitations

**Effort:** ~5-7 days

---

## Comparison Matrix

| Approach | Interactivity | Dependencies | Complexity | Time | Reliability |
|----------|--------------|--------------|------------|------|-------------|
| 1. HTTP API | None | Minimal | Low | 2-3d | External API |
| 2. Self-hosted API | None | Node service | Medium | 4-5d | Self-managed |
| 3. React Charts | Full | @nivo packages | Medium | 5-7d | Client-only |
| 4. Hybrid | Full + Export | @nivo + server | High | 7-10d | Best |
| 5. WebPreview | Full + Isolated | Separate app | Medium | 5-7d | Isolated |

---

## Recommended Implementation Path

### Phase 1: Quick Win (Week 1)
**Implement Approach 1** - HTTP API integration
- Add `generate_chart` tool
- Use existing Image artifact
- Validate concept with users
- Support: pie, bar, line charts

### Phase 2: Interactive Upgrade (Week 2-3)
**Implement Approach 3** - Interactive React charts
- Install nivo packages
- Create ChartArtifact component
- Add client-side export
- Support all chart types

### Phase 3: Polish (Week 4)
**Add Hybrid Features** from Approach 4
- Static image fallback for sharing
- Chart data table view
- Copy chart config
- Theme customization

---

## Detailed Implementation Checklist

### Backend Changes

- [ ] Create `generate_chart` tool in `huf/ai/sdk_tools.py`
- [ ] Define chart type enum and data schemas
- [ ] Add chart config to message metadata
- [ ] Register tool with agent

### Frontend Changes

- [ ] Install nivo packages
  ```bash
  npm install @nivo/core @nivo/pie @nivo/bar @nivo/line @nivo/heatmap @nivo/radar
  ```
- [ ] Create `ChartArtifact` component
- [ ] Create individual chart wrapper components
- [ ] Add chart rendering to `ChatWindow.tsx`
- [ ] Implement export functionality
- [ ] Add chart theming (match app theme)

### Testing

- [ ] Unit tests for chart tool
- [ ] Visual regression tests for charts
- [ ] Test all chart types with sample data
- [ ] Test export functionality

---

## Sample Tool Definitions

### Simple Tool (MVP)

```python
from agents import tool
from typing import Literal

@tool
def generate_chart(
    chart_type: Literal["pie", "bar", "line"],
    title: str,
    data: list[dict],
    x_axis: str = None,  # For bar/line charts
    y_axis: str = None,  # For bar/line charts
) -> dict:
    """
    Generate a data visualization chart.

    Use this tool when the user wants to visualize data.

    Args:
        chart_type: The type of chart to generate
        title: A descriptive title for the chart
        data: The data to visualize. Format depends on chart type:
            - pie: [{"id": "label", "value": 100}, ...]
            - bar: [{"category": "A", "value": 100}, ...]
            - line: [{"id": "series1", "data": [{"x": 0, "y": 10}, ...]}, ...]
        x_axis: Label for X axis (bar/line only)
        y_axis: Label for Y axis (bar/line only)

    Returns:
        Chart configuration for frontend rendering
    """
    config = {
        "margin": {"top": 50, "right": 130, "bottom": 50, "left": 60},
        "animate": True,
    }

    if chart_type == "pie":
        config.update({
            "innerRadius": 0.5,
            "padAngle": 0.7,
            "cornerRadius": 3,
            "activeOuterRadiusOffset": 8,
            "arcLinkLabelsSkipAngle": 10,
            "arcLabelsSkipAngle": 10,
        })
    elif chart_type == "bar":
        config.update({
            "keys": ["value"],
            "indexBy": "category",
            "padding": 0.3,
            "axisBottom": {"legend": x_axis} if x_axis else None,
            "axisLeft": {"legend": y_axis} if y_axis else None,
        })
    elif chart_type == "line":
        config.update({
            "xScale": {"type": "point"},
            "yScale": {"type": "linear", "min": "auto", "max": "auto"},
            "pointSize": 10,
            "pointBorderWidth": 2,
            "useMesh": True,
        })

    return {
        "type": chart_type,
        "title": title,
        "data": data,
        "config": config
    }
```

### Advanced Tool (Full Featured)

```python
@tool
def generate_advanced_chart(
    chart_type: Literal["pie", "bar", "line", "area", "heatmap", "radar", "sankey", "treemap"],
    title: str,
    data: list[dict],
    config: dict = None,
    theme: Literal["default", "dark", "nivo", "category10"] = "default",
    legend_position: Literal["top", "right", "bottom", "left", "none"] = "right",
    enable_labels: bool = True,
    enable_grid: bool = True,
) -> dict:
    """
    Generate an advanced data visualization chart with full customization.

    Args:
        chart_type: Type of chart
        title: Chart title
        data: Chart data (format varies by chart type)
        config: Advanced nivo configuration (overrides defaults)
        theme: Color theme
        legend_position: Position of legend
        enable_labels: Show data labels
        enable_grid: Show grid lines (applicable charts)

    Returns:
        Full chart configuration
    """
    # Implementation...
```

---

## Frontend Component Structure

```
frontend/src/components/
├── ai-elements/
│   ├── chart-artifact.tsx       # Main chart artifact component
│   └── charts/
│       ├── index.ts             # Chart component registry
│       ├── pie-chart.tsx        # Pie chart wrapper
│       ├── bar-chart.tsx        # Bar chart wrapper
│       ├── line-chart.tsx       # Line chart wrapper
│       ├── heatmap-chart.tsx    # Heatmap wrapper
│       ├── radar-chart.tsx      # Radar chart wrapper
│       └── chart-export.tsx     # Export utilities
```

---

## Open Questions

1. **Bundle size**: Nivo adds ~200-400KB gzipped. Is this acceptable?
   - Alternative: Dynamic imports for each chart type

2. **Data limits**: How much data should a single chart support?
   - Recommendation: Warn at 1000 points, limit at 10000

3. **Chart storage**: Should chart configs be stored in DB for regeneration?
   - Recommendation: Store in message metadata like images

4. **Real-time updates**: Should charts support live data updates?
   - Could integrate with socket events for dashboard use cases

5. **Accessibility**: Ensure charts are screen-reader friendly
   - Nivo supports aria labels and keyboard navigation

---

## References

- [Nivo Documentation](https://nivo.rocks/)
- [Nivo GitHub](https://github.com/plouc/nivo)
- [Nivo Storybook](https://nivo.rocks/storybook/)
- [Nivo API Reference](https://nivo.rocks/pie/api/)
- [Vercel ai-elements](https://github.com/vercel/ai-elements)
