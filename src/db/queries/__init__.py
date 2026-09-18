from __future__ import annotations

from src.db.schemas import (
    AlbumSearchHit,
    AlbumCard,
    BreadcrumbItem,
    PaginatedAlbums,
    AlbumDetail,
    CategoryMenuRow,
)

from src.db.queries.helpers import (
    _clean_query,
    _first_letter,
    _attach_covers_stmt,
    _bulk_cover_ids,
)

from src.db.queries.search import (
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SEARCH_LIMIT,
    MIN_QUERY_LENGTH,
    SUGGEST_DEFAULT_LIMIT,
    SUGGEST_MIN_QUERY_LENGTH,
    SUGGEST_DEFAULT_THRESHOLD,
    search_albums,
    search_albums_suggest,
)

from src.db.queries.albums import (
    DEFAULT_PER_PAGE,
    get_album_detail,
    get_latest_albums,
    get_latest_albums_paginated,
    get_category_albums_paginated,
)

from src.db.queries.categories import (
    get_category_by_id,
    get_category_path,
    get_all_categories_with_counts,
)


__all__ = [
    # DTO / Schemas
    "AlbumSearchHit",
    "AlbumCard",
    "BreadcrumbItem",
    "PaginatedAlbums",
    "AlbumDetail",
    "CategoryMenuRow",
    # Constants
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_SEARCH_LIMIT",
    "MIN_QUERY_LENGTH",
    "DEFAULT_PER_PAGE",
    "SUGGEST_DEFAULT_LIMIT",
    "SUGGEST_MIN_QUERY_LENGTH",
    "SUGGEST_DEFAULT_THRESHOLD",
    # Helpers
    "_clean_query",
    "_first_letter",
    "_attach_covers_stmt",
    "_bulk_cover_ids",
    # Search
    "search_albums",
    "search_albums_suggest",
    # Albums
    "get_album_detail",
    "get_latest_albums",
    "get_latest_albums_paginated",
    "get_category_albums_paginated",
    # Categories
    "get_category_by_id",
    "get_category_path",
    "get_all_categories_with_counts",
]
