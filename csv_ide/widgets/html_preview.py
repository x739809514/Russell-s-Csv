import html
import re
from typing import Optional

from PyQt6 import QtCore, QtWebEngineWidgets, QtWidgets


class HtmlPreviewWindow(QtWidgets.QMainWindow):
    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, show_editor: bool = True
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("HTML Preview")
        self.resize(900, 600)
        self._show_editor = show_editor

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

    def _build_html(self, raw: str) -> str:
        content = raw.strip()
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
      body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; }}
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
        }}

        canvas.addEventListener("wheel", (event) => {{
          event.preventDefault();
          const direction = event.deltaY > 0 ? 0.9 : 1.1;
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

        node_width = 308
        node_height = 96
        x_gap = 196
        y_gap = 126
        padding = 50

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

        svg_parts = [
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            'xmlns="http://www.w3.org/2000/svg">',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" '
            'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 10 5 L 0 10 z" '
            'fill="#444"/></marker></defs>',
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
            svg_parts.append(
                f'<line x1="{start_x}" y1="{start_y}" x2="{end_x}" y2="{end_y}" '
                'stroke="#444" stroke-width="2" marker-end="url(#arrow)" />'
            )
            if label:
                label_x = (start_x + end_x) / 2
                label_y = (start_y + end_y) / 2 - 6
                svg_parts.append(
                    f'<text x="{label_x}" y="{label_y}" font-size="16" '
                    f'fill="#333" text-anchor="middle">{esc(label)}</text>'
                )

        for node, (x, y) in positions.items():
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" '
                'rx="6" ry="6" fill="#F9F9F9" stroke="#333" stroke-width="1.5" />'
            )
            svg_parts.append(
                f'<text x="{x + node_width / 2}" y="{y + node_height / 2 + 4}" '
                'font-size="17" fill="#111" text-anchor="middle">'
                f'{esc(node)}</text>'
            )
        svg_parts.append("</svg>")
        return "\n".join(svg_parts)
