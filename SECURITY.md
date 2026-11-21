# Security Policy

The CrowdVision team takes the security of crowd monitoring systems and user infrastructure seriously. Crowd control environments involve critical public safety operations; our software is built with defense-in-depth principles.

## Supported Versions

Only the latest active development versions receive security updates and patches:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in CrowdVision or the AI Crowd Management Agent:

1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via **GitHub Security Advisories** on this repository (under the "Security" tab -> "Report a vulnerability").
3. Alternatively, email the maintainers at **security@crowdvision.io** with:
   - A detailed summary of the vulnerability.
   - Proof of Concept (PoC) scripts or reproduction steps.
   - Potential impact assessment.
   - Any recommended remediation steps.

### Our Commitment
- We will acknowledge receipt of your vulnerability report within **48 hours**.
- We will provide a triage assessment and target patch timeline within **7 days**.
- Once a fix is verified, we will coordinate public disclosure and credit the reporter.

## Core Security Architectures in CrowdVision

- **Zero Untrusted Code Execution**: Uploaded video files, single frames, and venue floorplans are strictly validated for MIME type, file extensions, and decoded via OpenCV memory buffers. File systems enforce randomized UUID naming and sanitize against path traversal (`../`).
- **Resource Exhaustion Defense (DoS Mitigation)**:
  - Video uploads stream in chunks and enforce strict size limits (`MAX_UPLOAD_SIZE_MB`, default 500 MB).
  - OpenCV video decode verifies resolution limits (`MAX_VIDEO_DIMENSION`, default 4096px) and maximum duration limits (`MAX_VIDEO_DURATION_SECONDS`, default 14,400s / 4 hours).
- **Privacy by Design**:
  - LLMs (e.g., Gemini, OpenAI, Claude) **never** receive raw video streams, personal facial features, or biometric recordings.
  - LLMs receive structured analytical telemetry exclusively (counts, densities, flow vectors, and zone occupancy numbers).
- **Offline & Air-Gapped Resiliency**:
  - If third-party AI APIs become unreachable or are disabled, the system gracefully falls back to deterministic rule-based analysis without interrupting real-time crowd alerts.
- **SQL Injection Prevention**:
  - All database interactions utilize SQLAlchemy async ORM with parameterized queries. Raw SQL string formatting is strictly prohibited.
