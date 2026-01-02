#!/usr/bin/env python3
"""
Migration script to fix escaped quotes in existing highlights.

This script unescapes Lua escape sequences that were incorrectly stored in the database.
Run with: docker compose exec web python3 scripts/fix_escaped_quotes.py
"""

import os
import sys

# Add parent directory to path so we can import the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Highlight, Note, Book


def unescape_lua_string(s: str) -> str:
    """Unescape Lua string escape sequences."""
    if not s:
        return s
    # Replace escape sequences in order from most specific to least
    s = s.replace(r"\\", "\x00")  # Temporarily replace \\ with placeholder
    s = s.replace(r"\"", '"')
    s = s.replace(r"\'", "'")
    s = s.replace(r"\n", "\n")
    s = s.replace(r"\r", "\r")
    s = s.replace(r"\t", "\t")
    s = s.replace("\x00", "\\")  # Restore actual backslashes
    return s


def main():
    app = create_app()
    with app.app_context():
        print("Fixing escaped quotes in highlights...")

        # Fix highlights
        highlights = Highlight.query.filter(
            (Highlight.text.like('%\\\\"%'))
            | (Highlight.text.like("%\\\\'%"))
            | (Highlight.text.like("%\\\\n%"))
            | (Highlight.text.like("%\\\\t%"))
        ).all()

        print(f"Found {len(highlights)} highlights with escape sequences")

        for h in highlights:
            old_text = h.text
            h.text = unescape_lua_string(h.text)
            if h.text != old_text:
                print(
                    f"  Fixed highlight {h.id}: {old_text[:50]}... -> {h.text[:50]}..."
                )

        # Fix notes
        notes = Note.query.filter(
            (Note.text.like('%\\\\"%'))
            | (Note.text.like("%\\\\'%"))
            | (Note.text.like("%\\\\n%"))
            | (Note.text.like("%\\\\t%"))
        ).all()

        print(f"Found {len(notes)} notes with escape sequences")

        for n in notes:
            old_text = n.text
            n.text = unescape_lua_string(n.text)
            if n.text != old_text:
                print(f"  Fixed note {n.id}: {old_text[:50]}... -> {n.text[:50]}...")

        # Fix book titles and authors
        books = Book.query.filter(
            (Book.raw_title.like('%\\\\"%'))
            | (Book.clean_title.like('%\\\\"%'))
            | (Book.raw_authors.like('%\\\\"%'))
            | (Book.clean_authors.like('%\\\\"%'))
        ).all()

        print(f"Found {len(books)} books with escape sequences")

        for b in books:
            if b.raw_title:
                b.raw_title = unescape_lua_string(b.raw_title)
            if b.clean_title:
                b.clean_title = unescape_lua_string(b.clean_title)
            if b.raw_authors:
                b.raw_authors = unescape_lua_string(b.raw_authors)
            if b.clean_authors:
                b.clean_authors = unescape_lua_string(b.clean_authors)

        # Commit all changes
        db.session.commit()
        print(
            f"\nFixed {len(highlights)} highlights, {len(notes)} notes, and {len(books)} books"
        )
        print("Migration complete!")


if __name__ == "__main__":
    main()
