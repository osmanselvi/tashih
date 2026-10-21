"""SQLAlchemy modelleri."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="extracted")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    analyzer_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    pages: Mapped[list[Page]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Page.number",
    )

    @property
    def pending_count(self) -> int:
        return sum(
            1
            for page in self.pages
            for sug in page.suggestions
            if sug.status == "pending"
        )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    original_text: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    has_text: Mapped[bool] = mapped_column(Boolean, default=True)
    # PDF sayfa puanları (sol üst orijin) ve hizalı sözcük kutuları (JSON)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    words: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="pages")
    suggestions: Mapped[list[Suggestion]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="Suggestion.start",
    )


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="spelling")
    original: Mapped[str] = mapped_column(Text)
    replacement: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # Düzeltmenin asıl PDF sayfasındaki konumu [x0, y0, x1, y1] (JSON)
    rect: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "ai" (kural/LLM) veya "manual" (yazar/musahhih işareti)
    source: Mapped[str] = mapped_column(String(16), default="ai")
    # Manuel işaretlerde düzeltmenin türü: delete|insert|replace|space|join
    mutation: Mapped[str | None] = mapped_column(String(16), nullable=True)

    page: Mapped[Page] = relationship(back_populates="suggestions")


class ChangeLog(Base):
    __tablename__ = "changelog"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[int | None] = mapped_column(
        ForeignKey("pages.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    old_text: Mapped[str] = mapped_column(Text, default="")
    new_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
