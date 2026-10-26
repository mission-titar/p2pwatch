"""The node metrics in Prometheus's text format 0.0.4, which every Prometheus scrapes. Like the
console's CSV, the text goes through no display."""

from p2pwatch.application.ports.driving.node_metric_lister import NodeMetricListing
from p2pwatch.domain.observability.node_metric import NodeCounter

PROMETHEUS_TEXT_MEDIA_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def prometheus_text(node_metric_listing: NodeMetricListing) -> str:
    """A ``# HELP`` and a ``# TYPE`` line per node metric, then a line per sample; a counter's
    name takes ``_total`` on all of them."""
    lines: list[str] = []
    for node_metric, samples in node_metric_listing.samples_by_node_metric.items():
        is_counter = isinstance(node_metric, NodeCounter)
        exposed_name = (
            f"{node_metric.exposed_name}_total" if is_counter else node_metric.exposed_name
        )
        lines.append(f"# HELP {exposed_name} {node_metric.description}")
        lines.append(f"# TYPE {exposed_name} {'counter' if is_counter else 'gauge'}")
        lines.extend(
            f"{exposed_name}{_label_set(sample.labels)} {sample.value!r}" for sample in samples
        )
    return "".join(f"{line}\n" for line in lines)


def _label_set(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    return (
        "{"
        + ",".join(f'{label_name}="{_escaped(label_value)}"' for label_name, label_value in labels)
        + "}"
    )


def _escaped(label_value: str) -> str:
    return label_value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
