# Contributing to CrowdVision

Thank you for your interest in contributing to CrowdVision and the AI Crowd Management Agent. We welcome contributions from developers, machine learning engineers, and computer vision researchers.

## Code of Conduct

All contributors are expected to uphold a professional, respectful, and inclusive environment. Harassment or discriminatory behavior will not be tolerated.

## Development Setup

### Prerequisites
- Python 3.10+ (tested up to 3.14)
- Node.js 18+ and npm
- OpenCV system libraries (e.g. `libgl1-mesa-glx` on Linux)

### Backend & AI Agent Setup
```bash
# Set up a Python virtual environment
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Linux/macOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Running the Automated Test Suite

Before submitting any Pull Request, ensure that all test suites pass completely:

```bash
# Run backend and security tests
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; $env:PYTHONPATH="backend"; python -m pytest -p pytest_asyncio.plugin backend/tests/ -v

# Run AI agent unit, integration, and benchmark tests
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; $env:PYTHONPATH="ai_agent"; python -m pytest -p pytest_asyncio.plugin ai_agent/tests/ -v

# Build frontend to verify TypeScript types
cd frontend
npm run build
```

## Contribution Workflow

1. **Fork the Repository**: Create your feature branch (`git checkout -b feature/your-feature-name`).
2. **Follow Coding Standards**:
   - Write clean, type-annotated Python code following PEP 8.
   - Use parameterized SQLAlchemy queries to prevent injection.
   - Never commit API keys, personal footage, or model weight binaries.
3. **Write Tests**: Add corresponding unit or integration tests for any new features or bug fixes under `backend/tests/` or `ai_agent/tests/`.
4. **Submit a Pull Request**: Provide a clear description of the problem solved, testing steps verified, and any architectural considerations.
