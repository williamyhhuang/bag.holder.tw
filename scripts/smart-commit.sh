#!/bin/bash

# Smart commit script for Taiwan Stock Monitor
# Automatically detects changes and creates appropriate commit messages

set -e

echo "🔍 Taiwan Stock Monitor - Smart Commit"
echo "===================================="

# Function to detect change type
detect_change_type() {
    local changes=$(git diff --cached --name-status)

    if echo "$changes" | grep -q "^A.*\.py$"; then
        echo "feat"
    elif echo "$changes" | grep -q "^M.*fubon_client\.py$"; then
        echo "fix(api)"
    elif echo "$changes" | grep -q "^M.*requirements\.txt$"; then
        echo "deps"
    elif echo "$changes" | grep -q "^M.*docker.*\.yml$"; then
        echo "ci"
    elif echo "$changes" | grep -q "^M.*\.md$"; then
        echo "docs"
    elif echo "$changes" | grep -q "^M.*test.*\.py$"; then
        echo "test"
    elif echo "$changes" | grep -q "^M.*\.env"; then
        echo "config"
    else
        echo "update"
    fi
}

# Function to generate commit message
generate_commit_message() {
    local change_type=$1
    local changed_files=$(git diff --cached --name-only | head -5)
    local file_count=$(git diff --cached --name-only | wc -l | tr -d ' ')

    case $change_type in
        "feat")
            echo "✨ Add new feature components"
            ;;
        "fix(api)")
            echo "🔧 Update Fubon API client implementation"
            ;;
        "deps")
            echo "📦 Update project dependencies"
            ;;
        "ci")
            echo "🐳 Update Docker configuration"
            ;;
        "docs")
            echo "📚 Update documentation"
            ;;
        "test")
            echo "🧪 Update test suite"
            ;;
        "config")
            echo "⚙️ Update configuration settings"
            ;;
        *)
            if [ $file_count -eq 1 ]; then
                local filename=$(basename "$changed_files")
                echo "🔄 Update $filename"
            else
                echo "🔄 Update multiple files ($file_count files)"
            fi
            ;;
    esac
}

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "❌ Not in a git repository"
    exit 1
fi

# Check for unstaged changes and add them
if ! git diff-index --quiet HEAD --; then
    echo "📦 Adding unstaged changes..."
    git add .
fi

# Check if there are staged changes
if git diff-index --quiet --cached HEAD --; then
    echo "ℹ️  No changes to commit"
    exit 0
fi

# Detect change type and generate message
change_type=$(detect_change_type)
commit_message=$(generate_commit_message "$change_type")

echo "📋 Detected changes:"
git status --short

echo ""
echo "📝 Generated commit message: $commit_message"

# Ask for confirmation unless -y flag is provided
if [[ "$1" != "-y" ]]; then
    read -p "🤔 Proceed with this commit? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ -n $REPLY ]]; then
        echo "❌ Commit cancelled"
        exit 1
    fi
fi

# Create commit
echo "💾 Creating commit..."
git commit -m "$(cat <<EOF
${commit_message}

$(git diff --cached --name-only | head -10 | sed 's/^/- /')

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Show the commit
echo "✅ Commit created successfully:"
git log --oneline -1

echo "🎉 Smart commit completed!"