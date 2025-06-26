#!/bin/bash
echo "Resolving symlinks..."

# Go to slicer directory
cd slicer

# Find all symlinks and replace with real files/directories
find . -type l | while read link; do
    target=$(readlink "$link")
    echo "Resolving $link -> $target"
    rm "$link"
    cp -r "$target" "$link"
done
