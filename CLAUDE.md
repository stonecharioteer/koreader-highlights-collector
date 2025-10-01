# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KoReader Highlights Collector - A Python tool that collects and aggregates highlights from KoReader e-reader devices synced via Syncthing.

## Architecture

The project consists of a single Python script (`collect_highlights.py`) that:

1. **Scans** multiple device folders in `~/syncthing/ebooks-highlights/`
2. **Parses** KoReader Lua metadata files (`metadata.epub.lua`, `metadata.pdf.lua`)
3. **Extracts** highlights with metadata (text, chapter, page number, datetime, device ID)
4. **Aggregates** highlights grouped by book
5. **Exports** to a single JSON file (`highlights.json`)

### Key Components

- `LuaTableParser`: Custom parser for KoReader's Lua metadata format
  - `parse_file()`: Main entry point for parsing Lua files
  - `_extract_field_value()`: Brace-matching algorithm to extract nested Lua table values
  - `_parse_annotations()`: Extracts individual highlight entries
  - `_parse_doc_props()`: Extracts book metadata (title, author, etc.)

- `HighlightsCollector`: Main orchestrator
  - `collect()`: Scans all device folders and processes metadata files
  - `_process_metadata_file()`: Processes a single metadata file
  - `export_json()`: Outputs aggregated data to JSON

### File Structure

- KoReader creates `.sdr` folders alongside ebooks containing `metadata.{epub|pdf}.lua` files
- Each metadata file contains:
  - `annotations[]`: Array of highlights with text, datetime, chapter, page number
  - `doc_props{}`: Book metadata (title, authors, identifiers, language)
  - `partial_md5_checksum`: Unique book identifier

## Usage

```bash
# Run with defaults (~/syncthing/ebooks-highlights -> highlights.json)
python3 collect_highlights.py

# Custom paths
python3 collect_highlights.py --base-path /path/to/highlights --output /path/to/output.json
```

## Dependencies

Python 3.x with standard library only (no external packages required).

## Notes

- The parser uses a custom brace-matching algorithm to handle nested Lua table structures
- Books are identified by `partial_md5_checksum` to merge highlights from same book across devices
- Device ID is extracted from the folder name (e.g., `boox-palma`, `s24u`)
- Designed to be run as a cron job for periodic collection
