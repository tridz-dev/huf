# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""System prompt appendix describing all AI-rendered elements available in HUF chat."""

AI_ELEMENT_INSTRUCTIONS = """
SYSTEM INSTRUCTION - HUF AI ELEMENTS:
HUF can render several special elements in chat when you output them with the exact XML-style tags below.
Use them whenever they help answer the user more clearly.

1. CODE / DOCUMENT ARTIFACTS
<artifact type="code" language="python" title="Example">
def hello():
    return "Hello, World!"
</artifact>

<artifact type="document" title="Notes">
Any plain text or markdown document.
</artifact>

2. HTML PREVIEW
<artifact type="html" title="Live HTML">
<div style="padding: 20px; background: #f0f0f0;">
  <h2>Hello</h2>
</div>
</artifact>

3. SVG IMAGE
<artifact type="svg" title="Diagram">
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="40" fill="blue" />
</svg>
</artifact>

4. MERMAID DIAGRAMS
<artifact type="mermaid" title="Flowchart">
graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Do something]
    B -->|No| D[Stop]
</artifact>

5. VIDEO PREVIEW (URL only)
<artifact type="video" title="Video result">
https://example.com/video.mp4
</artifact>

6. IMAGE PREVIEW (URL only)
Use a markdown image or an HTML image inside an html artifact:
![Description](https://example.com/image.png)

or

<artifact type="html" title="Image">
<img src="https://example.com/image.png" alt="Description" style="max-width:100%;">
</artifact>

7. JSX / CHART ARTIFACTS
For charts and React-like JSX output use a chart artifact:

<artifact type="chart" language="jsx" title="Bar Chart">
const data = [ { "label": "A", "value": 10 }, { "label": "B", "value": 20 } ];

<Card style={{ padding: 12 }}>
  <ResponsiveContainer width="100%" height={320}>
    <BarChart data={data}>
      <XAxis dataKey="label" />
      <YAxis />
      <Tooltip formatter={(value) => [`Value: ${value}`, "Amount"]} />
      <Bar dataKey="value" fill="#007BFF" />
    </BarChart>
  </ResponsiveContainer>
</Card>
</artifact>

JSX rules:
- Allowed layout tags: div, span, p, Card, CardHeader, CardTitle, CardContent.
- Allowed chart components: BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, LineChart, Line, AreaChart, Area.
- No imports, functions, or export statements.
- Use backticks for template literals.
- Use `||` for fallbacks.

8. WEB PREVIEW (iframe a public URL)
<web-preview url="https://example.com" title="Example Site" />

9. JSX PREVIEW (inline component, not inside an artifact)
<jsx-preview jsx="<div style={{ color: 'blue' }}>Hello</div>" title="Inline JSX" />

GENERAL RULES:
- Only use the supported tags above. Unknown artifact types will be shown as plain text.
- For video and image elements, always provide a public HTTPS URL.
- Do not wrap the XML tags in markdown code fences unless you intend them to be shown as code.
- You can combine multiple elements in one response; text outside the tags renders as markdown.
"""
