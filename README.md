# Wear & Wonder Automation

AI-assisted fashion content production workspace engineered for multi-look fashion videos, trend research, outfit coordination, master model identity fidelity, and video clip generation across Stages 1–5.

---

## 1. Project Overview

Wear & Wonder automates the preparation of cohesive fashion videos (such as jeans and top combinations, color harmonies, campus styling, formal workwear, and couples' coordination) following a strict, sequential approval workflow.

### Stages Implemented

1. **Stage 1 — Idea Studio & Topic Router:** Interprets natural-language fashion ideas into structured research briefs, classifying primary fashion topics (denim, color combinations, footwear, seasonal, suiting, etc.) with local and Gemini AI options.
2. **Stage 2 — Live Fashion Research:** Retrieves genuine external fashion references and publications via DuckDuckGo web search and curated authoritative fashion repositories. Verifies URL accessibility and categorizes verified factual claims vs. reported trends vs. AI styling hypotheses.
3. **Stage 3 — Outfit Proposals & 16-Dimension Validation:** Synthesizes structured outfit proposals evaluated against 16 distinct fashion dimensions (silhouette, fit, proportions, fabrics, color harmony, footwear, practicality, distinctness, etc.), calculates confidence scores, flags near-duplicates, and provides an outfit editor with cascade invalidation.
4. **Stage 4 — Image Prompts, Character Fidelity & Manual Handoff:** Generates traceable image prompts enforcing approved master character identity (e.g. `WW-CHAR-01`, `WW-CHAR-02`, `WW-CHAR-03`), links verified reference images, supports manual handoff / direct image asset upload, and provides per-image visual review and approval controls.
5. **Stage 5 — Video Prompts, Motion & Google Flow Handoff:** Prepares cinematic vertical video prompts (framing, subtle motion, camera movement, dialogue, speaker identity, lip-sync, negative constraints, and dual-model left/right staging), provides Google Flow manual handoff instructions, allows clip import, and renders inline video playback preview for per-clip approval.

---

## 2. Mandatory Approval Workflow & Gate Transitions

The pipeline enforces a strict sequential gatekeeper:

```
[IDEA INTAKE]
      ↓
[AI / LOCAL INTERPRETATION]
      ↓
[STAGE 2: LIVE FASHION RESEARCH]
      ↓  (Mandatory user review & approval of research sources)
[STAGE 3: OUTFIT PROPOSALS]
      ↓  (Mandatory per-outfit review & approval)
[STAGE 4: IMAGE PROMPTS & HANDOFF]
      ↓  (Mandatory visual review & per-image approval)
[STAGE 5: VIDEO PROMPTS & CLIP HANDOFF]
      ↓  (Mandatory per-clip playback review & approval)
[STAGE 6: READY FOR EDITING & ASSEMBLY]
```

### Cascade Invalidation Matrix
- **Editing an approved outfit** automatically invalidates downstream image and video assets for that outfit, returning them to `PENDING` approval.
- **Rejecting an image** blocks downstream video prompt and clip generation for that outfit.
- **Independent outfits retain their approved status**, minimizing rework.

---

## 3. Setup and Prerequisites

### System Requirements
- Windows 10/11
- Python 3.12+
- VS Code or preferred editor
- Git

### Virtual Environment Setup

```powershell
# Navigate to the repository root
cd c:\Users\Tejashwini\Documents\ww

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install / update dependencies
pip install -r requirements.txt   # or inspect installed packages via pip list
```

### Environment Configuration (`.env`)

Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

Ensure `.env` contains:
```ini
# Google Gemini API Key from Google AI Studio (Free Tier)
GEMINI_API_KEY=your_actual_gemini_api_key

# Default Gemini Model for Interactions API
GEMINI_MODEL=gemini-3.8-flash
```

> **Security Note:** `.env` is ignored by `.gitignore`. Never commit API keys or sensitive credentials to Git.

---

## 4. Running the Dashboard

Launch the Streamlit interactive dashboard:

```powershell
.\.venv\Scripts\streamlit run dashboard.py
```

Open your browser at `http://localhost:8501`.

### Dashboard Tabs
- **💡 Idea Studio:** Enter free-text ideas, select primary topic, run AI or Local review, adjust and save briefs.
- **🔎 Research:** Execute live web research, inspect verified URLs, review factual evidence vs. styling hypotheses, and approve research.
- **👗 Outfit Proposals:** Generate candidate outfits, inspect the 16-point validation breakdown, review near-duplicate checks, edit garment details, and approve looks.
- **📸 Image Studio:** Generate character-locked image prompts, copy prompts to Google Flow / Imagen / Midjourney, upload generated images, and approve images.
- **🎬 Video Studio:** Generate motion/dialogue video prompts, follow Google Flow handoff instructions, upload clips, preview playback, and approve clips.
- **👤 Master Models:** Inspect approved reference portraits (`WW-CHAR-01`, `WW-CHAR-02`, `WW-CHAR-03`), register new references, and manage approval status.
- **📊 Workflow Status:** Live stage matrix for the active brief, prerequisite tracker, and tamper-proof audit trail of all actions.

---

## 5. Running the Automated Test Suite

All tests use mocked external API calls to avoid consuming live quota or requiring internet connectivity:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Test Suite Structure
- `tests/test_topic_router.py`: Tests fashion topic classification, templates, and guidance.
- `tests/test_fashion_ai.py`: Tests Gemini Interactions API error handling (`401`, `404`, `429`, `503`, `504`), timeouts, and sanitization.
- `tests/test_idea_intake.py`: Tests local parsing rules, number word extraction, and brief creation.
- `tests/test_research.py`: Tests URL normalization, reachability verification, search providers, and source deduplication.
- `tests/test_outfit_validation.py`: Tests all 16 validation dimensions, near-duplicate detection, confidence scoring, and cascade invalidation.
- `tests/test_image_studio.py`: Tests master character profile checks, image prompt builder, and image handoff/import.
- `tests/test_video_studio.py`: Tests video prompt construction, dialogue scripts, dual-model staging, and clip approval.
- `tests/test_approval_workflow.py`: Tests global workflow gates, cascade invalidation matrix, and audit logging.
- `tests/test_brief_workflow.py`: End-to-end integration test walking through the complete Stages 1–5 pipeline.

---

## 6. Data & Asset Locations

- `data/research.json`: Master project briefs (backward compatible with all previous records).
- `data/research_sources.json`: External research sources and synthesis summaries.
- `data/outfits.json`: Structured outfit proposals, validation results, and review status.
- `data/image_assets.json`: Image generation prompts, reference links, and image status.
- `data/video_assets.json`: Video generation prompts, dialogue, clip paths, and approval status.
- `data/master_models.json`: Master model identity rules and reference image paths.
- `data/workflow_audit.json`: Complete audit log of every workflow state transition and user action.
- `assets/master_models/`: Approved master reference portraits (`WW-CHAR-01.png`, etc.).
- `assets/generated_images/`: Local storage for generated/imported outfit images.
- `assets/generated_videos/`: Local storage for generated/imported video clips.

---

## 7. Cost Considerations & Free-Tier Boundaries

- **Target Spending:** ₹0.00 additional cost.
- **Gemini Free Tier:** Used for idea interpretation and planning via the Interactions API (`gemini-3.8-flash`).
- **Web Research:** Uses open web queries via DuckDuckGo and curated fashion style repositories without requiring paid Search API subscriptions.
- **Image & Video Generation:** Because public APIs for Google Flow or Imagen may require paid cloud billing or lack public developer APIs, a robust **Manual Handoff Workflow** is implemented:
  - Exact structured prompts with start-frame references and negative constraints are prepared.
  - Step-by-step handoff instructions guide generation in available tools (Google Flow, Canva Pro Lite, etc.).
  - Output files are directly imported, tracked, previewed, and approved within the application.
  - No fake assets or simulated approvals are ever produced.

---

## 8. Troubleshooting

- **Gemini 504 / 503 / Timeout Errors:** The Interactions API client uses bounded retries and client-side timeouts. If Google AI Studio servers are temporarily congested, use the **Quick Local Review** button in Idea Studio.
- **Port In Use / Streamlit:** If Streamlit reports port 8501 is busy, specify `--server.port 8502`.
- **Missing Master Reference Image:** Ensure `assets/master_models/WW-CHAR-01.png` (or corresponding model) exists and has `approval_status: APPROVED` in the Master Models tab.
