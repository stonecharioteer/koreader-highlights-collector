#!/usr/bin/env python3
"""Migration: Add export_templates and export_jobs tables"""

from app import create_app, db


def main():
    app = create_app()
    with app.app_context():
        # Create tables
        from app.models import ExportTemplate, ExportJob
        db.create_all()

        # Add default template
        default = ExportTemplate.query.filter_by(is_default=True).first()
        if not default:
            default_template = ExportTemplate(
                name='Blog Post (Markdown)',
                is_default=True,
                template_content="""---
title: "Highlights from {{ book.clean_title or book.raw_title }}"
date: {{ current_date }}
tags:
  - book-highlights
  - reading
cover: cover.jpg
---

# Highlights from *{{ book.clean_title or book.raw_title }}*

{% if book.clean_authors or book.raw_authors %}
**Author**: {{ book.clean_authors or book.raw_authors }}
{% endif %}

{% if read_start and read_end %}
**Read**: {{ read_start }} — {{ read_end }}
{% endif %}

{% if book.description %}
## About the Book

{{ book.description }}
{% endif %}

## Selected Highlights

{% for highlight in highlights %}
### Highlight {{ loop.index }}

> {{ highlight.text }}

{% if highlight.chapter %}*— {{ highlight.chapter }}*{% endif %}
{% if highlight.page_number %}*Page {{ highlight.page_number }}*{% endif %}
{% if highlight.datetime %}*Highlighted on {{ highlight.datetime }}*{% endif %}

---

{% endfor %}

*Exported from KOllector on {{ current_timestamp }}*
"""
            )
            db.session.add(default_template)
            db.session.commit()
            print(f"✓ Created default template: {default_template.name}")
        else:
            print(f"✓ Default template already exists: {default.name}")


if __name__ == '__main__':
    main()
