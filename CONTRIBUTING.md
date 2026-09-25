# Contributing to MCP AI Workforce

Thank you for your interest in contributing to MCP AI Workforce. We welcome contributions from developers worldwide to improve model orchestration, expand toolsets, and enhance security guardrails.

---

## Code of Conduct

This project adheres to professional standards of conduct. All participants are expected to communicate constructively, respectfully, and collaboratively.

---

## Development Setup

### Prerequisites

- Python 3.10, 3.11, or 3.12
- Git
- OpenRouter API key (optional for mocked unit tests; required for live integration)

### Local Environment Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/DevImperatore/mcp-ai-workforce.git
   cd mcp-ai-workforce
   ```

2. Create and activate a virtual environment:
   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Install the package in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Configure environment variables for local testing:
   ```bash
   cp .env.example .env
   # Edit .env with your OPENROUTER_API_KEY
   ```

---

## Testing Guidelines

All submissions must maintain 100% test coverage and pass our automated test suite.

### Running Tests

Execute the full pytest suite:

```bash
pytest -v
```

Before opening a pull request, ensure:
- All unit and integration tests pass without errors or warnings.
- New features include corresponding unit tests under `tests/`.
- Security guardrails in `src/guardrails.py` are strictly preserved or strengthened.

---

## Pull Request Process

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Commit changes using Conventional Commits:
   - `feat: add support for local Ollama endpoints`
   - `fix: handle edge case in path resolution on Windows UNC shares`
   - `docs: clarify Claude Desktop configuration parameters`
   - `test: add unit tests for agent loop error recovery`

3. Professional Style Guidelines:
   Documentation, commit messages, and source code comments must strictly avoid emojis.

4. Push your branch and open a Pull Request against `main`. Provide a clear description of the problem solved, changes made, and verification steps.

---

## Security Disclosures

If you discover a security vulnerability (such as a path jail bypass or credential exposure), please do not open a public issue. Report it directly via GitHub Security Advisories or contact the maintainer privately.
