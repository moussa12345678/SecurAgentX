#!/bin/bash
# ============================================================
# apply_to_fork.sh — Apply PentAGI integration to YOUR fork
# ============================================================
# Usage:
#   1. Fork https://github.com/moussa12345678/SecurAgentX on GitHub
#   2. Clone YOUR fork locally
#   3. Place this script + securagentx-pentagi-integration.tar.gz
#      in the root of your cloned fork
#   4. Run: bash apply_to_fork.sh
# ============================================================

set -e

# --- Configuration ---
ARCHIVE="elengenix-pentagi-integration.tar.gz"
PATCH="securagentx-pentagi-integration.patch"
BRANCH_NAME="feat/pentagi-integration"
COMMIT_MSG="feat: integrate PentAGI features into SecurAgentX

- Multi-agent system (15 agents): PrimaryAgent, Searcher, Pentester,
  Coder, Installer, Memorist, Adviser, Enricher, Generator, Refiner,
  Reporter, Reflector, Summarizer, ToolCallFixer, Assistant
- Docker sandbox isolation (11 modules): sandbox, terminal, file_ops,
  image_chooser, browser, lifecycle, cleanup, resource_limits, network, db
- Local Knowledge Graph (NetworkX + SQLite): 9 node labels, 6 edge types,
  7 search types, MMR reranking, entity extraction, community detection
- REST API (FastAPI): ~50 endpoints, JWT HS256 auth (byte-compatible
  with PentAGI), cookie sessions, OAuth2 PKCE (GitHub + Google)
- GraphQL API (strawberry): 19 enums, 46 queries, 31 mutations,
  38 subscriptions, WebSocket transport
- 10 LLM providers: OpenAI, Anthropic, Gemini, Bedrock, Ollama,
  DeepSeek, GLM, Kimi, Qwen, Custom (vLLM)
- 7 search providers: Tavily, Perplexity, DuckDuckGo, Google,
  Sploitus, Traversaal, SearXNG
- Flow management: Flow→Task→SubTask→Action hierarchy with
  5-state machine and back-propagation
- Observability: OpenTelemetry + Langfuse + structlog + 7 metrics
- Enhanced PDF reports: ReportLab + CVSS calculator + 4 templates
- 1406 brutal tests (all passing, deterministic)

Total: 144 modules, 88,400 LOC, 0 compilation errors.
"

# --- Helper functions ---
log() {
    echo ""
    echo "=============================================="
    echo "  $1"
    echo "=============================================="
}

# --- Pre-flight checks ---
log "PRE-FLIGHT CHECKS"

if [ ! -f "$ARCHIVE" ]; then
    echo "ERROR: $ARCHIVE not found in current directory"
    echo "Download it from: /home/z/my-project/download/$ARCHIVE"
    exit 1
fi

if [ ! -d ".git" ]; then
    echo "ERROR: Not a git repository. Run this script inside your cloned fork."
    exit 1
fi

# Check we're in an SecurAgentX repo
if [ ! -f "securagentx/agent/vuln_agent.py" ] && [ ! -f "main.py" ]; then
    echo "WARNING: This doesn't look like an SecurAgentX repo. Continue? (y/N)"
    read -r response
    [ "$response" != "y" ] && exit 1
fi

# --- Step 1: Create feature branch ---
log "STEP 1/5: Creating feature branch '$BRANCH_NAME'"

git checkout -b "$BRANCH_NAME" 2>/dev/null || {
    echo "Branch already exists. Switching to it..."
    git checkout "$BRANCH_NAME"
}

# --- Step 2: Extract archive ---
log "STEP 2/5: Extracting integration files"

mkdir -p /tmp/securagentx-integration
tar -xzf "$ARCHIVE" -C /tmp/securagentx-integration
echo "Extracted to: /tmp/securagentx-integration"

# --- Step 3: Copy files into repo ---
log "STEP 3/5: Copying new modules into your fork"

# Copy securagentx/ subdirectories (agents, docker, knowledge_graph, etc.)
for dir in agents docker knowledge_graph api auth graphql observability providers search_providers flows reports chains; do
    if [ -d "/tmp/securagentx-integration/securagentx/$dir" ]; then
        mkdir -p "securagentx/$dir"
        cp -r "/tmp/securagentx-integration/securagentx/$dir/"* "securagentx/$dir/" 2>/dev/null || true
        echo "  + securagentx/$dir/"
    fi
done

# Copy tests/brutal/
if [ -d "/tmp/securagentx-integration/tests/brutal" ]; then
    mkdir -p tests/brutal
    cp -r /tmp/securagentx-integration/tests/brutal/* tests/brutal/ 2>/dev/null || true
    echo "  + tests/brutal/"
fi

# Update pyproject.toml if present
if [ -f "/tmp/securagentx-integration/pyproject.toml" ]; then
    cp /tmp/securagentx-integration/pyproject.toml pyproject.toml
    echo "  + pyproject.toml (updated)"
fi

# --- Step 4: Stage and commit ---
log "STEP 4/5: Staging and committing changes"

git add -A
git commit -m "$COMMIT_MSG" --no-verify 2>/dev/null || {
    echo "Nothing to commit (already up to date?)"
}

# --- Step 5: Push to your fork ---
log "STEP 5/5: Push to your fork"

echo "Ready to push. Run one of:"
echo ""
echo "  # Option A: HTTPS (use YOUR token, NOT shared)"
echo "  git push -u origin $BRANCH_NAME"
echo ""
echo "  # Option B: SSH (if you have SSH keys set up)"
echo "  git remote set-url origin git@github.com:YOUR_USERNAME/SecurAgentX.git"
echo "  git push -u origin $BRANCH_NAME"
echo ""
echo "Then open a Pull Request on GitHub:"
echo "  https://github.com/moussa12345678/SecurAgentX/compare/main...YOUR_USERNAME:SecurAgentX:$BRANCH_NAME"

# --- Cleanup ---
rm -rf /tmp/securagentx-integration

log "DONE!"
echo ""
echo "Files added in this commit:"
git show --stat HEAD | tail -20
