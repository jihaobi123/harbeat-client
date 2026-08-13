"""UTF-8 UIAutomator semantics with fresh-frame-safe control coordinates."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True)
class SemanticControl:
    label: str
    text: str
    resource_id: str
    class_name: str
    bounds: tuple[int, int, int, int]
    enabled: bool
    clickable: bool

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


def _control_from_node(node: ET.Element) -> SemanticControl | None:
    attrs = node.attrib
    match = _BOUNDS.fullmatch(attrs.get("bounds", ""))
    if not match:
        return None
    description = attrs.get("content-desc", "").strip()
    text = attrs.get("text", "").strip()
    label = description or text
    if not label:
        return None
    return SemanticControl(
        label=label,
        text=text,
        resource_id=attrs.get("resource-id", ""),
        class_name=attrs.get("class", ""),
        bounds=tuple(int(value) for value in match.groups()),
        enabled=attrs.get("enabled") == "true",
        clickable=attrs.get("clickable") == "true",
    )


def parse_controls(xml_source: str | bytes | Path) -> list[SemanticControl]:
    if isinstance(xml_source, Path):
        root = ET.parse(xml_source).getroot()
    else:
        payload = xml_source.decode("utf-8") if isinstance(xml_source, bytes) else xml_source
        root = ET.fromstring(payload)
    controls = []
    for node in root.iter("node"):
        control = _control_from_node(node)
        if control is not None:
            controls.append(control)
    return controls


def find_control(
    controls: list[SemanticControl],
    label: str,
    *,
    resource_id: str | None = None,
    exact: bool = True,
    require_clickable: bool = True,
    require_enabled: bool = True,
) -> SemanticControl | None:
    wanted = label.casefold().strip()
    matches = []
    for control in controls:
        if require_clickable and not control.clickable:
            continue
        if require_enabled and not control.enabled:
            continue
        if resource_id is not None and control.resource_id != resource_id:
            continue
        actual = control.label.casefold().strip()
        label_matches = actual == wanted if exact else wanted in actual
        if label_matches:
            matches.append(control)
    if not matches:
        return None
    matches.sort(key=lambda item: (not item.clickable, item.bounds[1], item.bounds[0]))
    return matches[0]

