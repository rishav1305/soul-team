#!/bin/bash
# inbox-archive.sh — Archive inbox files older than 7 days
#
# Scans ~/soul-roles/shared/inbox/*/ for .md files older than 7 days.
# Moves them to an archive/ subdirectory within each agent's inbox.
# Designed for crontab: 0 4 * * *
#
# Token optimization: keeps agent startup fast by reducing inbox scan size.

set -euo pipefail

INBOX_ROOT="$HOME/soul-roles/shared/inbox"
AGE_DAYS=7
ARCHIVED=0
SKIPPED=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Exit gracefully if inbox root doesn't exist
if [ ! -d "$INBOX_ROOT" ]; then
    log "Inbox root not found: $INBOX_ROOT — nothing to archive."
    exit 0
fi

# Process each agent directory
for agent_dir in "$INBOX_ROOT"/*/; do
    # Skip if not a directory (handles empty glob)
    [ -d "$agent_dir" ] || continue

    agent_name=$(basename "$agent_dir")

    # Find .md files older than AGE_DAYS (exclude archive/ subdirectory)
    while IFS= read -r -d '' file; do
        # Create archive dir if needed
        archive_dir="${agent_dir}archive"
        mkdir -p "$archive_dir"

        filename=$(basename "$file")
        dest="${archive_dir}/${filename}"

        # Handle filename collisions
        if [ -f "$dest" ]; then
            dest="${archive_dir}/$(date +%s)-${filename}"
        fi

        mv "$file" "$dest"
        log "Archived: ${agent_name}/${filename}"
        ARCHIVED=$((ARCHIVED + 1))
    done < <(find "$agent_dir" -maxdepth 1 -name "*.md" -type f -mtime +"$AGE_DAYS" -print0 2>/dev/null)
done

if [ "$ARCHIVED" -gt 0 ]; then
    log "Done. Archived $ARCHIVED file(s)."
else
    log "No files older than ${AGE_DAYS} days found."
fi
