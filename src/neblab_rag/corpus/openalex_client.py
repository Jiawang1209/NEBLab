# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Thin wrapper over pyalex with our DTO.

OpenAlex returns abstracts as an inverted index (``{word: [positions]}``)
rather than plain text — we reconstruct the original ordering here.

Setting ``pyalex.config.email`` is a process-global mutation; instantiating
``OpenAlexClient`` more than once with different emails will race. For v1
we always build a single client per ingestion run, so this is safe.
"""

from collections.abc import Iterator

import pyalex
from pyalex import Works
from pydantic import BaseModel


class OpenAlexRecord(BaseModel):
    openalex_id: str
    doi: str | None
    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    language: str | None
    is_oa: bool
    cited_by_count: int
    abstract: str | None


def _restore_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexClient:
    def __init__(self, email: str):
        pyalex.config.email = email

    def search_by_keywords(
        self,
        *,
        keywords: list[str],
        language: str | None = None,
        max_results: int = 1000,
        per_page: int = 100,
    ) -> Iterator[OpenAlexRecord]:
        query = " OR ".join(f'"{k}"' for k in keywords)
        works = Works().search(query)
        if language:
            works = works.filter(language=language)

        count = 0
        for page in works.paginate(per_page=per_page, n_max=max_results):
            for w in page:
                if count >= max_results:
                    return
                # OpenAlex returns nested objects that may be null even when
                # the key is present, so we cannot rely on dict.get default.
                # Use `or {}` to coerce null → empty-dict at every hop.
                loc = w.get("primary_location") or {}
                src = loc.get("source") or {}
                oa = w.get("open_access") or {}
                authorships = w.get("authorships") or []
                yield OpenAlexRecord(
                    openalex_id=w["id"].rsplit("/", 1)[-1],
                    doi=(w.get("doi") or "").removeprefix("https://doi.org/") or None,
                    title=w.get("title") or "",
                    authors=[
                        name
                        for a in authorships
                        if (name := (a.get("author") or {}).get("display_name"))
                    ],
                    venue=src.get("display_name"),
                    year=w.get("publication_year"),
                    language=w.get("language"),
                    is_oa=bool(oa.get("is_oa") or False),
                    cited_by_count=w.get("cited_by_count") or 0,
                    abstract=_restore_abstract(w.get("abstract_inverted_index")),
                )
                count += 1
