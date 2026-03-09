#!/usr/bin/env bash
# HIVE Engine -- Git initialization script
# Usage: bash scripts/git_init.sh [repo-name]

set -euo pipefail

REPO_NAME="${1:-hive-engine}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== HIVE Engine Git Init ==="

# Initialize git if not already
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
else
    echo "Git already initialized."
fi

# Create .gitignore if it doesn't exist
if [ ! -f ".gitignore" ]; then
    echo "Creating .gitignore..."
    cat > .gitignore << 'EOF'
.env
.hive/
edge_build/
__pycache__/
*.pyc
.DS_Store
*.db
EOF
fi

# Initial commit
echo "Creating initial commit..."
git add -A
git commit -m "Initial commit: HIVE Engine scaffold

- 8 AI personas (Forge, Oracle, Sentinel, Debug, Muse, Coda, Aegis, Apis)
- LiteLLM model routing with 3-tier ladder
- SQLite + HNSW memory system
- MCP server with 15 tools
- CLI with full command set
- CI/CD pipeline
- Edge build system"

# Create GitHub repo if gh is available
if command -v gh &> /dev/null; then
    echo "Creating GitHub repository: $REPO_NAME"
    gh repo create "$REPO_NAME" --private --source=. --remote=origin --push
    echo "Pushed to GitHub: $REPO_NAME"
else
    echo "gh CLI not found. Skipping GitHub repo creation."
    echo "Install gh: https://cli.github.com/"
    echo "Then run: gh repo create $REPO_NAME --private --source=. --remote=origin --push"
fi

echo ""
echo "=== Done ==="
echo "Repository initialized at: $PROJECT_ROOT"
