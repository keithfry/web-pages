#!/bin/bash
# Wrapper script for launchd — loads the user's shell environment
# so that python3 and any pip-installed packages (feedparser, etc.) are found.

# Source user profile to pick up PATH, pyenv, conda, etc.
source ~/.zprofile 2>/dev/null || source ~/.bash_profile 2>/dev/null || true

exec python3 "$(dirname "$0")/server.py"
