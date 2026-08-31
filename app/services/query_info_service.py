"""Admin-curated, read-only named queries — run by any authenticated user via `name`.

Security model: the only thing a caller of `run()` ever supplies is the query's `name` — never
any SQL text or WHERE-clause fragment, so there's no injection surface at call time. All the
risk lives in what admins are allowed to *save* into `query`, which is why `create`/`update`
validate it's a single, standalone SELECT statement (via sqlparse, not a string blocklist —
blocklists are bypassable, a real SQL-aware parse of statement count/type isn't). This still
doesn't prevent an admin-authored SELECT from reading columns/tables a given caller "shouldn't"
see — that's an inherent trade-off of exposing execute-by-name to any authenticated user rather
than admins only, not something the SELECT-only check can catch.
"""

import uuid

import sqlparse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.query_info import QueryInfo
from app.repositories.query_info_repo import QueryInfoRepository
from app.schemas.query_info import QueryInfoCreateIn, QueryInfoUpdateIn, QueryResultPage


def _validate_select_only(query: str) -> str:
    cleaned = query.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    statements = [
        stmt for stmt in sqlparse.parse(cleaned) if stmt.token_first(skip_cm=True) is not None
    ]
    if len(statements) != 1:
        raise ValidationAppError(
            "Exactly one SQL statement is allowed (no semicolon-separated statements)."
        )
    if statements[0].get_type().upper() != "SELECT":
        raise ValidationAppError("Only SELECT statements are allowed.")
    return cleaned


class QueryInfoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.query_infos = QueryInfoRepository(session)

    async def list(self) -> list[QueryInfo]:
        return await self.query_infos.list_all()

    async def create(self, payload: QueryInfoCreateIn) -> QueryInfo:
        if await self.query_infos.get_by_name(payload.name) is not None:
            raise ConflictError(f"A query with name '{payload.name}' already exists.")

        query_info = QueryInfo(
            name=payload.name,
            query=_validate_select_only(payload.query),
            batch_size=payload.batch_size,
            is_active=payload.is_active,
        )
        self.query_infos.add(query_info)
        await self.session.flush()
        return query_info

    async def update(self, query_info_id: uuid.UUID, payload: QueryInfoUpdateIn) -> QueryInfo:
        query_info = await self.query_infos.get(query_info_id)
        if query_info is None:
            raise NotFoundError("Query not found.")

        data = payload.model_dump(exclude_unset=True)
        if "query" in data:
            data["query"] = _validate_select_only(data["query"])
        for field, value in data.items():
            setattr(query_info, field, value)

        await self.session.flush()
        return query_info

    async def delete(self, query_info_id: uuid.UUID) -> None:
        query_info = await self.query_infos.get(query_info_id)
        if query_info is None:
            raise NotFoundError("Query not found.")
        await self.query_infos.delete(query_info)
        await self.session.flush()

    async def run(self, name: str, *, page: int, page_size: int | None) -> QueryResultPage:
        query_info = await self.query_infos.get_by_name(name)
        if query_info is None or not query_info.is_active:
            raise NotFoundError(f"No query found for name '{name}'.")

        effective_page_size = (
            min(page_size, query_info.batch_size) if page_size else query_info.batch_size
        )
        offset = (max(page, 1) - 1) * effective_page_size

        # Wrapped as a subquery (on its own lines) rather than string-appending LIMIT/OFFSET
        # onto the stored text directly — robust regardless of the stored query's own
        # formatting, and a trailing line comment in it can only eat its own line, not the
        # closing paren below.
        #
        # noqa justification (S608 - possible SQL injection via string-built query): the
        # interpolated value is `query_info.query`, never caller input — it was already
        # validated as a single standalone SELECT statement by `_validate_select_only` at
        # save time (create/update, admin-only). The only caller-supplied values here are
        # `limit`/`offset`, and those are bound parameters, not interpolated into the string.
        wrapped = text(
            f"SELECT * FROM (\n{query_info.query}\n) AS query_info_subquery\n"  # noqa: S608
            "LIMIT :limit OFFSET :offset"
        )
        result = await self.session.execute(
            wrapped, {"limit": effective_page_size + 1, "offset": offset}
        )
        rows = [dict(row._mapping) for row in result]
        has_next = len(rows) > effective_page_size
        rows = rows[:effective_page_size]

        return QueryResultPage(
            items=rows, page=max(page, 1), page_size=effective_page_size, has_next=has_next
        )
