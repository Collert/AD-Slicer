#!/bin/bash
echo "Resolving symlinks..."

cd slicer || exit 1

find . -type l | while read link; do
    target=$(readlink "$link")

    # Print what we're resolving
    echo "Resolving $link -> $target"

    # Skip dangerous or recursive symlinks
    if [[ "$target" == ".." || "$target" == "../" || "$target" == "." ]]; then
        echo "⚠️ Skipping $link (would copy into itself)"
        continue
    fi

    # Resolve full target path
    full_target=$(realpath "$link" 2>/dev/null)
    if [[ ! -e "$full_target" ]]; then
        echo "❌ Skipping $link (target '$target' not found)"
        continue
    fi

    # Replace the symlink with real file or directory
    rm "$link"
    if [[ -d "$full_target" ]]; then
        cp -r "$full_target" "$link"
    else
        cp "$full_target" "$link"
    fi
done
