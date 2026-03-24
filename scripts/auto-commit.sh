#!/bin/bash

# Auto-commit script for Taiwan Stock Monitor
# Usage: ./scripts/auto-commit.sh "commit message"

set -e

# Check if commit message is provided
if [ -z "$1" ]; then
    echo "❌ Please provide a commit message"
    echo "Usage: ./scripts/auto-commit.sh 'Your commit message'"
    exit 1
fi

COMMIT_MSG="$1"

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "❌ Not in a git repository"
    exit 1
fi

echo "📝 Preparing to commit changes..."

# Check for changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "✅ Found changes to commit"
else
    echo "ℹ️  No changes to commit"
    exit 0
fi

# Add all changes
echo "📦 Adding all changes..."
git add .

# Show what will be committed
echo "📋 Changes to be committed:"
git status --short

# Create commit with Claude Code attribution
echo "💾 Creating commit..."
git commit -m "$(cat <<EOF
${COMMIT_MSG}

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Show the commit
echo "✅ Commit created successfully:"
git log --oneline -1

echo "🎉 Auto-commit completed!"