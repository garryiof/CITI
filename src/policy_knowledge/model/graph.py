"""Graph helpers — NetworkX when available, minimal fallback otherwise."""

from __future__ import annotations

from typing import Any

from policy_knowledge.model.schemas import PolicyKnowledge

try:
    import networkx as nx  # type: ignore

    _HAS_NX = True
except ImportError:  # pragma: no cover - exercised when networkx absent locally
    _HAS_NX = False


class _MiniDiGraph:
    """Minimal directed graph for environments without networkx installed."""

    def __init__(self) -> None:
        self._nodes: set[str] = set()
        self._edges: dict[tuple[str, str], dict[str, Any]] = {}

    def add_node(self, node_id: str, **attrs: Any) -> None:
        self._nodes.add(node_id)

    def add_edge(self, u: str, v: str, **attrs: Any) -> None:
        self._nodes.add(u)
        self._nodes.add(v)
        self._edges[(u, v)] = attrs

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def has_edge(self, u: str, v: str) -> bool:
        return (u, v) in self._edges

    def nodes(self) -> set[str]:
        return set(self._nodes)

    def edges(self, data: bool = False):
        if data:
            return [(u, v, attrs) for (u, v), attrs in self._edges.items()]
        return list(self._edges.keys())


def _new_graph():
    if _HAS_NX:
        return nx.DiGraph()
    return _MiniDiGraph()


def build_knowledge_graph(knowledge: PolicyKnowledge):
    g = _new_graph()
    collections = [
        ("policy", [knowledge.policy]),
        ("source_block", knowledge.source_blocks),
        ("requirement", knowledge.requirements),
        ("role", knowledge.roles),
        ("action", knowledge.actions),
        ("process", knowledge.processes),
        ("decision", knowledge.decisions),
        ("risk", knowledge.risks),
        ("control", knowledge.controls),
        ("evidence", knowledge.evidence),
    ]
    for kind, items in collections:
        for item in items:
            node_id = getattr(item, "id")
            label = getattr(item, "title", None) or getattr(item, "name", None) or getattr(item, "label", None) or getattr(item, "text", None) or node_id
            g.add_node(node_id, kind=kind, label=str(label)[:120])
    for edge in knowledge.edges:
        g.add_edge(
            edge.source_id,
            edge.target_id,
            relation_type=edge.relation_type,
            derivation=edge.derivation,
            id=edge.id,
        )
    return g


def to_cytoscape_elements(knowledge: PolicyKnowledge) -> list[dict[str, Any]]:
    g = build_knowledge_graph(knowledge)
    elements: list[dict[str, Any]] = []
    if _HAS_NX:
        for node_id, attrs in g.nodes(data=True):
            elements.append({"data": {"id": node_id, **attrs}})
        for u, v, attrs in g.edges(data=True):
            elements.append(
                {
                    "data": {
                        "id": attrs.get("id", f"{u}->{v}"),
                        "source": u,
                        "target": v,
                        **{k: val for k, val in attrs.items() if k != "id"},
                    }
                }
            )
        return elements

    for node_id in g.nodes():
        elements.append({"data": {"id": node_id}})
    for u, v, attrs in g.edges(data=True):
        elements.append(
            {
                "data": {
                    "id": attrs.get("id", f"{u}->{v}"),
                    "source": u,
                    "target": v,
                    **{k: val for k, val in attrs.items() if k != "id"},
                }
            }
        )
    return elements
