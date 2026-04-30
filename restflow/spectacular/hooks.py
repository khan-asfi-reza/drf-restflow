import logging

from restflow.spectacular.parameters import (
    build_filterset_parameters,
    resolve_filterset_class,
)

logger = logging.getLogger(__name__)


def add_filterset_parameters(result, generator, request=None, public=None, **kwargs):  # noqa: ARG001
    """
    drf-spectacular postprocessing hook that injects filter parameters for any view declaring `filterset_class`.
    """
    paths = result.get("paths") or {}

    for path, _path_regex, method, view in generator._get_paths_and_endpoints():
        filterset_class = resolve_filterset_class(view)
        if filterset_class is None:
            continue
        try:
            params = build_filterset_parameters(filterset_class)
        except Exception as exc:
            logger.warning(
                "restflow add_filterset_parameters: failed to build params for %r: %s",
                view,
                exc,
            )
            continue
        if not params:
            continue

        operation = (paths.get(path) or {}).get(method.lower())
        if operation is None:
            continue
        existing = operation.setdefault("parameters", [])
        existing_keys = {
            (p.get("name"), p.get("in"))
            for p in existing
            if isinstance(p, dict)
        }
        for parameter in params:
            key = (parameter.get("name"), parameter.get("in"))
            if key in existing_keys:
                continue
            existing.append(parameter)
            existing_keys.add(key)

    return result
