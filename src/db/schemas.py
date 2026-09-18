from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from src.db.models import Album


@dataclass
class AlbumSearchHit:
    album: "Album"
    similarity: float
    cover_image_id: Optional[int] = None
    cover_tg_file_id: Optional[str] = None


@dataclass
class AlbumCard:
    album_id: int
    clean_title: str
    cover_image_id: Optional[int]


@dataclass
class BreadcrumbItem:
    id: Optional[int]
    name: str
    url: str


@dataclass
class PaginatedAlbums:
    items: list[AlbumCard]
    page: int
    per_page: int
    total: int
    total_pages: int
    has_prev: bool
    has_next: bool
    prev_url: Optional[str] = None
    next_url: Optional[str] = None


@dataclass
class AlbumDetail:
    album_id: int
    clean_title: str
    cover_image_id: Optional[int]
    images: List[int]
    breadcrumbs: List[BreadcrumbItem]


@dataclass
class CategoryMenuRow:
    id: int
    name: str
    first_letter: str
    album_count: int
    url: str


__all__ = [
    "AlbumSearchHit",
    "AlbumCard",
    "BreadcrumbItem",
    "PaginatedAlbums",
    "AlbumDetail",
    "CategoryMenuRow",
]
