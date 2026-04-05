# ⭐ Trusted Sources Feature

## Overview
The Trusted Sources feature allows analysts to maintain a curated list of reliable dark web sources for each operation. Each source can be assigned a trust score (0.0-1.0) and a custom title.

## Features

### 1. **Trusted Sources Section** (Top of each operation)
- Located at the top of each operation's main view
- Displays all trusted sources sorted by trust score (highest first)
- Shows URL, title, and trust score for each source

### 2. **Add New Trusted Source**
- Expandable form to manually add sources
- Fields:
  - **Source URL**: The onion URL to trust
  - **Source Title**: Custom name (e.g., "Dark Web Forum", "Ransomware Marketplace")
  - **Trust Score**: 0.0 (untrusted) to 1.0 (fully trusted) - default is 0.5

### 3. **Edit Trusted Sources**
- **Title**: Click the title field to edit it immediately
- **Trust Score**: Use the slider to adjust the score from 0.0 to 1.0
- **Delete**: Click the trash icon to remove from trusted list

### 4. **Add to Trust Button** (Intelligence Feed)
- New "⭐ Add to Trust" button appears next to each scanned link
- Automatically adds the link to trusted sources with:
  - **Trust Score**: 0.0 (minimum trust by default)
  - **Title**: The link's original title
- User can then edit the score and title in the Trusted Sources section

## Database Schema

Trusted sources are stored as documents in Elasticsearch with:
```
{
  "type": "trusted_source",
  "thread_id": "<operation_id>",
  "url": "<onion_url>",
  "title": "<human_readable_name>",
  "trust_score": 0.0-1.0,
  "added_at": "<ISO_timestamp>"
}
```

## Database Functions

All functions are in `src/database/database.py`:

### `add_trusted_source(client, thread_id, url, title="No title", trust_score=0.0)`
Adds a new trusted source to an operation

### `get_trusted_sources(client, thread_id)`
Retrieves all trusted sources for an operation, sorted by trust score (descending)

### `update_trusted_source(client, source_id, title=None, trust_score=None)`
Updates the title and/or trust score of an existing trusted source

### `delete_trusted_source(client, source_id)`
Removes a trusted source from the list

## UI Components

### Trusted Sources Header Section
- Shows "⭐ Trusted Sources" heading with expandable form
- Displays each source in an organized table with editable fields
- Shows message if no sources exist yet

### Intelligence Feed Buttons
Layout changed from 4 columns to 5 columns:
1. **🕷 Deep Crawl** - Fetch full content
2. **⭐ Add to Trust** - Add to trusted list (NEW)
3. **🚫 Ban Local** - Ban from this operation
4. **🛑 Ban Global** - Ban from all operations
5. **View Raw Data** - Expander for full content

## Workflow Example

1. **Analyst runs "Scan & Attach"** to find new links
2. **Analyst finds a reliable source** and clicks "⭐ Add to Trust"
3. **Link automatically added** with trust_score=0.0 and original title
4. **Analyst navigates to Trusted Sources section** at top of page
5. **Analyst adjusts the trust score** to 0.8 (slider)
6. **Analyst renames** "No title" to "Known Ransomware Forum"
7. **Future analysis** can filter/prioritize links from trusted sources (if implemented)

## Implementation Notes

- Trust scores are clamped between 0.0 and 1.0
- All edits trigger real-time rerun of Streamlit app
- Trusted sources persist in Elasticsearch
- Each operation has independent trusted sources list
- Sorting by trust_score makes highest-trust sources appear first
