#!/bin/bash
set -e

# If directories are passed as arguments, use them.
# Otherwise process the entire repo.
if [ "$#" -gt 0 ]; then
  TARGET_DIRS=("$@")
else
  TARGET_DIRS=(".")
fi

echo "Directories to process:"
printf " - %s\n" "${TARGET_DIRS[@]}"

generate_index() {
  local dir="$1"
  local index="$dir/index.html"

  # Skip .git and .github
  if [[ "$dir" == *"/.git"* ]] || [[ "$dir" == *"/.github"* ]]; then
    return
  fi

  echo " → Generating $index"

  {
    echo "<html><body><h2>Index of $dir</h2><ul>"

    for f in "$dir"/*; do
      [[ -e "$f" ]] || continue
      [[ "$f" == "$index" ]] && continue

      fname=$(basename "$f")
      echo "<li><a href=\"./$fname\">$fname</a></li>"
    done

    echo "</ul></body></html>"
  } > "$index"
}

# Walk every target directory and subdirectory
for base in "${TARGET_DIRS[@]}"; do
  find "$base" -type d | while read dir; do
    generate_index "$dir"
  done
done
