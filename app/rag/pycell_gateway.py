from __future__ import annotations

from typing import Any

from app.api import routes_chat
from app.api.case_browse import _case_status
from app.models.schemas import QueryRequest, RetrieveRequest
from app.rag.admin_publish import catalog_status, media_status, publish_catalog, publish_media, reindex_catalog


class PyCellProtocolUnavailable(RuntimeError):
    pass


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _payload_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Expected object payload")
    return dict(value)


class RAGGatewayBackend:
    """In-process RAG facade for Python CellProtocol cells.

    This intentionally reuses the same route/service functions as the HTTP API
    without issuing HTTP requests. Access control should be handled by the
    surrounding trusted Python CellProtocol runtime.
    """

    def list_cases(self) -> dict[str, Any]:
        return _dump(routes_chat.list_cases())

    def case_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("case_id is required")
        routes_chat._validate_case_visibility(case_id, None)
        return _dump(_case_status(case_id))

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = QueryRequest.model_validate(payload)
        response = routes_chat._run_query(req)
        trace = None
        if response.retrieval_debug and isinstance(response.retrieval_debug, dict):
            trace = response.retrieval_debug.get("query_plan")
        return _dump(
            {
                "answer": response.answer,
                "citations": response.citations,
                "retrieval_debug": response.retrieval_debug,
                "trace": trace,
            }
        )

    def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = RetrieveRequest.model_validate(payload)
        return _dump(routes_chat._run_retrieve(req))

    def catalog_publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _dump(publish_catalog(payload))

    def catalog_reindex(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _dump(
            reindex_catalog(
                case_id=str(payload.get("case_id") or "").strip(),
                source_repo=payload.get("source_repo"),
                source_type=payload.get("source_type"),
            )
        )

    def catalog_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _dump(
            catalog_status(
                case_id=str(payload.get("case_id") or "").strip(),
                source_repo=payload.get("source_repo"),
                source_type=payload.get("source_type"),
            )
        )

    def media_publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _dump(publish_media(payload))

    def media_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _dump(
            media_status(
                case_id=str(payload.get("case_id") or "").strip(),
                source_repo=payload.get("source_repo"),
                source_type=payload.get("source_type"),
            )
        )


def contract() -> dict[str, Any]:
    return {
        "name": "RAGGateway",
        "transport": "python-cellprotocol",
        "trust": "in-process",
        "keypaths": {
            "cases.list": {"method": "get", "returns": "RAG case list"},
            "status.get": {"method": "set", "input": {"case_id": "string"}, "returns": "case runtime/corpus status"},
            "query.run": {"method": "set", "input": "QueryRequest", "returns": "QueryResponse"},
            "retrieve.run": {"method": "set", "input": "RetrieveRequest", "returns": "RetrieveResponse"},
            "catalog.publish": {"method": "set", "input": "CatalogPublishRequest", "returns": "publish summary"},
            "catalog.reindex": {"method": "set", "input": {"case_id": "string"}, "returns": "reindex summary"},
            "catalog.status": {"method": "set", "input": {"case_id": "string"}, "returns": "catalog status"},
            "media.publish": {"method": "set", "input": "MediaPublishRequest", "returns": "publish summary"},
            "media.status": {"method": "set", "input": {"case_id": "string"}, "returns": "media status"},
        },
    }


def create_rag_gateway_cell(name: str = "RAGGateway", backend: RAGGatewayBackend | None = None) -> Any:
    try:
        from cellprotocol.general_cell import GeneralCell
    except Exception as exc:  # pragma: no cover - depends on optional external package
        raise PyCellProtocolUnavailable(
            "PyCellProtocol is not importable. Add it to PYTHONPATH or install the pycellprotocol package."
        ) from exc

    backend = backend or RAGGatewayBackend()

    class RAGGatewayCell(GeneralCell):
        def __init__(self) -> None:
            super().__init__(name=name)
            self._get_handlers["cases.list"] = self._cases_list
            self._get_handlers["runtime.contract"] = self._runtime_contract
            self._set_handlers["status.get"] = self._status_get
            self._set_handlers["query.run"] = self._query_run
            self._set_handlers["retrieve.run"] = self._retrieve_run
            self._set_handlers["catalog.publish"] = self._catalog_publish
            self._set_handlers["catalog.reindex"] = self._catalog_reindex
            self._set_handlers["catalog.status"] = self._catalog_status
            self._set_handlers["media.publish"] = self._media_publish
            self._set_handlers["media.status"] = self._media_status
            self._explore_contracts.update(contract()["keypaths"])

        async def _runtime_contract(self, keypath: str, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return contract()

        async def _cases_list(self, keypath: str, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.list_cases()

        async def _status_get(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.case_status(_payload_dict(value))

        async def _query_run(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.query(_payload_dict(value))

        async def _retrieve_run(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.retrieve(_payload_dict(value))

        async def _catalog_publish(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.catalog_publish(_payload_dict(value))

        async def _catalog_reindex(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.catalog_reindex(_payload_dict(value))

        async def _catalog_status(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.catalog_status(_payload_dict(value))

        async def _media_publish(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.media_publish(_payload_dict(value))

        async def _media_status(self, keypath: str, value: Any, requester: Any | None) -> dict[str, Any]:
            _ = keypath, requester
            return backend.media_status(_payload_dict(value))

    return RAGGatewayCell()


def create_registry() -> Any:
    try:
        from cellprotocol_scaffold.registry import ScaffoldRegistry
    except Exception as exc:  # pragma: no cover - depends on optional external package
        raise PyCellProtocolUnavailable(
            "cellprotocol_scaffold is not importable. Add PyCellProtocol/src to PYTHONPATH or install pycellprotocol[scaffold]."
        ) from exc

    registry = ScaffoldRegistry()
    registry.add_cell(create_rag_gateway_cell())
    return registry


def create_app() -> Any:
    try:
        from cellprotocol_scaffold.app import create_app as create_scaffold_app
    except Exception as exc:  # pragma: no cover - depends on optional external package
        raise PyCellProtocolUnavailable(
            "cellprotocol_scaffold is not importable. Add PyCellProtocol/src to PYTHONPATH or install pycellprotocol[scaffold]."
        ) from exc

    return create_scaffold_app(create_registry())
