import html
import json
import re
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWebEngineWidgets, QtWidgets

from csv_ide.theme import theme_palette


class HtmlPreviewWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        show_editor: bool = True,
        enable_node_drag: bool = False,
        layout_path: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("HTML Preview")
        self.resize(900, 600)
        self._show_editor = show_editor
        self._enable_node_drag = enable_node_drag
        self._layout_path = layout_path
        self._layout_map: dict[str, dict[str, float]] = {}
        self._closing_for_layout = False
        if self._enable_node_drag and self._layout_path:
            self._layout_map = self._load_layout_map()

        splitter = QtWidgets.QSplitter(self)
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        self._code_edit = QtWidgets.QPlainTextEdit(self)
        self._code_edit.setPlaceholderText("Paste HTML here...")
        self._preview = QtWebEngineWidgets.QWebEngineView(self)

        splitter.addWidget(self._code_edit)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._code_edit.textChanged.connect(self._update_preview)
        self._update_preview()
        if not self._show_editor:
            self._code_edit.setVisible(False)
            splitter.setSizes([0, 1])

    def set_content(self, content: str) -> None:
        self._code_edit.setPlainText(content)
        self._update_preview()

    def _update_preview(self) -> None:
        raw = self._code_edit.toPlainText()
        self._preview.setHtml(self._build_html(raw))

    def _load_layout_map(self) -> dict[str, dict[str, float]]:
        if not self._layout_path:
            return {}
        try:
            with open(self._layout_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        nodes = data.get("nodes", {})
        if not isinstance(nodes, dict):
            return {}
        layout: dict[str, dict[str, float]] = {}
        for key, value in nodes.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            x = value.get("x")
            y = value.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                layout[key] = {"x": float(x), "y": float(y)}
        return layout

    def _save_layout_map(self, layout: dict[str, dict[str, float]]) -> None:
        if not self._layout_path:
            return
        payload = {"version": 1, "nodes": layout}
        try:
            with open(self._layout_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        except OSError:
            return

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not self._enable_node_drag or not self._layout_path:
            super().closeEvent(event)
            return
        if self._closing_for_layout:
            super().closeEvent(event)
            return
        event.ignore()

        def _on_layout(result: object) -> None:
            layout = result if isinstance(result, dict) else {}
            if layout:
                self._save_layout_map(layout)
            self._closing_for_layout = True
            self.close()

        self._preview.page().runJavaScript(
            "window.__graphLayout && window.__graphLayout()", _on_layout
        )

    def _build_html(self, raw: str) -> str:
        content = raw.strip()
        colors = self._theme_colors()
        if not content:
            body = "<p>Paste HTML to preview it here.</p>"
        else:
            mermaid_source = self._extract_mermaid_source(content)
            if mermaid_source:
                body = self._render_simple_graph(mermaid_source)
            else:
                lower = content.lower()
                if "<html" in lower or "<!doctype" in lower:
                    return content
                looks_like_html = re.search(r"</?[a-zA-Z][\s>]", content) is not None
                if looks_like_html:
                    body = content
                else:
                    body = f"<pre>{html.escape(raw)}</pre>"
        return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {{ height: 100%; margin: 0; }}
      body {{
        font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
        background: radial-gradient(circle at 20% 20%, {colors["glow"]}, {colors["window"]} 55%, {colors["base_alt"]});
      }}
      pre {{ white-space: pre-wrap; }}
      #canvas {{ width: 100%; height: 100%; overflow: hidden; cursor: grab; }}
      #pan-zoom {{ transform-origin: 0 0; padding: 16px; }}
    </style>
  </head>
  <body>
    <div id="canvas">
      <div id="pan-zoom">
        {body}
      </div>
    </div>
    <script>
      (function () {{
        const canvas = document.getElementById("canvas");
        const panZoom = document.getElementById("pan-zoom");
        if (!canvas || !panZoom) {{
          return;
        }}
        let scale = 1;
        let translateX = 0;
        let translateY = 0;
        let dragging = false;
        let lastX = 0;
        let lastY = 0;

        function applyTransform() {{
          panZoom.style.transform =
            "translate(" + translateX + "px, " + translateY + "px) scale(" + scale + ")";
          window.__panZoomState = {{
            scale,
            translateX,
            translateY
          }};
        }}

        canvas.addEventListener("wheel", (event) => {{
          event.preventDefault();
          const direction = event.deltaY > 0 ? 0.95 : 1.05;
          const next = Math.min(4, Math.max(0.2, scale * direction));
          scale = next;
          applyTransform();
        }}, {{ passive: false }});

        canvas.addEventListener("mousedown", (event) => {{
          dragging = true;
          canvas.style.cursor = "grabbing";
          lastX = event.clientX;
          lastY = event.clientY;
        }});

        window.addEventListener("mouseup", () => {{
          dragging = false;
          canvas.style.cursor = "grab";
        }});

        window.addEventListener("mousemove", (event) => {{
          if (!dragging) {{
            return;
          }}
          const dx = event.clientX - lastX;
          const dy = event.clientY - lastY;
          lastX = event.clientX;
          lastY = event.clientY;
          translateX += dx;
          translateY += dy;
          applyTransform();
        }});

        applyTransform();
      }})();
    </script>
    {self._drag_script() if self._enable_node_drag else ""}
  </body>
</html>"""

    def _extract_mermaid_source(self, content: str) -> Optional[str]:
        lower = content.lower()
        if "class=\"mermaid\"" in lower:
            match = re.search(r"<pre\\s+class=\\\"mermaid\\\"[^>]*>(.*?)</pre>", content, re.S)
            if match:
                return match.group(1).strip()
        for starter in ("graph ", "flowchart "):
            if lower.startswith(starter):
                return content
        if "-->" in content and "graph" in lower:
            return content
        return None

    def _theme_colors(self) -> dict[str, str]:
        settings = QtCore.QSettings("RussellCsv", "RussellCsv")
        name = settings.value("ui_theme", "light", type=str)
        palette = theme_palette(name)
        if name == "dark":
            return {
                "window": palette["window"],
                "base": palette["base"],
                "base_alt": palette["base_alt"],
                "text": palette["text"],
                "accent": palette["accent"],
                "accent_text": palette["accent_text"],
                "glow": "#1f2429",
                "edge": "#C98D3A",
                "edge_text": "#E0B26C",
                "node_stroke": "#A56B2A",
            }
        return {
            "window": palette["window"],
            "base": palette["base"],
            "base_alt": palette["base_alt"],
            "text": palette["text"],
            "accent": palette["accent"],
            "accent_text": palette["accent_text"],
            "glow": "#fff4dc",
            "edge": "#B5762C",
            "edge_text": "#915A1C",
            "node_stroke": "#B0793B",
        }

    def _drag_script(self) -> str:
        return """
    <script>
      (function () {
        const svg = document.querySelector("svg[data-graph='relation']");
        if (!svg) {
          return;
        }
        const nodes = Array.from(svg.querySelectorAll("g[data-node]"));
        const edges = Array.from(svg.querySelectorAll("path[data-src]"));
        const direction = (svg.getAttribute("data-direction") || "TD").toUpperCase();

        function getRect(node) {
          return {
            x: parseFloat(node.dataset.x || "0"),
            y: parseFloat(node.dataset.y || "0"),
            w: parseFloat(node.dataset.width || "0"),
            h: parseFloat(node.dataset.height || "0")
          };
        }

        function setPos(node, x, y) {
          node.dataset.x = x;
          node.dataset.y = y;
          node.setAttribute("transform", "translate(" + x + " " + y + ")");
        }

        function edgePath(src, dst) {
          const srcCx = src.x + src.w;
          const srcCy = src.y + src.h / 2;
          const dstCx = dst.x;
          const dstCy = dst.y + dst.h / 2;
          if (direction === "TD" || direction === "TB") {
            const sX = src.x + src.w / 2;
            const sY = src.y + src.h;
            const eX = dst.x + dst.w / 2;
            const eY = dst.y;
            const midY = (sY + eY) / 2;
            return "M " + sX + " " + sY + " C " + sX + " " + midY + ", " + eX + " " + midY + ", " + eX + " " + eY;
          }
          const midX = (srcCx + dstCx) / 2;
          return "M " + srcCx + " " + srcCy + " C " + midX + " " + srcCy + ", " + midX + " " + dstCy + ", " + dstCx + " " + dstCy;
        }

        function updateEdgesFor(nodeName) {
          edges.forEach((edge) => {
            if (edge.dataset.src !== nodeName && edge.dataset.dst !== nodeName) {
              return;
            }
            const srcNode = svg.querySelector("g[data-node='" + edge.dataset.src + "']");
            const dstNode = svg.querySelector("g[data-node='" + edge.dataset.dst + "']");
            if (!srcNode || !dstNode) {
              return;
            }
            const src = getRect(srcNode);
            const dst = getRect(dstNode);
            edge.setAttribute("d", edgePath(src, dst));
          });
        }

        function updateAllEdges() {
          edges.forEach((edge) => {
            const srcNode = svg.querySelector("g[data-node='" + edge.dataset.src + "']");
            const dstNode = svg.querySelector("g[data-node='" + edge.dataset.dst + "']");
            if (!srcNode || !dstNode) {
              return;
            }
            const src = getRect(srcNode);
            const dst = getRect(dstNode);
            edge.setAttribute("d", edgePath(src, dst));
          });
        }

        window.__graphLayout = function () {
          const layout = {};
          nodes.forEach((node) => {
            const label = node.dataset.label || node.dataset.node;
            layout[label] = {
              x: parseFloat(node.dataset.x || "0"),
              y: parseFloat(node.dataset.y || "0")
            };
          });
          return layout;
        };

        let dragging = null;
        let lastX = 0;
        let lastY = 0;

        svg.addEventListener("mousedown", (event) => {
          const target = event.target.closest("g[data-node]");
          if (!target) {
            return;
          }
          dragging = target;
          lastX = event.clientX;
          lastY = event.clientY;
          event.preventDefault();
          event.stopPropagation();
        });

        window.addEventListener("mousemove", (event) => {
          if (!dragging) {
            return;
          }
          const state = window.__panZoomState || { scale: 1 };
          const scale = state.scale || 1;
          const dx = (event.clientX - lastX) / scale;
          const dy = (event.clientY - lastY) / scale;
          lastX = event.clientX;
          lastY = event.clientY;
          const rect = getRect(dragging);
          setPos(dragging, rect.x + dx, rect.y + dy);
          updateEdgesFor(dragging.dataset.node);
        });

        window.addEventListener("mouseup", () => {
          dragging = null;
        });

        updateAllEdges();
      })();
    </script>
        """

    def _render_simple_graph(self, source: str) -> str:
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        direction = "TD"
        if lines:
            first = lines[0].lower()
            if first.startswith("graph "):
                direction = first.split(" ", 1)[1].strip().upper()
                lines = lines[1:]
            elif first.startswith("flowchart "):
                direction = first.split(" ", 1)[1].strip().upper()
                lines = lines[1:]
        edges: list[tuple[str, str, str]] = []
        nodes: list[str] = []
        for line in lines:
            if line.startswith("%%"):
                continue
            match = re.match(r"(.+?)-->(.+)", line)
            if not match:
                continue
            left = match.group(1).strip()
            right = match.group(2).strip()
            label = ""
            if right.startswith("|") and "|" in right[1:]:
                label, right = right[1:].split("|", 1)
                right = right.strip()
                label = label.strip()
            left = left.strip()
            right = right.strip()
            if not left or not right:
                continue
            if left not in nodes:
                nodes.append(left)
            if right not in nodes:
                nodes.append(right)
            edges.append((left, right, label))
        if not nodes:
            return "<p>No supported graph lines found.</p>"

        indegree: dict[str, int] = {node: 0 for node in nodes}
        outgoing: dict[str, list[str]] = {node: [] for node in nodes}
        for src, dst, _ in edges:
            outgoing[src].append(dst)
            indegree[dst] += 1

        layers: dict[str, int] = {}
        queue = [node for node in nodes if indegree[node] == 0]
        order = list(queue)
        while queue:
            current = queue.pop(0)
            base = layers.get(current, 0)
            for nxt in outgoing[current]:
                layers[nxt] = max(layers.get(nxt, 0), base + 1)
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
                    order.append(nxt)
        if len(order) != len(nodes):
            order = nodes[:]
            for idx, node in enumerate(order):
                layers[node] = layers.get(node, idx)

        grouped: dict[int, list[str]] = {}
        for node in order:
            layer = layers.get(node, 0)
            grouped.setdefault(layer, []).append(node)

        node_width = 320
        node_height = 96
        x_gap = 190
        y_gap = 120
        padding = 60

        positions: dict[str, tuple[int, int]] = {}
        max_primary = max(grouped.keys())
        max_secondary = max(len(items) for items in grouped.values())
        for layer, items in grouped.items():
            for idx, node in enumerate(items):
                if direction in {"LR", "RL"}:
                    x = padding + layer * (node_width + x_gap)
                    y = padding + idx * (node_height + y_gap)
                else:
                    x = padding + idx * (node_width + x_gap)
                    y = padding + layer * (node_height + y_gap)
                positions[node] = (x, y)

        if direction in {"LR", "RL"}:
            width = padding * 2 + (max_primary + 1) * node_width + max_primary * x_gap
            height = padding * 2 + max_secondary * node_height + max(0, max_secondary - 1) * y_gap
        else:
            width = padding * 2 + max_secondary * node_width + max(0, max_secondary - 1) * x_gap
            height = padding * 2 + (max_primary + 1) * node_height + max_primary * y_gap

        def esc(value: str) -> str:
            return html.escape(value, quote=True)

        colors = self._theme_colors()
        if colors["window"] == "#121416":
            palette = [
                ("#23282C", "#3C8BC8"),
                ("#2A2E33", "#C88D3B"),
                ("#2B332E", "#57A374"),
                ("#2E2730", "#C77A9A"),
            ]
        else:
            palette = [
                ("#FFF3E0", "#E1A24C"),
                ("#EAF2FF", "#6C8DC8"),
                ("#ECF8EC", "#67A470"),
                ("#FDEBF2", "#C96E8C"),
            ]

        def node_lines(text: str) -> list[str]:
            if " (" in text and text.endswith(")"):
                left, right = text[:-1].split(" (", 1)
                return [left, right]
            if "\\n" in text:
                return [part for part in text.split("\\n") if part]
            return [text]

        if self._enable_node_drag and self._layout_map:
            for node, coords in self._layout_map.items():
                if node in positions:
                    positions[node] = (coords.get("x", positions[node][0]), coords.get("y", positions[node][1]))

        node_ids = {node: f"node-{idx}" for idx, node in enumerate(nodes)}

        svg_parts = [
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'data-graph="relation" data-direction="{direction}" '
            'xmlns="http://www.w3.org/2000/svg">',
            "<defs>",
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" '
            'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 10 5 L 0 10 z" '
            f'fill="{colors["edge"]}"/></marker>',
            '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="3" stdDeviation="6" flood-color="#2b2b2b" flood-opacity="0.15"/>'
            "</filter>",
            "</defs>",
        ]
        for src, dst, label in edges:
            x1, y1 = positions[src]
            x2, y2 = positions[dst]
            start_x = x1 + node_width
            start_y = y1 + node_height / 2
            end_x = x2
            end_y = y2 + node_height / 2
            if direction in {"TD", "TB"}:
                start_x = x1 + node_width / 2
                start_y = y1 + node_height
                end_x = x2 + node_width / 2
                end_y = y2
            if direction in {"LR", "RL"}:
                mid_x = (start_x + end_x) / 2
                path = (
                    f"M {start_x} {start_y} C {mid_x} {start_y}, "
                    f"{mid_x} {end_y}, {end_x} {end_y}"
                )
            else:
                mid_y = (start_y + end_y) / 2
                path = (
                    f"M {start_x} {start_y} C {start_x} {mid_y}, "
                    f"{end_x} {mid_y}, {end_x} {end_y}"
                )
            svg_parts.append(
                f'<path d="{path}" stroke="{colors["edge"]}" stroke-width="2.2" fill="none" '
                f'data-src="{node_ids[src]}" data-dst="{node_ids[dst]}" '
                'marker-end="url(#arrow)" />'
            )
            if label:
                label_x = (start_x + end_x) / 2
                label_y = (start_y + end_y) / 2 - 6
                svg_parts.append(
                    f'<text x="{label_x}" y="{label_y}" font-size="15" '
                    f'fill="{colors["edge_text"]}" text-anchor="middle">{esc(label)}</text>'
                )

        for node, (x, y) in positions.items():
            fill, stroke = palette[layers.get(node, 0) % len(palette)]
            label_attr = esc(node)
            node_id = node_ids[node]
            svg_parts.append(
                f'<g data-node="{node_id}" data-label="{label_attr}" data-x="{x}" '
                f'data-y="{y}" data-width="{node_width}" data-height="{node_height}" '
                f'transform="translate({x} {y})">'
            )
            svg_parts.append(
                f'<rect x="0" y="0" width="{node_width}" height="{node_height}" '
                f'rx="22" ry="22" fill="{fill}" stroke="{stroke}" '
                'stroke-width="1.6" filter="url(#shadow)" />'
            )
            lines = node_lines(node)
            line_height = 18
            block_height = line_height * len(lines)
            start_y = (node_height - block_height) / 2 + line_height - 3
            svg_parts.append(
                f'<text x="{node_width / 2}" y="{start_y}" '
                f'font-size="16" fill="{colors["text"]}" text-anchor="middle">'
            )
            for idx, line in enumerate(lines):
                dy = idx * line_height
                svg_parts.append(
                    f'<tspan x="{node_width / 2}" y="{start_y + dy}">'
                    f"{esc(line)}</tspan>"
                )
            svg_parts.append("</text>")
            svg_parts.append("</g>")
        svg_parts.append("</svg>")
        return "\n".join(svg_parts)
