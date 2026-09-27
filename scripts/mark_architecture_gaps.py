"""Mark planned but absent components in diagrams.net architecture files."""

from pathlib import Path
import xml.etree.ElementTree as ET


RED = "#c62828"
GAPS = {
    "architecture.drawio": {"state", "featurert", "postgres", "archive"},
    "online-architecture.drawio": {"redis", "worker", "archive", "postgres"},
    "training-architecture.drawio": {"torch"},
    "sequence.drawio": {
        0: {"actor2", "actor3", "label4", "label5", "self6", "label7", "self8", "label11", "label12", "self13", "label14", "label15", "label16", "label17", "note1"},
        1: set(),
    },
}


def mark(cell, root, offset=0):
    style = cell.get("style", "")
    style = style.replace(f";fontColor={RED};strokeColor={RED};", "")
    cell.set("style", style + f";fontColor={RED};strokeColor={RED};")
    geometry = cell.find("mxGeometry")
    if geometry is None or geometry.get("relative") == "1":
        return
    x = float(geometry.get("x", 0))
    y = float(geometry.get("y", 0))
    width = float(geometry.get("width", 0))
    height = float(geometry.get("height", 0))
    line = ET.SubElement(root, "mxCell", {
        "id": f"gap-{cell.get('id')}",
        "value": "",
        "style": f"endArrow=none;startArrow=none;strokeColor={RED};strokeWidth=4;",
        "edge": "1",
        "parent": "1",
    })
    geo = ET.SubElement(line, "mxGeometry", {"relative": "1", "as": "geometry"})
    ET.SubElement(geo, "mxPoint", {"x": str(x + 5), "y": str(y + height - 5 + offset), "as": "sourcePoint"})
    ET.SubElement(geo, "mxPoint", {"x": str(x + width - 5), "y": str(y + 5 + offset), "as": "targetPoint"})


def main():
    docs = Path(__file__).resolve().parents[1] / "docs"
    for filename, gaps in GAPS.items():
        path = docs / filename
        if not path.exists():
            continue
        tree = ET.parse(path)
        diagrams = list(tree.getroot().iter("diagram"))
        for index, diagram in enumerate(diagrams):
            root = diagram.find("mxGraphModel/root")
            if root is None:
                continue
            selected = gaps.get(index, set()) if isinstance(gaps, dict) else gaps
            for old in list(root):
                if old.get("id", "").startswith("gap-"):
                    root.remove(old)
            for cell in list(root):
                if cell.get("id") in selected:
                    mark(cell, root)
                elif filename == "online-architecture.drawio" and cell.get("id") == "api":
                    cell.set("value", "Backend · REST (SSE отсутствует)")
                elif filename == "online-architecture.drawio" and cell.get("id") == "front":
                    cell.set("value", "React · MapLibre (Mantine отсутствует)")
                elif filename == "architecture.drawio" and cell.get("id") == "alert":
                    cell.set("value", "Backend · API и replay\nАлерты в интерфейсе")
                elif filename == "architecture.drawio" and cell.get("id") == "train":
                    cell.set("value", "ML-модуль · обучение\nCatBoostRegressor → MAE\nPyTorch отсутствует")
                elif filename == "sequence.drawio" and index == 1 and cell.get("id") == "self3":
                    cell.set("value", "3. Baseline cur_dev_s; CatBoost (PyTorch отсутствует)")
            if filename == "online-architecture.drawio":
                for name, x, y in (("SSE", 955, 500), ("Mantine", 1250, 500)):
                    note = ET.SubElement(root, "mxCell", {
                        "id": f"gap-note-{name.lower()}", "value": name,
                        "style": "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff3f3;",
                        "vertex": "1", "parent": "1",
                    })
                    ET.SubElement(note, "mxGeometry", {"x": str(x), "y": str(y), "width": "205", "height": "38", "as": "geometry"})
                    mark(note, root)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
