"""
Chart generation tools for HUF agents.

Provides tools for generating interactive charts using nivo.
The charts are rendered on the frontend using @nivo React components.
"""

import frappe
from typing import Any


def _extract_numeric_keys(data: list[dict]) -> list[str]:
    """Extract keys with numeric values from first data item."""
    if not data or not isinstance(data, list):
        return []
    first = data[0] if data else {}
    if not isinstance(first, dict):
        return []
    return [k for k, v in first.items() if isinstance(v, (int, float))]


def _find_index_key(data: list[dict]) -> str:
    """Find the likely index/category key."""
    if not data or not isinstance(data, list):
        return "id"
    first = data[0] if data else {}
    if not isinstance(first, dict):
        return "id"
    for key in ["id", "name", "category", "label", "index", "country", "month", "year", "date"]:
        if key in first:
            return key
    # Return first string key
    for k, v in first.items():
        if isinstance(v, str):
            return k
    return list(first.keys())[0] if first else "id"


def handle_generate_chart(
    chart_type: str,
    title: str,
    data: Any,
    config: dict = None,
    **kwargs
) -> dict:
    """
    Generate a data visualization chart.

    Use this tool when the user wants to visualize data as a chart.
    The chart will be rendered interactively in the frontend.

    Args:
        chart_type: Type of chart to generate. Supported types:
            - bar: Compare values across categories (vertical/horizontal bars)
            - line: Show trends over time or continuous data
            - pie: Show proportions of a whole (also supports donut style)
            - radar: Compare multiple variables across categories
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
            - sankey: {"nodes": [{"id": "A"}, ...], "links": [{"source": "A", "target": "B", "value": 100}, ...]}
            - treemap: {"name": "root", "children": [{"name": "child", "value": 100}, ...]}
            - sunburst: {"name": "root", "children": [...]} (same as treemap)
            - chord: [[n, n, ...], ...] (matrix format showing relationships)
            - calendar: [{"day": "2024-01-15", "value": 50}, ...]

        config: Optional configuration overrides (colors, margins, legends, etc.)
            Common options:
            - colors: {"scheme": "nivo"} or ["#e8c1a0", "#f47560", ...]
            - margin: {"top": 40, "right": 80, "bottom": 60, "left": 60}
            - enableLabel: true/false
            - legends: [{"anchor": "bottom", "direction": "row", ...}]

    Returns:
        Chart configuration for frontend rendering
    """
    try:
        # Validate chart type
        valid_types = ["bar", "line", "pie", "radar", "heatmap", "sankey", "treemap", "sunburst", "chord", "calendar"]
        if chart_type not in valid_types:
            return {
                "success": False,
                "error": f"Invalid chart type '{chart_type}'. Supported types: {', '.join(valid_types)}"
            }

        # Validate data is present
        if data is None:
            return {
                "success": False,
                "error": "Data is required for chart generation"
            }

        # Default configurations per chart type
        defaults = {
            "bar": {
                "keys": _extract_numeric_keys(data) if isinstance(data, list) else ["value"],
                "indexBy": _find_index_key(data) if isinstance(data, list) else "id",
                "groupMode": "grouped",
                "layout": "vertical",
                "colors": {"scheme": "nivo"},
                "enableLabel": True,
                "labelSkipWidth": 12,
                "labelSkipHeight": 12,
                "axisBottom": {
                    "tickSize": 5,
                    "tickPadding": 5,
                    "tickRotation": 0,
                },
                "axisLeft": {
                    "tickSize": 5,
                    "tickPadding": 5,
                    "tickRotation": 0,
                },
            },
            "line": {
                "xScale": {"type": "point"},
                "yScale": {"type": "linear", "min": "auto", "max": "auto"},
                "curve": "monotoneX",
                "pointSize": 10,
                "pointBorderWidth": 2,
                "pointBorderColor": {"from": "serieColor"},
                "useMesh": True,
                "enableSlices": "x",
                "colors": {"scheme": "nivo"},
            },
            "pie": {
                "innerRadius": 0.5,
                "padAngle": 0.7,
                "cornerRadius": 3,
                "activeOuterRadiusOffset": 8,
                "arcLinkLabelsSkipAngle": 10,
                "arcLinkLabelsTextColor": "hsl(var(--foreground))",
                "arcLinkLabelsThickness": 2,
                "arcLinkLabelsColor": {"from": "color"},
                "arcLabelsSkipAngle": 10,
                "colors": {"scheme": "nivo"},
            },
            "radar": {
                "indexBy": "category",
                "keys": _extract_numeric_keys(data) if isinstance(data, list) else ["value"],
                "maxValue": "auto",
                "curve": "linearClosed",
                "fillOpacity": 0.25,
                "dotSize": 8,
                "dotBorderWidth": 2,
                "colors": {"scheme": "nivo"},
            },
            "heatmap": {
                "colors": {
                    "type": "sequential",
                    "scheme": "blues",
                },
                "emptyColor": "#555555",
            },
            "sankey": {
                "nodeOpacity": 1,
                "nodeThickness": 18,
                "nodeInnerPadding": 3,
                "nodeSpacing": 24,
                "nodeBorderWidth": 0,
                "linkOpacity": 0.5,
                "linkBlendMode": "multiply",
                "enableLinkGradient": True,
                "colors": {"scheme": "category10"},
            },
            "treemap": {
                "identity": "name",
                "value": "value",
                "innerPadding": 3,
                "outerPadding": 3,
                "colors": {"scheme": "nivo"},
                "borderWidth": 1,
                "borderColor": {"from": "color", "modifiers": [["darker", 0.3]]},
            },
            "sunburst": {
                "id": "name",
                "value": "value",
                "cornerRadius": 2,
                "borderWidth": 1,
                "borderColor": {"from": "color", "modifiers": [["darker", 0.3]]},
                "colors": {"scheme": "nivo"},
                "enableArcLabels": True,
                "arcLabelsSkipAngle": 10,
            },
            "chord": {
                "padAngle": 0.02,
                "innerRadiusRatio": 0.96,
                "innerRadiusOffset": 0.02,
                "arcOpacity": 1,
                "arcBorderWidth": 1,
                "arcBorderColor": {"from": "color", "modifiers": [["darker", 0.4]]},
                "ribbonOpacity": 0.5,
                "ribbonBorderWidth": 1,
                "ribbonBorderColor": {"from": "color", "modifiers": [["darker", 0.4]]},
                "colors": {"scheme": "nivo"},
            },
            "calendar": {
                "emptyColor": "#eeeeee",
                "colors": ["#61cdbb", "#97e3d5", "#e8c1a0", "#f47560"],
                "yearSpacing": 40,
                "monthBorderColor": "#ffffff",
                "dayBorderWidth": 2,
                "dayBorderColor": "#ffffff",
            },
        }

        base_config = defaults.get(chart_type, {})
        merged_config = {**base_config, **(config or {})}

        return {
            "success": True,
            "type": chart_type,
            "title": title,
            "data": data,
            "config": merged_config,
            "_render": "chart",  # Signal to frontend this is a chart
        }

    except Exception as e:
        frappe.log_error(f"Error generating chart: {str(e)}", "Chart Tool Error")
        return {
            "success": False,
            "error": str(e)
        }
