from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, ForeignKey, Text, Boolean, Integer, DateTime, func, Table, Column, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, DeclarativeBase):
    pass

album_category_association = Table(
    "album_category_association",
    Base.metadata,
    Column(
        "album_id",
        Integer,
        ForeignKey("albums.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    yupoo_path: Mapped[str] = mapped_column(String(512), unique=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    subcategories: Mapped[List["Category"]] = relationship(
        "Category",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Optional["Category"]] = relationship(
        "Category",
        back_populates="subcategories",
        remote_side=[id],
    )

    albums: Mapped[List["Album"]] = relationship(
        "Album",
        secondary=album_category_association,
        back_populates="categories",
    )

class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        Index(
            "idx_album_title_trgm",
            "clean_title",
            postgresql_using="gin",
            postgresql_ops={"clean_title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    original_title: Mapped[str] = mapped_column(Text)
    clean_title: Mapped[str] = mapped_column(Text)

    yupoo_url: Mapped[str] = mapped_column(String(512), unique=True)
    weidian_url: Mapped[Optional[str]] = mapped_column(Text)
    cover_url: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    categories: Mapped[List["Category"]] = relationship(
        "Category",
        secondary=album_category_association,
        back_populates="albums",
    )
    images: Mapped[List["Image"]] = relationship(
        "Image",
        back_populates="album",
        cascade="all, delete-orphan",
    )

class Image(Base):
    __tablename__ = "images"
    __table_args__ = (
        UniqueConstraint(
            "album_id",
            "yupoo_origin_url",
            name="uq_images_album_origin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"))

    yupoo_origin_url: Mapped[str] = mapped_column(Text)
    tg_file_id: Mapped[Optional[str]] = mapped_column(String(255))

    position: Mapped[int] = mapped_column(default=0)
    is_cover: Mapped[bool] = mapped_column(default=False)

    album: Mapped["Album"] = relationship("Album", back_populates="images")
