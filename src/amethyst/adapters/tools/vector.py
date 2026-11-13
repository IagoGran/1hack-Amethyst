"""Vector-store adapters. Vendor clients are loaded only when used."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any, cast

from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    OperationContext,
    Source,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

MAX_CHUNKS = 8
# One character per token is a conservative ceiling without choosing a model tokenizer.
MAX_CHUNK_CHARS = 1_000


class _VectorTool:
    name = "vector.query"
    description = "Retrieve relevant records from the configured vector collection."

    def __init__(self, collection: str, *, max_chunks: int = MAX_CHUNKS) -> None:
        """Configure the target collection and retrieval bound.

        Parameters
        ----------
        collection : str
            Vector-store collection name.
        max_chunks : int, optional
            Maximum records returned for one query.
        """
        self.collection = collection
        self.max_chunks = min(max(1, max_chunks), MAX_CHUNKS)

    @property
    def definition(self) -> ToolDefinition:
        """Describe the vector query tool accepted by the agent.

        Returns
        -------
        ToolDefinition
            Query schema requiring a numeric vector.
        """
        return ToolDefinition(
            self.name,
            self.description,
            {
                "type": "object",
                "properties": {
                    "vector": {"type": "array", "items": {"type": "number"}},
                    "limit": {"type": "integer"},
                },
                "required": ["vector"],
            },
        )

    def _validate(self, call: ToolCall) -> tuple[list[float], int]:
        """Validate and normalize query vector and requested result count.

        Parameters
        ----------
        call : ToolCall
            Tool invocation with vector and optional limit.

        Returns
        -------
        tuple
            Finite float vector and bounded result count.

        Raises
        ------
        ContractError
            If the call name, vector, or limit is invalid.
        """
        vector = call.arguments.get("vector")
        if call.name != self.name or not isinstance(vector, list) or not vector:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "A non-empty query vector is required."
            )
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in vector
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Query vector values must be numeric."
            )
        limit = call.arguments.get("limit", self.max_chunks)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Retrieval limit must be an integer."
            )
        numeric_vector = cast(list[int | float], vector)
        return [float(value) for value in numeric_vector], min(
            max(limit, 1), self.max_chunks
        )

    def _result(
        self, call_id: str, records: list[dict[str, Any]], limit: int, output_limit: int
    ) -> ToolResult:
        """Build a bounded JSON result and matching source references.

        Parameters
        ----------
        call_id : str
            ID of the tool invocation.
        records : list of dict
            Retrieved vector-store records.
        limit : int
            Maximum number of records to include.
        output_limit : int
            Maximum serialized output bytes.

        Returns
        -------
        ToolResult
            Serialized records with matching source metadata.
        """
        selected = []
        sources = []
        truncated = False
        for item in records[:limit]:
            text = str(item.get("text", ""))
            if len(text) > MAX_CHUNK_CHARS:
                text = text[:MAX_CHUNK_CHARS]
                truncated = True
            source_id = str(item.get("id", "unknown"))
            metadata = item.get("metadata", {})
            title = str(metadata.get("title", "")) if isinstance(metadata, dict) else ""
            url = metadata.get("url") if isinstance(metadata, dict) else None
            selected.append({"id": source_id, "text": text, "metadata": metadata})
            sources.append(Source(source_id, title, str(url) if url else None))
        if len(records) > limit:
            truncated = True
        # Truncate only at record boundaries to keep valid JSON and matching sources.
        kept: list[dict[str, Any]] = []
        kept_sources: list[Source] = []
        for item, source in zip(selected, sources, strict=True):
            candidate = json.dumps(
                [*kept, item],
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            if len(candidate.encode("utf-8")) > output_limit:
                truncated = True
                break
            kept.append(item)
            kept_sources.append(source)
        return ToolResult(
            call_id,
            json.dumps(kept, ensure_ascii=False, separators=(",", ":"), default=str),
            tuple(kept_sources),
            truncated,
        )

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Retrieve records and convert backend errors to safe domain errors.

        Parameters
        ----------
        call : ToolCall
            Vector query and optional result limit.
        context : OperationContext
            Timeout and output-size constraints.

        Returns
        -------
        ToolResult
            Bounded matching records and source references.

        Raises
        ------
        ContractError
            For invalid input, timeout, or vector-store failures.
        """
        vector, limit = self._validate(call)
        output_limit = max(0, context.output_limit_bytes)
        try:
            records = await asyncio.wait_for(
                asyncio.to_thread(self._search, vector, limit),
                timeout=max(0.01, context.timeout_seconds),
            )
        except TimeoutError:
            raise ContractError(
                ErrorCode.TIMEOUT, "Vector retrieval timed out.", transient=True
            ) from None
        except ImportError as exc:
            raise ContractError(ErrorCode.UNAVAILABLE, str(exc)) from None
        except Exception as exc:
            raise _vector_error(exc) from None
        return self._result(call.id, records, limit, output_limit)

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check that the selected collection can be reached.

        Parameters
        ----------
        context : OperationContext
            Connection-test timeout.

        Returns
        -------
        ConnectionHealth
            Redacted availability result.
        """
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._health), timeout=context.timeout_seconds
            )
        except ImportError as exc:
            return ConnectionHealth(False, str(exc), ErrorCode.UNAVAILABLE)
        except TimeoutError:
            return ConnectionHealth(
                False, "Vector store connection timed out.", ErrorCode.TIMEOUT
            )
        except Exception as exc:
            failure = _vector_error(exc)
            return ConnectionHealth(False, str(failure), failure.code)
        return ConnectionHealth(True, "Vector store connection is available.")

    def _search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        """Query the configured backend; implemented by each vendor adapter."""
        raise NotImplementedError

    def _health(self) -> None:
        """Check backend connectivity; implemented by each vendor adapter."""
        raise NotImplementedError


class QdrantTool(_VectorTool):
    name = "vector.qdrant.query"

    def __init__(
        self, collection: str, client: Any, *, max_chunks: int = MAX_CHUNKS
    ) -> None:
        """Configure a Qdrant collection client.

        Parameters
        ----------
        collection : str
            Qdrant collection name.
        client : Any
            Configured Qdrant client instance.
        max_chunks : int, optional
            Maximum records returned by one query.
        """
        super().__init__(collection, max_chunks=max_chunks)
        self.client = client

    def _search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        """Search Qdrant and normalize its point payloads.

        Parameters
        ----------
        vector : list of float
            Query embedding.
        limit : int
            Maximum number of points.

        Returns
        -------
        list of dict
            Records in the common vector adapter format.
        """
        if hasattr(self.client, "query_points"):
            result = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            points = result.points
        else:
            points = self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=limit,
                with_payload=True,
            )
        return [
            {
                "id": point.id,
                "text": (point.payload or {}).get("text", ""),
                "metadata": point.payload or {},
            }
            for point in points
        ]

    def _health(self) -> None:
        """Fetch collection metadata to verify Qdrant connectivity."""
        self.client.get_collection(self.collection)


class ChromaTool(_VectorTool):
    name = "vector.chroma.query"

    def __init__(
        self, collection: str, client: Any, *, max_chunks: int = MAX_CHUNKS
    ) -> None:
        """Configure a Chroma collection client.

        Parameters
        ----------
        collection : str
            Chroma collection name.
        client : Any
            Configured Chroma client instance.
        max_chunks : int, optional
            Maximum records returned by one query.
        """
        super().__init__(collection, max_chunks=max_chunks)
        self.client = client

    def _collection(self):
        """Return the selected Chroma collection.

        Returns
        -------
        Any
            Chroma collection handle.
        """
        return self.client.get_collection(self.collection)

    def _search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        """Search Chroma and normalize its first query result.

        Parameters
        ----------
        vector : list of float
            Query embedding.
        limit : int
            Maximum number of records.

        Returns
        -------
        list of dict
            Records in the common vector adapter format.
        """
        result = self._collection().query(
            query_embeddings=[vector],
            n_results=limit,
            include=["documents", "metadatas"],
        )
        records = []
        for index, item_id in enumerate(result.get("ids", [[]])[0]):
            records.append(
                {
                    "id": item_id,
                    "text": (result.get("documents") or [[]])[0][index] or "",
                    "metadata": (result.get("metadatas") or [[]])[0][index] or {},
                }
            )
        return records

    def _health(self) -> None:
        """Count collection records to verify Chroma connectivity."""
        self._collection().count()


class MilvusTool(_VectorTool):
    name = "vector.milvus.query"

    def __init__(
        self, collection: str, client: Any, *, max_chunks: int = MAX_CHUNKS
    ) -> None:
        """Configure a Milvus collection client.

        Parameters
        ----------
        collection : str
            Milvus collection name.
        client : Any
            Configured Milvus client instance.
        max_chunks : int, optional
            Maximum records returned by one query.
        """
        super().__init__(collection, max_chunks=max_chunks)
        self.client = client

    def _search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        """Search Milvus and normalize hits and entity metadata.

        Parameters
        ----------
        vector : list of float
            Query embedding.
        limit : int
            Maximum number of hits.

        Returns
        -------
        list of dict
            Records in the common vector adapter format.
        """
        result = self.client.search(
            collection_name=self.collection,
            data=[vector],
            limit=limit,
            output_fields=["text", "metadata", "url", "title"],
        )
        records = []
        for hit in result[0] if result else []:
            entity = hit.get("entity", {})
            metadata = entity.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {"metadata": metadata}
            for key in ("url", "title"):
                if key in entity:
                    metadata[key] = entity[key]
            records.append(
                {
                    "id": hit.get("id", "unknown"),
                    "text": entity.get("text", ""),
                    "metadata": metadata,
                }
            )
        return records

    def _health(self) -> None:
        """Describe the collection to verify Milvus connectivity."""
        self.client.describe_collection(self.collection)


def _vector_error(error: Exception) -> ContractError:
    """Map vendor status information to a safe contract error.

    Parameters
    ----------
    error : Exception
        Backend exception to classify.

    Returns
    -------
    ContractError
        Redacted error with a stable domain code.
    """
    status = getattr(error, "status_code", getattr(error, "status", None))
    if status in (401, 403):
        return ContractError(
            ErrorCode.AUTHENTICATION, "Vector store authentication failed."
        )
    if status == 404:
        return ContractError(ErrorCode.NOT_FOUND, "Vector collection was not found.")
    if status in (400, 422):
        return ContractError(ErrorCode.INVALID_INPUT, "Vector query is invalid.")
    return ContractError(
        ErrorCode.UNAVAILABLE,
        "Vector store is unavailable.",
        transient=status is None or isinstance(status, int) and status >= 500,
    )
