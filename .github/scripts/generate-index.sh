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

  # Skip .git and .github (both at root and nested)
  if [[ "$dir" == .git* ]] || [[ "$dir" == .github* ]] || [[ "$dir" == *"/.git"* ]] || [[ "$dir" == *"/.github"* ]]; then
    return
  fi

  echo " → Generating $index"

  # Collect files and extract dates
  declare -a files_list

  for f in "$dir"/*; do
    [[ -e "$f" ]] || continue
    [[ "$f" == "$index" ]] && continue

    fname=$(basename "$f")
    [[ "$fname" == favicon.* ]] && continue

    # Try to extract date in YYYY-MM-DD format from filename
    if [[ "$fname" =~ ([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
      year="${BASH_REMATCH[1]}"
      month="${BASH_REMATCH[2]}"
      day="${BASH_REMATCH[3]}"

      # Convert month number to name
      case "$month" in
        01) month_name="January" ;;
        02) month_name="February" ;;
        03) month_name="March" ;;
        04) month_name="April" ;;
        05) month_name="May" ;;
        06) month_name="June" ;;
        07) month_name="July" ;;
        08) month_name="August" ;;
        09) month_name="September" ;;
        10) month_name="October" ;;
        11) month_name="November" ;;
        12) month_name="December" ;;
      esac

      month_key="$year-$month"
      month_label="$month_name $year"

      # Store file with its month key and full date for sorting
      files_list+=("$month_key|$year-$month-$day|$month_label|$fname")
    else
      # No date found, use a default group
      files_list+=("0000-00|0000-00-00|Other|$fname")
    fi
  done

  {
    echo "<html>"
    echo "<head>"
    echo '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">'
    echo '<meta http-equiv="Pragma" content="no-cache">'
    echo '<meta http-equiv="Expires" content="0">'
    echo "</head>"
    echo "<body><h2>Index of $dir</h2>"

    # Sort files by date (latest first), then group by month
    printf '%s\n' "${files_list[@]}" | sort -t'|' -k2 -r | {
      current_month=""
      while IFS='|' read -r month_key date month_label fname; do
        if [[ "$month_key" != "$current_month" ]]; then
          # Close previous month's list if any
          [[ -n "$current_month" ]] && echo "</ul>"

          # Start new month section
          echo "<h2>$month_label</h2>"
          echo "<ul>"
          current_month="$month_key"
        fi

        echo "<li><a href=\"./$fname\">$fname</a></li>"
      done

      # Close final list
      [[ -n "$current_month" ]] && echo "</ul>"
    }

    echo "</body></html>"
  } > "$index"
}

# Walk every target directory and subdirectory
for base in "${TARGET_DIRS[@]}"; do
  find "$base" -type d | while read dir; do
    generate_index "$dir"
  done
done
