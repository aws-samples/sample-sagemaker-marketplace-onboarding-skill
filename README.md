# SageMaker Marketplace Onboarding — an Agent Skill for Claude Code, Amazon Quick, Kiro, and Codex

[![skills.sh](https://skills.sh/b/aws-samples/sample-sagemaker-marketplace-onboarding-skill)](https://skills.sh/aws-samples/sample-sagemaker-marketplace-onboarding-skill)

An interactive [Agent Skill](https://agentskills.io) that walks model providers through building an inference container that complies with the **Amazon SageMaker Marketplace** container contract — and, optionally, through publishing a Marketplace listing. Works with [Claude Code](https://docs.claude.com/en/docs/claude-code), [Amazon Quick](https://docs.aws.amazon.com/quick/latest/userguide/skills-and-agents-desktop.html), [Kiro](https://kiro.dev/docs/skills/), [Codex](https://developers.openai.com/codex/skills), and any other tool that supports the standard `SKILL.md` format.

You describe your model; your agent guides you phase by phase — inventorying an existing project or scaffolding a new one, enforcing the `/ping` and `/invocations` contract, packaging model weights, running a local validation gate, and pushing to ECR. It is 100% guidance and templates: **no code runs on your behalf, and it never edits your existing project files.**

> **Non-production disclaimer.** The templates this skill scaffolds (`app.py`, `Dockerfile`, `model_loader.py`, `inference.py`, `metering.py`, `websocket_handler.py`, and the rest of `templates/`) are provided for demonstration and as a starting point only. They are **not intended for production or Marketplace submission as-is** and have not undergone security review. Before deploying or submitting a listing, you are responsible for your own security review and testing — including input validation, authentication/authorization where applicable, dependency pinning and vulnerability scanning, and any controls your use case and compliance obligations require.

---

## What you get

- **Works with existing projects or greenfield.** For existing code, the skill produces a gap report and scaffolds a compliant version *alongside* your files — you merge by hand. For new projects, it scaffolds from templates.
- **One `/invocations` implementation, four modes.** The same container serves Real-Time, Streaming, Async Inference, and Batch Transform. SageMaker handles routing.
- **A real `/ping` health check** that exercises the inference path, instead of a static `200` that passes health checks while the model is broken (the most common Marketplace validation failure).
- **Correct weights handling.** Weights load from `/opt/ml/model/` and ship separately as `model.tar` — no baked-in weights, no network calls at runtime.
- **Opt-in modules** for bidirectional WebSocket streaming and per-inference metering, scaffolded only if you need them.
- **A local validation gate** (`test/test_local.sh`) you run before you ever push to ECR.
- **Optional listing hand-off** that takes you through `CreateModelPackage` and the validation job if you want to publish.

## Requirements

- One of: [Claude Code](https://docs.claude.com/en/docs/claude-code), [Amazon Quick](https://docs.aws.amazon.com/quick/latest/userguide/skills-and-agents-desktop.html), [Kiro](https://kiro.dev/docs/skills/), [Codex](https://developers.openai.com/codex/skills), or another agent that reads the standard `SKILL.md` format.
- For local container testing: Docker, and the AWS CLI configured if you push to ECR.
- Python 3.12+ if you use the WebSocket client SDK notes (see `reference/websocket.md`).

## Install

This repo *is* the skill — `SKILL.md`, `reference/`, and `templates/` live at the repo root.

**Option A — from a release archive (recommended)**

Download the `sagemaker-marketplace-onboarding.skill` file from the [Releases](../../releases) page, then unzip it into your skills directory:

```bash
# User-global (available in every project)
unzip sagemaker-marketplace-onboarding.skill -d ~/.claude/skills/

# — or, per-project —
unzip sagemaker-marketplace-onboarding.skill -d .claude/skills/
```

**Option B — from source**

```bash
git clone https://github.com/aws-samples/sample-sagemaker-marketplace-onboarding-skill.git
mkdir -p ~/.claude/skills/sagemaker-marketplace-onboarding
cp -r sample-sagemaker-marketplace-onboarding-skill/{SKILL.md,reference,templates} ~/.claude/skills/sagemaker-marketplace-onboarding/
```

**Option C — via the [skills CLI](https://github.com/vercel-labs/skills)** (auto-detects Claude Code, Kiro, and Codex; installs to each one's own skills directory)

```bash
npx skills add aws-samples/sample-sagemaker-marketplace-onboarding-skill

# Or target a specific agent:
npx skills add aws-samples/sample-sagemaker-marketplace-onboarding-skill -a claude-code
npx skills add aws-samples/sample-sagemaker-marketplace-onboarding-skill -a kiro-cli
npx skills add aws-samples/sample-sagemaker-marketplace-onboarding-skill -a codex
```

**Option D — Amazon Quick**

Amazon Quick's desktop app imports skills from a single `SKILL.md` file rather than a repo URL: open **Agents & skills** > **Skills** tab > **+ Create** > **Import from file**, and select this repo's `SKILL.md`. See [Skills and agents in Amazon Quick](https://docs.aws.amazon.com/quick/latest/userguide/skills-and-agents-desktop.html) for details.

Restart your agent (or start a fresh session) so it picks up the new skill.

## Usage

Start a session with your agent and describe what you want. The skill activates on requests like:

- "Help me build a SageMaker Marketplace container"
- "Onboard my model to SageMaker Marketplace"
- "Package my model for SageMaker Marketplace"
- "Review my container against the SageMaker Marketplace spec"

Your agent asks two framing questions up front — container-only vs. also-list, and existing project vs. greenfield — then walks the rest one phase at a time, confirming before it moves on.

### The walkthrough at a glance

| Phase | What happens |
|------:|--------------|
| 0 | Goal + project-state questions that branch the flow |
| 1–2 | Inventory an existing project, then a discovery interview |
| 3–4 | Gap report and/or scaffold from templates |
| 5–10 | Contract, Dockerfile, weights packaging, local testing, ECR push, pre-submission checklist |
| 11 | *(also-list only)* `CreateModelPackage` + validation job + AWS docs hand-off |

Modality- and mode-specific questions are gated: an LLM provider never sees text-to-speech questions, and a container-only user never sees listing steps.

## Repository layout

```
SKILL.md                              ← the walkthrough Claude follows, phase by phase
templates/                            ← code files scaffolded into your project
├── Dockerfile
├── requirements.txt
├── app.py                            ← FastAPI server: /ping, /invocations, /execution-parameters
├── model_loader.py
├── inference.py                      ← smoke_check + predict + predict_stream + zip_outputs
├── metering.py                       ← per-inference billing headers (opt-in)
├── websocket_handler.py              ← bidirectional streaming (opt-in)
├── supervisord.conf                  ← multi-process container config (opt-in)
├── package_model.sh                  ← builds model.tar and uploads to S3
├── PRE_SUBMISSION_CHECKLIST.md
└── test/                             ← test_input.json, test_local.sh, test_streaming.py, test_websocket.py
reference/                             ← docs Claude reads to cite constraints (not scaffolded)
├── contract.md                       ← endpoint/header/timing cheat sheet
├── timing.md                         ← hard timing limits
├── checklist.md                      ← full pre-submission checklist
├── gap-checks.md                     ← gap-analysis list for existing projects
├── websocket.md                      ← bidirectional streaming + client SDK notes
├── billing.md                        ← hourly vs. per-inference metering
├── logging.md                        ← CloudWatch logging patterns
└── marketplace-listing.md            ← CreateModelPackage skeleton for the also-list path
```

`sagemaker-marketplace-onboarding.skill` — a prebuilt zip of the above three (wrapped in a `sagemaker-marketplace-onboarding/` folder, the name most agents expect under their own skills directory — e.g. `.claude/skills/` for Claude Code, `.kiro/skills/` for Kiro, `.agents/skills/` for Codex), attached to each [release](../../releases).

- **`templates/`** — files copied into your project. Changing one changes what you ship.
- **`reference/`** — docs Claude reads to answer questions and cite constraints, without touching your code.

## Scope — what this skill does *not* do

By design, the skill:

- **Never edits your existing project files.** It produces a gap report and scaffolds a compliant version alongside; you merge by hand.
- **Makes no AWS API calls on your behalf.** No boto3, no live SageMaker actions — it guides, you act.
- **Stops at `CreateModelPackage`.** FDP enrollment, IAM roles, pricing, EULA, and publishing live with AWS account teams and the Marketplace Management Portal.
- **Does not test your model's accuracy.** It validates AWS Sagemaker contract compliance, not model quality.

## Contributing

Contributions are welcome. Found a bug, an outdated constraint, or a gap? [Open an issue](../../issues) or send a [pull request](../../pulls). See [CONTRIBUTING.md](CONTRIBUTING.md) for details. The skill is entirely documentation and templates, so most changes are edits to `SKILL.md`, `reference/*.md`, or `templates/`.

Please test locally before opening a PR: install the skill into your own agent (Claude Code, Amazon Quick, Kiro, or Codex), run the walkthrough end to end, and for template changes do a full scaffold plus `bash test/test_local.sh <image> <weights>`. There is no CI — manual testing is the gate.

A few design principles are load-bearing and shouldn't be changed casually: `/ping` must exercise inference, `ENTRYPOINT` must be exec-form, no weights baked into the image and no runtime network calls, container code stays mode-agnostic, and every walkthrough question uses structured prompts rather than free text.

## License

See [LICENSE](LICENSE).
