# Testing Generative UI Components in Huf

> **Date**: 2026-03-19
> **Prerequisites**: A running Huf instance with at least one AI Agent configured
> **Scope**: Testing the `<ui-component>` structured tag system in chat

---

## Table of Contents

1. [How It Works](#1-how-it-works)
2. [Setup for Testing](#2-setup-for-testing)
3. [Test Examples — Step by Step](#3-test-examples--step-by-step)
   - [Example 1: Stats Card — Revenue KPI](#example-1-stats-card--revenue-kpi)
   - [Example 2: KPI Grid — Financial Dashboard](#example-2-kpi-grid--financial-dashboard)
   - [Example 3: Bar Chart — Sales by Region](#example-3-bar-chart--sales-by-region)
   - [Example 4: Line Chart — Monthly Revenue Trend](#example-4-line-chart--monthly-revenue-trend)
   - [Example 5: Pie Chart — Expense Breakdown](#example-5-pie-chart--expense-breakdown)
   - [Example 6: Area Chart — Cash Flow Over Time](#example-6-area-chart--cash-flow-over-time)
   - [Example 7: Data Table — Outstanding Invoices](#example-7-data-table--outstanding-invoices)
   - [Example 8: Progress Card — Quarterly Targets](#example-8-progress-card--quarterly-targets)
   - [Example 9: Info Card — Sales Order Summary](#example-9-info-card--sales-order-summary)
   - [Example 10: Multi-Component — Full Sales Report](#example-10-multi-component--full-sales-report)
4. [Agent Instruction Templates](#4-agent-instruction-templates)
5. [Quick-Test Without an AI Agent](#5-quick-test-without-an-ai-agent)
6. [Component Reference](#6-component-reference)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. How It Works

The system works by parsing special XML-style tags in AI agent responses:

```
<ui-component type="stats-card" data='{"title":"Revenue","value":48250,"format":"currency"}' />
```

**Flow:**

1. The AI agent includes `<ui-component>` tags in its text response
2. The chat message renderer (`MessageContentWithArtifacts`) detects these tags
3. The parser (`uiComponentParser.ts`) extracts the type and JSON data
4. The registry (`registry.ts`) maps the type to a React renderer
5. The renderer displays a polished, interactive component inline in the chat

**Key rules:**
- Tags are **self-closing** (`/>`)
- The `type` attribute selects the renderer
- The `data` attribute contains **single-quoted JSON** (so double quotes work inside)
- Surrounding text renders normally as markdown
- Unknown types show a graceful fallback with raw JSON
- Invalid JSON shows a clear error message

---

## 2. Setup for Testing

### Option A: Agent instructions (recommended)

The easiest way to test is to configure an AI agent with instructions that tell it to use `<ui-component>` tags. Add these instructions to your agent's system prompt:

```
When presenting numerical data, metrics, charts, or tabular information, use structured <ui-component> tags instead of plain text or markdown tables.

Available component types:
- stats-card: Single KPI metric. Data: {"title":"...", "value":number, "change":number, "changeLabel":"...", "format":"currency|number|percent|compact"}
- kpi-grid: Multiple KPIs. Data: {"title":"...", "items":[{"label":"...", "value":number, "change":number, "format":"..."}], "columns":number}
- bar-chart: Bar chart. Data: {"title":"...", "items":[{"name":"...", "value":number}], "dataKey":"value", "categoryKey":"name"}
- line-chart: Line chart. Data: {"title":"...", "items":[{"name":"...", "value":number}], "xKey":"name"}
- pie-chart: Pie chart. Data: {"title":"...", "items":[{"name":"...", "value":number}]}
- area-chart: Area chart. Data: {"title":"...", "items":[{"name":"...", "value":number}], "xKey":"name"}
- data-table: Data table. Data: {"title":"...", "columns":["Col1","Col2"], "rows":[["val1","val2"]]}
- progress-card: Progress bars. Data: {"title":"...", "value":75, "max":100, "label":"Completion"}
- info-card: Detail card. Data: {"title":"...", "status":"Active", "items":[{"label":"...", "value":"..."}]}

Rules:
- Use single quotes around the data attribute: data='...'
- Use double quotes inside JSON
- Tags are self-closing: />
- You can mix text and components in a single response
```

### Option B: Direct message testing

If you have access to the backend, you can simulate an agent response by directly creating an `Agent Message` document with content that includes `<ui-component>` tags. See [Section 5](#5-quick-test-without-an-ai-agent) for details.

### Option C: Frontend-only testing

You can test the renderer components directly by temporarily modifying `ChatMessage.tsx` or creating a test page. See [Section 5](#5-quick-test-without-an-ai-agent).

---

## 3. Test Examples — Step by Step

Each example below shows:
1. What to ask the agent (prompt)
2. What the agent should respond with (expected response format)
3. What the user sees (rendered output description)

### Example 1: Stats Card — Revenue KPI

**Prompt to agent:**
> Show me total revenue for Q1 2026

**Expected agent response (raw text):**
```
Here's the Q1 2026 revenue summary:

<ui-component type="stats-card" data='{"title":"Q1 2026 Revenue","value":1245000,"change":12.5,"changeLabel":"vs Q1 2025","format":"currency"}' />

Revenue increased 12.5% compared to the same quarter last year, driven primarily by growth in the enterprise segment.
```

**What renders:**
- Markdown paragraph: "Here's the Q1 2026 revenue summary:"
- A card showing:
  - Title: "Q1 2026 Revenue" (muted text)
  - Value: "$1,245,000" (large bold)
  - Green trend arrow with "+12.5% vs Q1 2025"
- Markdown paragraph: "Revenue increased 12.5%..."

**Data schema:**
```json
{
  "title": "Q1 2026 Revenue",
  "value": 1245000,
  "change": 12.5,
  "changeLabel": "vs Q1 2025",
  "format": "currency"
}
```

**Supported `format` values:** `"currency"`, `"number"`, `"percent"`, `"compact"`

---

### Example 2: KPI Grid — Financial Dashboard

**Prompt to agent:**
> Give me a financial overview of last month

**Expected agent response:**
```
Here's your financial overview for February 2026:

<ui-component type="kpi-grid" data='{"title":"February 2026 Financial Summary","items":[{"label":"Revenue","value":425000,"change":8.3,"format":"currency"},{"label":"Expenses","value":312000,"change":-2.1,"format":"currency"},{"label":"Net Profit","value":113000,"change":24.6,"format":"currency"},{"label":"Profit Margin","value":26.6,"change":3.2,"format":"percent"}],"columns":4}' />

All key metrics show improvement. Net profit grew 24.6% month-over-month with expenses declining by 2.1%.
```

**What renders:**
- A card with title "February 2026 Financial Summary"
- 4-column grid with:
  - Revenue: $425,000 (green +8.3%)
  - Expenses: $312,000 (red -2.1%)
  - Net Profit: $113,000 (green +24.6%)
  - Profit Margin: 26.6% (green +3.2%)

**Data schema:**
```json
{
  "title": "February 2026 Financial Summary",
  "items": [
    { "label": "Revenue", "value": 425000, "change": 8.3, "format": "currency" },
    { "label": "Expenses", "value": 312000, "change": -2.1, "format": "currency" },
    { "label": "Net Profit", "value": 113000, "change": 24.6, "format": "currency" },
    { "label": "Profit Margin", "value": 26.6, "change": 3.2, "format": "percent" }
  ],
  "columns": 4
}
```

---

### Example 3: Bar Chart — Sales by Region

**Prompt to agent:**
> Compare sales across regions for this quarter

**Expected agent response:**
```
Here's the regional sales breakdown for Q1 2026:

<ui-component type="bar-chart" data='{"title":"Q1 2026 Sales by Region","description":"Revenue in thousands (USD)","items":[{"region":"North America","revenue":520,"orders":145},{"region":"Europe","revenue":380,"orders":112},{"region":"Asia Pacific","revenue":290,"orders":98},{"region":"Latin America","revenue":145,"orders":56},{"region":"Middle East","revenue":95,"orders":32}],"categoryKey":"region","bars":[{"dataKey":"revenue","label":"Revenue ($K)","color":"#8884d8"},{"dataKey":"orders","label":"Orders","color":"#82ca9d"}]}' />

North America leads with $520K in revenue, followed by Europe at $380K. Asia Pacific shows strong growth potential.
```

**What renders:**
- A card with "Q1 2026 Sales by Region" title
- Grouped bar chart with two bars per region (Revenue and Orders)
- Color-coded legend
- Tooltip on hover showing exact values

**Data schema:**
```json
{
  "title": "Q1 2026 Sales by Region",
  "description": "Revenue in thousands (USD)",
  "items": [
    { "region": "North America", "revenue": 520, "orders": 145 },
    { "region": "Europe", "revenue": 380, "orders": 112 }
  ],
  "categoryKey": "region",
  "bars": [
    { "dataKey": "revenue", "label": "Revenue ($K)", "color": "#8884d8" },
    { "dataKey": "orders", "label": "Orders", "color": "#82ca9d" }
  ]
}
```

**Optional properties:**
- `stacked: true` — stack bars instead of grouping
- `horizontal: true` — render bars horizontally

---

### Example 4: Line Chart — Monthly Revenue Trend

**Prompt to agent:**
> Show me the revenue trend for the last 6 months

**Expected agent response:**
```
Here's the revenue trend from September 2025 to February 2026:

<ui-component type="line-chart" data='{"title":"Monthly Revenue Trend","description":"Last 6 months","items":[{"month":"Sep 2025","revenue":380000,"target":400000},{"month":"Oct 2025","revenue":420000,"target":410000},{"month":"Nov 2025","revenue":395000,"target":420000},{"month":"Dec 2025","revenue":510000,"target":430000},{"month":"Jan 2026","revenue":445000,"target":440000},{"month":"Feb 2026","revenue":485000,"target":450000}],"xKey":"month","lines":[{"dataKey":"revenue","label":"Actual Revenue","color":"#8884d8"},{"dataKey":"target","label":"Target","color":"#82ca9d","dashed":true}]}' />

Revenue has been trending upward with a strong December spike. January and February both exceeded targets.
```

**What renders:**
- Line chart with two lines: solid for actual revenue, dashed for target
- Smooth curved lines with data points
- Interactive tooltip on hover
- Legend showing both series

**Data schema:**
```json
{
  "title": "Monthly Revenue Trend",
  "items": [
    { "month": "Sep 2025", "revenue": 380000, "target": 400000 },
    { "month": "Oct 2025", "revenue": 420000, "target": 410000 }
  ],
  "xKey": "month",
  "lines": [
    { "dataKey": "revenue", "label": "Actual Revenue", "color": "#8884d8" },
    { "dataKey": "target", "label": "Target", "color": "#82ca9d", "dashed": true }
  ]
}
```

---

### Example 5: Pie Chart — Expense Breakdown

**Prompt to agent:**
> Show me a breakdown of our expenses

**Expected agent response:**
```
Here's the expense distribution for February 2026:

<ui-component type="pie-chart" data='{"title":"February 2026 Expense Breakdown","items":[{"category":"Salaries & Wages","amount":156000},{"category":"Raw Materials","amount":89000},{"category":"Marketing","amount":32000},{"category":"Rent & Utilities","amount":18000},{"category":"Software & Tools","amount":12000},{"category":"Other","amount":5000}],"nameKey":"category","valueKey":"amount"}' />

Salaries make up the largest expense at 50%, followed by raw materials at 28.5%.
```

**What renders:**
- Pie chart with labeled slices showing category names and percentages
- Color-coded legend below
- Hover tooltip with formatted numbers

**Optional:** Add `"donut": true` for a donut chart variant.

---

### Example 6: Area Chart — Cash Flow Over Time

**Prompt to agent:**
> Show me cash flow for the last quarter

**Expected agent response:**
```
Here's the cash flow analysis for Q1 2026:

<ui-component type="area-chart" data='{"title":"Q1 2026 Cash Flow","description":"Inflows vs Outflows (USD)","items":[{"week":"W1 Jan","inflow":120000,"outflow":95000},{"week":"W2 Jan","inflow":105000,"outflow":88000},{"week":"W3 Jan","inflow":135000,"outflow":102000},{"week":"W4 Jan","inflow":98000,"outflow":91000},{"week":"W1 Feb","inflow":142000,"outflow":98000},{"week":"W2 Feb","inflow":118000,"outflow":85000},{"week":"W3 Feb","inflow":128000,"outflow":105000},{"week":"W4 Feb","inflow":155000,"outflow":92000}],"xKey":"week","areas":[{"dataKey":"inflow","label":"Cash Inflow","color":"#82ca9d"},{"dataKey":"outflow","label":"Cash Outflow","color":"#ff7300"}]}' />

Cash inflows consistently exceeded outflows throughout Q1, with the strongest positive gap in late February.
```

---

### Example 7: Data Table — Outstanding Invoices

**Prompt to agent:**
> Show me all outstanding invoices

**Expected agent response:**
```
Here are the outstanding invoices requiring attention:

<ui-component type="data-table" data='{"title":"Outstanding Invoices","description":"As of March 19, 2026","columns":["Invoice #","Customer","Amount","Due Date",{"label":"Status","format":"badge"},{"label":"Days Overdue","align":"right"}],"rows":[["INV-2026-0142","Acme Corp",28500,"2026-03-15","Overdue",4],["INV-2026-0138","GlobalTech Ltd",42000,"2026-03-10","Overdue",9],["INV-2026-0155","Smith & Associates",12800,"2026-03-25","Pending",null],["INV-2026-0159","Pacific Trading Co",8900,"2026-03-28","Pending",null],["INV-2026-0161","Northern Industries",35200,"2026-04-01","Pending",null]],"striped":true}' />

Two invoices are overdue totaling $70,500. I recommend following up with Acme Corp and GlobalTech Ltd immediately.
```

**What renders:**
- A data table with formatted columns
- "Overdue" appears as a red badge, "Pending" as a muted badge
- Striped rows for readability
- Days Overdue is right-aligned
- Null values render as "—"

**Column definition options:**
- Simple string: `"Customer"` — left-aligned, no formatting
- Object: `{"label": "Status", "format": "badge"}` — with badge formatting
- Object: `{"label": "Amount", "align": "right", "format": "currency"}` — right-aligned currency

**Supported `format` values for columns:** `"badge"`, `"currency"`, `"number"`, `"percent"`

**Badge color rules (automatic):**
- Green: paid, completed, active, approved, submitted, success
- Red: overdue, failed, cancelled, rejected, error
- Gray: pending, draft, unpaid, open
- Outline: everything else

---

### Example 8: Progress Card — Quarterly Targets

**Prompt to agent:**
> How are we tracking against quarterly targets?

**Expected agent response:**
```
Here's how you're tracking against Q1 2026 targets:

<ui-component type="progress-card" data='{"title":"Q1 2026 Target Progress","description":"Updated March 19, 2026","items":[{"label":"Revenue Target ($1.2M)","value":1050000,"max":1200000},{"label":"New Customers (50)","value":38,"max":50},{"label":"Customer Retention","value":94,"max":100},{"label":"Support Tickets Resolved","value":892,"max":1000}]}' />

Revenue is at 87.5% of target with 12 days remaining. Customer acquisition needs acceleration to reach the 50-customer goal.
```

**What renders:**
- Card with title and description
- Four progress bars, each showing label, percentage, and fill level
- Revenue at 87.5%, New Customers at 76%, Retention at 94%, Tickets at 89.2%

**Single progress bar mode:**
```json
{
  "title": "Monthly Sales Quota",
  "value": 78000,
  "max": 100000,
  "label": "Current Progress",
  "showPercent": true
}
```

---

### Example 9: Info Card — Sales Order Summary

**Prompt to agent:**
> Show me the details of Sales Order SO-2026-0089

**Expected agent response:**
```
Here are the details for Sales Order SO-2026-0089:

<ui-component type="info-card" data='{"title":"SO-2026-0089","status":"Submitted","description":"Sales Order for Acme Corp","sections":[{"heading":"Order Details","items":[{"label":"Customer","value":"Acme Corp"},{"label":"Order Date","value":"March 15, 2026"},{"label":"Delivery Date","value":"March 28, 2026"},{"label":"Payment Terms","value":"Net 30"}]},{"heading":"Financials","items":[{"label":"Subtotal","value":"$42,500.00"},{"label":"Tax (8%)","value":"$3,400.00"},{"label":"Grand Total","value":"$45,900.00"},{"label":"Payment Status","value":"Unpaid","badge":true}]}]}' />

This order is due for delivery on March 28. Payment of $45,900 is due by April 14 under Net 30 terms.
```

**What renders:**
- Card with title "SO-2026-0089" and green "Submitted" badge
- Description: "Sales Order for Acme Corp"
- Two sections separated by dividers:
  - "Order Details" with key-value pairs
  - "Financials" with "Unpaid" rendered as a badge

---

### Example 10: Multi-Component — Full Sales Report

**Prompt to agent:**
> Give me a complete sales report for last month

**Expected agent response:**
```
## February 2026 Sales Report

Here's the complete sales overview:

<ui-component type="kpi-grid" data='{"title":"Key Metrics","items":[{"label":"Total Revenue","value":485000,"change":8.3,"format":"currency"},{"label":"Orders","value":156,"change":12.1,"format":"number"},{"label":"Avg Order Value","value":3109,"change":-3.4,"format":"currency"},{"label":"Win Rate","value":68.5,"change":2.8,"format":"percent"}],"columns":4}' />

### Revenue by Product Category

<ui-component type="bar-chart" data='{"title":"Revenue by Category","items":[{"category":"Enterprise Software","revenue":195000},{"category":"Professional Services","revenue":142000},{"category":"Support Contracts","revenue":89000},{"category":"Training","revenue":35000},{"category":"Hardware","revenue":24000}],"categoryKey":"category","dataKey":"revenue"}' />

### Monthly Trend

<ui-component type="line-chart" data='{"title":"Revenue vs Target — Last 6 Months","items":[{"month":"Sep","actual":380000,"target":400000},{"month":"Oct","actual":420000,"target":410000},{"month":"Nov","actual":395000,"target":420000},{"month":"Dec","actual":510000,"target":430000},{"month":"Jan","actual":445000,"target":440000},{"month":"Feb","actual":485000,"target":450000}],"xKey":"month","lines":[{"dataKey":"actual","label":"Actual","color":"#8884d8"},{"dataKey":"target","label":"Target","color":"#82ca9d","dashed":true}]}' />

### Top Deals

<ui-component type="data-table" data='{"title":"Top 5 Deals — February 2026","columns":["Deal","Customer",{"label":"Value","align":"right","format":"currency"},{"label":"Stage","format":"badge"}],"rows":[["Enterprise Platform","Acme Corp",125000,"Completed"],["Cloud Migration","GlobalTech",89000,"Completed"],["Support Renewal","Pacific Trading",45000,"Completed"],["Custom Dev","Northern Ind.",38000,"Pending"],["Training Package","Smith & Assoc",28000,"Pending"]],"striped":true}' />

### Target Completion

<ui-component type="progress-card" data='{"title":"February Targets","items":[{"label":"Revenue ($450K target)","value":485000,"max":450000},{"label":"New Deals (20 target)","value":18,"max":20},{"label":"Customer Satisfaction","value":92,"max":100}]}' />

Overall strong performance in February. Revenue exceeded the $450K target by 7.8%. Two more deals needed to hit the new deals target — focus on the pending proposals for Northern Industries and Smith & Associates.
```

**What renders:**
- Markdown heading "February 2026 Sales Report"
- KPI grid with 4 metrics
- Bar chart showing revenue by category
- Line chart comparing actual vs target
- Data table of top deals with status badges
- Progress card showing target completion
- Closing analysis paragraph

---

## 4. Agent Instruction Templates

### Minimal Instructions (add to agent system prompt)

```
When presenting data, use <ui-component> tags. Available types:
stats-card, kpi-grid, bar-chart, line-chart, pie-chart, area-chart, data-table, progress-card, info-card.

Format: <ui-component type="TYPE" data='JSON' />
Use single quotes around data attribute. Always self-close with />.
```

### Full Instructions (recommended for best results)

```
## Rich UI Components

When presenting numerical data, metrics, charts, tables, or structured information, use <ui-component> tags to render interactive components inline.

### Tag Format
<ui-component type="TYPE" data='JSON_DATA' />

Rules:
- Always self-closing (ends with />)
- data attribute uses SINGLE quotes around the JSON
- JSON inside uses double quotes as normal
- You can include multiple components and mix with regular text/markdown

### Available Components

**stats-card** — Single KPI metric
data: {"title":"Label", "value":number, "change":number, "changeLabel":"vs period", "format":"currency|number|percent|compact", "description":"optional note"}

**kpi-grid** — Multiple KPIs in a grid
data: {"title":"Section", "items":[{"label":"Metric", "value":number, "change":number, "format":"currency|number|percent"}], "columns":2|3|4}

**bar-chart** — Bar chart (vertical, horizontal, stacked)
data: {"title":"Chart Title", "description":"subtitle", "items":[{...data points}], "categoryKey":"x-field", "bars":[{"dataKey":"y-field", "label":"Series Name", "color":"#hex"}], "stacked":false, "horizontal":false}

**line-chart** — Line chart with multiple series
data: {"title":"Title", "items":[{...points}], "xKey":"x-field", "lines":[{"dataKey":"field", "label":"Name", "color":"#hex", "dashed":false}], "curved":true}

**pie-chart** — Pie or donut chart
data: {"title":"Title", "items":[{"name":"Slice", "value":number}], "nameKey":"name", "valueKey":"value", "donut":false}

**area-chart** — Filled area chart
data: {"title":"Title", "items":[{...}], "xKey":"x-field", "areas":[{"dataKey":"field", "label":"Name", "color":"#hex"}], "stacked":false}

**data-table** — Formatted data table
data: {"title":"Title", "columns":["Col1", {"label":"Col2","align":"right","format":"currency|number|percent|badge"}], "rows":[["val1", 100]], "striped":true, "caption":"footnote"}

**progress-card** — Progress bars (single or multi)
Single: {"title":"Title", "value":75, "max":100, "label":"Progress"}
Multi: {"title":"Title", "items":[{"label":"Task", "value":75, "max":100}]}

**info-card** — Key-value detail card
data: {"title":"Title", "status":"Active", "description":"subtitle", "items":[{"label":"Key", "value":"Value", "badge":false}], "sections":[{"heading":"Section", "items":[...]}]}

### Guidelines
- Use stats-card for single important metrics
- Use kpi-grid when showing 2-4 related metrics together
- Use data-table for lists of documents, invoices, orders
- Use line-chart for trends over time
- Use bar-chart for category comparisons
- Use pie-chart for proportion/distribution
- Use info-card for document summaries (Sales Orders, Invoices, etc.)
- Use progress-card for target tracking and completion
- Always include explanatory text around components
- Use "format":"badge" in table columns for status fields
```

---

## 5. Quick-Test Without an AI Agent

If you want to test the rendering without configuring an AI agent, you can verify the components work by injecting test content directly.

### Method 1: Browser Console (fastest)

1. Open the Huf chat interface in your browser
2. Start any conversation (send any message)
3. Open browser DevTools (F12) → Console
4. Run this script to inject a test message:

```javascript
// Find the chat message list container and dispatch a custom event,
// or directly test the parser:

// Test the parser in console:
const testContent = `Here are your metrics:
<ui-component type="stats-card" data='{"title":"Revenue","value":48250,"change":12.5,"format":"currency"}' />
<ui-component type="bar-chart" data='{"title":"Sales","items":[{"name":"Jan","value":4000},{"name":"Feb","value":5200},{"name":"Mar","value":4800}],"categoryKey":"name","dataKey":"value"}' />
That is all.`;

console.log('Content has UI components:', testContent.includes('ui-component'));
```

### Method 2: Create a test message via Frappe API

```python
# Run in bench console: bench --site your-site console
import frappe

# Find an existing conversation or create one
conversation = frappe.get_last_doc("Agent Conversation")

# Create a message with ui-component tags
msg = frappe.get_doc({
    "doctype": "Agent Message",
    "conversation": conversation.name,
    "is_agent_message": 1,
    "content": """Here's a quick financial snapshot:

<ui-component type="kpi-grid" data='{"title":"Q1 Overview","items":[{"label":"Revenue","value":425000,"change":8.3,"format":"currency"},{"label":"Orders","value":156,"change":12.1,"format":"number"},{"label":"Margin","value":32.5,"change":1.2,"format":"percent"}],"columns":3}' />

<ui-component type="data-table" data='{"title":"Recent Orders","columns":["Order","Customer",{"label":"Amount","align":"right","format":"currency"},{"label":"Status","format":"badge"}],"rows":[["SO-001","Acme Corp",28500,"Completed"],["SO-002","GlobalTech",42000,"Pending"],["SO-003","Smith Inc",12800,"Draft"]],"striped":true}' />

All systems normal."""
})
msg.insert()
frappe.db.commit()
print(f"Created message: {msg.name}")
```

Then navigate to the conversation in Huf's chat UI to see the rendered components.

### Method 3: Frontend unit test

Create a test file to verify the parser works correctly:

```typescript
// Quick verification in browser console or test file
import { parseUIComponents, hasUIComponents } from '@/utils/uiComponentParser';

const input = `Text before
<ui-component type="stats-card" data='{"title":"Test","value":100}' />
Text after`;

console.assert(hasUIComponents(input) === true, 'Should detect UI components');

const result = parseUIComponents(input);
console.assert(result.components.length === 1, 'Should parse 1 component');
console.assert(result.components[0].type === 'stats-card', 'Type should be stats-card');
console.assert((result.components[0].data as any).value === 100, 'Value should be 100');
console.assert(result.text.includes('Text before'), 'Should preserve surrounding text');
console.assert(result.text.includes('Text after'), 'Should preserve surrounding text');
console.log('All parser tests passed!');
```

---

## 6. Component Reference

### Stats Card (`stats-card`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | Yes | Metric label |
| `value` | number \| string | Yes | The value to display |
| `change` | number | No | Percent change (positive = green, negative = red) |
| `changeLabel` | string | No | Context for the change (e.g., "vs last month") |
| `format` | string | No | `"currency"`, `"number"`, `"percent"`, `"compact"` |
| `prefix` | string | No | Text before value |
| `suffix` | string | No | Text after value |
| `description` | string | No | Small note below the value |

### KPI Grid (`kpi-grid`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Card title |
| `items` | KPIItem[] | Yes | Array of metric items |
| `columns` | number | No | Grid columns (default: min(items.length, 4)) |

KPIItem: `{ label, value, change?, format?, prefix?, suffix? }`

### Bar Chart (`bar-chart`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Chart title |
| `description` | string | No | Subtitle |
| `items` | object[] | Yes | Data points |
| `categoryKey` | string | No | X-axis field name (default: `"name"`) |
| `bars` | BarDef[] | No | Bar definitions (auto-inferred if omitted) |
| `dataKey` | string | No | Simple single-bar shorthand |
| `stacked` | boolean | No | Stack bars |
| `horizontal` | boolean | No | Horizontal orientation |

BarDef: `{ dataKey, label?, color? }`

### Line Chart (`line-chart`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Chart title |
| `description` | string | No | Subtitle |
| `items` | object[] | Yes | Data points |
| `xKey` | string | No | X-axis field name (default: `"name"`) |
| `lines` | LineDef[] | No | Line definitions (auto-inferred if omitted) |
| `curved` | boolean | No | Smooth curves (default: true) |

LineDef: `{ dataKey, label?, color?, dashed? }`

### Pie Chart (`pie-chart`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Chart title |
| `description` | string | No | Subtitle |
| `items` | object[] | Yes | Slice data |
| `nameKey` | string | No | Slice label field (default: `"name"`) |
| `valueKey` | string | No | Slice value field (default: `"value"`) |
| `donut` | boolean | No | Render as donut chart |
| `colors` | string[] | No | Custom color palette |

### Area Chart (`area-chart`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Chart title |
| `description` | string | No | Subtitle |
| `items` | object[] | Yes | Data points |
| `xKey` | string | No | X-axis field (default: `"name"`) |
| `areas` | AreaDef[] | No | Area definitions (auto-inferred if omitted) |
| `stacked` | boolean | No | Stack areas |

AreaDef: `{ dataKey, label?, color? }`

### Data Table (`data-table`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Table title |
| `description` | string | No | Subtitle |
| `columns` | (string \| ColumnDef)[] | Yes | Column definitions |
| `rows` | (string \| number \| null)[][] | Yes | Row data arrays |
| `caption` | string | No | Table footer caption |
| `striped` | boolean | No | Alternate row shading |

ColumnDef: `{ label, align?: "left"|"center"|"right", format?: "currency"|"number"|"percent"|"badge" }`

### Progress Card (`progress-card`)

**Single bar mode:**

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Card title |
| `description` | string | No | Subtitle |
| `value` | number | Yes | Current value |
| `max` | number | No | Maximum value (default: 100) |
| `label` | string | No | Progress label |
| `showPercent` | boolean | No | Show as percentage (default: true) |

**Multi-bar mode:**

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Card title |
| `description` | string | No | Subtitle |
| `items` | ProgressItem[] | Yes | Progress items |

ProgressItem: `{ label, value, max?, color? }`

### Info Card (`info-card`)

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | Yes | Card title |
| `description` | string | No | Subtitle |
| `status` | string | No | Status badge text |
| `items` | InfoItem[] | No | Key-value pairs (flat mode) |
| `sections` | InfoSection[] | No | Grouped sections with headings |

InfoItem: `{ label, value, badge? }`
InfoSection: `{ heading?, items: InfoItem[] }`

---

## 7. Troubleshooting

### Component not rendering — shows raw text

**Cause:** The tag syntax is incorrect.

**Check:**
- Tag must be self-closing: `/>` at the end
- `type` attribute must be quoted: `type="bar-chart"`
- `data` attribute must use single quotes: `data='...'`
- JSON inside data must be valid (matching braces, proper quoting)

**Fix:** Ensure the agent prompt clearly specifies the tag format rules.

### Shows "Unknown component type" alert

**Cause:** The `type` value doesn't match any registered renderer.

**Check:** Registered types are: `stats-card`, `kpi-grid`, `bar-chart`, `line-chart`, `pie-chart`, `area-chart`, `data-table`, `progress-card`, `info-card`.

**Fix:** Verify the type string matches exactly (case-sensitive, hyphenated).

### Shows "Component error — Invalid JSON" alert

**Cause:** The JSON in the `data` attribute is malformed.

**Common issues:**
- Missing closing brace `}`
- Trailing comma in arrays/objects
- Using single quotes inside JSON (must use double quotes)
- Unescaped characters

**Fix:** Validate the JSON separately. Instruct the agent to double-check JSON validity.

### Chart renders but shows no data

**Cause:** The `dataKey` or `categoryKey` doesn't match the field names in items.

**Check:** Ensure the field names in `items` objects match the `dataKey`, `categoryKey`, `xKey`, `nameKey`, or `valueKey` values.

### Components render but not during streaming

**Expected behavior:** Components only appear once the full `<ui-component ... />` tag has been received. During streaming, partial tags are treated as text and don't render. The component materializes when the closing `/>` arrives.

This is by design — it prevents rendering with incomplete JSON data.

### Badge colors are wrong

The badge color is determined automatically by keyword matching:
- **Green (default):** paid, completed, active, approved, submitted, success
- **Red (destructive):** overdue, failed, cancelled, rejected, error
- **Gray (secondary):** pending, draft, unpaid, open
- **Outline:** anything else

If you need specific colors, consider using the `info-card` component where badge styling is more controlled.
