# AI Video Tools Research

Date: March 19, 2026

## Scope

This note captures practical research on using `invideo AI` and `Google Flow` to produce short-form ACGS videos for:
- developers
- enterprise buyers
- YC / VC audiences

It combines:
- official product/help-center guidance
- hands-on browser automation findings from this repository session

## Executive Summary

`invideo AI` is the better near-term tool for prompt-to-Reel generation.

Why:
- It supports direct short-form workflows and script-driven video generation.
- It can generate full vertical short videos from a single prompt.
- It exposes a post-generation editing path via Magic Box, script editing, and media replacement.

`Google Flow` is better treated as a clip-generation and scene-composition tool, not a direct replacement for InVideo’s one-prompt Reel workflow.

Why:
- Flow is designed around generating and organizing clips, then composing scenes.
- The direct `Create` path in this session routed our ACGS prompt into image jobs, which failed.
- `Scenebuilder` expects project clips already present; it is not a blank “generate full Reel from script” surface.

`Gemini API + Veo 3.1` is the strongest programmable path when exact control matters more than UI convenience.

Why:
- It supports direct text-to-video generation through the Gemini API.
- It supports portrait `9:16` output for Reels / Shorts / TikTok.
- It supports reference images, first/last frame control, and video extension.
- It avoids some of the UI ambiguity encountered in InVideo and Flow when handling acronyms and technical product prompts.

## Official Product Research

### Google Flow

Official pages indicate:
- Flow is an AI creative studio built around Google DeepMind models `Veo`, `Imagen`, and `Gemini`.
- It is designed for creatives to create clips, refine them, and compose scenes.
- It is available to `Google AI Pro` and `Google AI Ultra` subscribers.
- It is best experienced on desktop in Chromium-based browsers.

Relevant official sources:
- Flow landing page: https://labs.google/fx/tools/flow
- Flow FAQ: https://labs.google/fx/tools/flow/faq

Key official language from the FAQ and landing page:
- Flow lets users create cinematic clips and transition them into scenes.
- Capabilities are framed as `Create`, `Refine`, and `Compose`.
- The workflow assumes asset and scene management, not only single-prompt full-video generation.

### InVideo AI

Official help indicates:
- InVideo supports workflow-driven creation from the prompt page.
- It has specific flows for short videos, Shorts/Reels/TikTok, and script-based video generation.
- It supports a “Use my script” flow for generating a video from an exact script.
- It supports post-generation editing through Magic Box and script/media editing.

Relevant official sources:
- Workflows overview: https://help.invideo.io/en/articles/9974576-where-can-i-find-the-flows-in-version-3-0
- Use my script: https://help.invideo.io/en/articles/9382180-how-can-i-create-a-video-using-my-script
- Shorts / Reels / TikTok: https://help.invideo.io/en/articles/9382184-how-can-i-create-youtube-shorts-instagram-reels-and-tiktok-videos
- Magic Box editing: https://help.invideo.io/en/articles/9387692-what-is-magic-box-and-how-to-use-it
- Script text editing: https://help.invideo.io/en/articles/9387669-how-can-i-add-edit-or-delete-text-shown-on-my-video

### Gemini API + Veo 3.1

Official API documentation indicates:
- Veo 3.1 is Google’s state-of-the-art video generation model for high-fidelity video with native audio.
- It supports text-to-video, image-to-video, reference images, first/last frame interpolation, and video extension.
- It supports portrait `9:16` generation for short-form social output.
- It uses long-running asynchronous operations that must be polled until generation completes.

Relevant official sources:
- Gemini API video guide: https://ai.google.dev/gemini-api/docs/video
- Veo model page: https://deepmind.google/models/veo/
- Pricing: https://ai.google.dev/gemini-api/docs/pricing#veo-3.1

Key official capabilities from the docs:
- Model code: `veo-3.1-generate-preview`
- Fast variant: `veo-3.1-fast-generate-preview`
- Aspect ratios: `16:9` and `9:16`
- Resolutions: `720p`, `1080p`, `4k`
- Duration: `4`, `6`, or `8` seconds
- Reference images: up to 3
- Video extension: supported for Veo-generated videos

## Live Session Findings

### InVideo: What Worked

Observed in session:
- InVideo allowed login and access to the AI workspace.
- The main prompt surface accepted direct requests for vertical Reels.
- Project creation succeeded for three ACGS variants:
  - developer
  - mass audience
  - VC / enterprise
- The `Use my script` flow existed and matched InVideo’s official help documentation.
- Generated project URLs were created successfully.

Observed project URLs created in session:
- Developer Reel:
  `https://ai.invideo.io/workspace/49ec7107-8e3b-495c-b640-f978954edc4e/v40-copilot/970addf3-e664-489e-90b7-33e17e5b7200`
- Mass-audience Reel:
  `https://ai.invideo.io/workspace/49ec7107-8e3b-495c-b640-f978954edc4e/v40-copilot/c4c69811-1f71-4a44-bd5b-639302e1642e`
- VC / enterprise Reel:
  `https://ai.invideo.io/workspace/49ec7107-8e3b-495c-b640-f978954edc4e/v40-copilot/8f35980f-e406-426f-897e-ff2afc17bada`

### InVideo: What Failed or Drifted

Observed failure mode:
- InVideo misread `ACGS` as `ACG Brands` during one early generation attempt.

Implication:
- Acronym-only prompts are unsafe for factual enterprise content.
- Prompting must expand the acronym and explicitly forbid tool-side reinterpretation.

Prompting fix that improved reliability:
- Expand `ACGS` as `Advanced Constitutional Governance System`.
- Explicitly state:
  - this is governance infrastructure for AI agents
  - this is not `ACG Brands`
  - do not invent or research a different company

### Flow: What Worked

Observed in session:
- Login succeeded after Google sign-in and 2-Step Verification.
- A new Flow project could be created.
- The main project surface exposed:
  - `Add Media`
  - `Scenebuilder`
  - prompt box + `Create`

### Flow: What Failed or Blocked

Observed failure mode:
- Direct `Create` from the project prompt surface routed the ACGS prompt into `image` generation jobs rather than a complete short-form video flow.
- Two identical attempts failed at `23%`.

Observed Scenebuilder limitation:
- `Scenebuilder` opened, but the empty project state said:
  `Add clips from your project to create a scene`

Implication:
- Flow’s creator UX is clip-first, then scene composition.
- It is not equivalent to InVideo’s prompt-to-Reel workflows.

### Gemini API + Veo 3.1: What The Docs Change

The API docs materially change the decision surface for ACGS.

Implication:
- The right comparison is not only `InVideo UI` vs `Flow UI`.
- There is a stronger third option for engineering-heavy content:
  `Generate short clips directly with Veo 3.1 via the Gemini API`.

Why this matters for ACGS:
- the content is acronym-heavy and technically precise
- we want fewer UI-side reinterpretations
- portrait social-video output is explicitly supported
- prompts can be versioned and reused in source control

## Veo 3.1 API Notes

### Best-fit use cases for ACGS

Use Veo 3.1 when you need:
- direct programmable generation
- exact control over prompt wording
- explicit aspect ratio and resolution control
- repeatable variant generation for hooks and promo assets
- an internal generation pipeline rather than ad hoc UI use

### Best-fit output strategy

For ACGS, Veo is best used in one of two ways:

1. Generate short portrait clips around one claim, then assemble them elsewhere.
2. Generate a small set of branded visual assets and use an editor for captions and sequencing.

This is a better fit for:
- hook clips
- animated governance visuals
- abstract enterprise AI motion assets

It is a weaker fit for:
- fully edited, text-heavy Reels out of the box
- one-click social video assembly with finished captions

### Strong prompt pattern for ACGS

For ACGS-specific generations:
- expand the acronym
- avoid relying on the tool to infer technical meaning
- emphasize visuals, not unsupported factual claims

Example prompt pattern:

```text
Create a vertical 9:16 cinematic technology promo clip about ACGS, the Advanced Constitutional Governance System.
Show abstract enterprise AI infrastructure, governance diagrams, and layered validation flows.
Visualize three distinct roles: proposer, validator, executor.
Show constitutional validation before action.
On-screen text style should be bold, minimal, and factual.
Mood: precise, modern, trustworthy, high-tech.
Avoid consumer branding, retail products, or irrelevant company imagery.
```

### API-level recommendation

If this repo needs a durable AI-video generation path, the API route is likely more defensible than Flow UI automation.

Why:
- prompts can be versioned
- outputs can be downloaded deterministically
- retries and polling are explicit
- aspect ratio and resolution are explicit
- it avoids UI drift and account-level modals

## Practical Comparison

### InVideo

Best for:
- fast prompt-to-Reel production
- exact script-to-video workflows
- short-form marketing / explainer / founder videos
- editing generated output without a full rebuild

Risks:
- semantic drift on acronyms or niche technical brands
- need for stronger factual guardrails in prompts
- should always be reviewed before export

### Flow

Best for:
- generating cinematic clips
- visual experimentation
- assembling scenes from generated assets
- creator workflows where visual polish matters more than speed

Risks:
- not optimized for “one prompt -> final Reel” execution
- more manual asset-building required
- current direct create flow can route technical prompts incorrectly

### Gemini API + Veo 3.1

Best for:
- programmable clip generation
- exact control of aspect ratio, resolution, and prompting
- repeatable technical content pipelines
- generating factual visual assets around a technical concept

Risks:
- not a full social-video editor
- requires polling and file handling
- likely needs a second tool for final assembly, captions, and sequencing
- cost and latency increase with higher resolution

## Recommended Tool Strategy For ACGS

### Primary path

Use `invideo AI` as the default production tool for short-form ACGS videos.

Use cases:
- founder Reels
- developer Reels
- enterprise / buyer Reels
- fast iteration on hooks and captions

### Secondary path

Use `Google Flow` only for high-polish visual sequences after message-market fit is established.

Use cases:
- clip generation for high-end promo visuals
- cinematic inserts
- scene-based storytelling where custom generated shots matter

### Programmable path

Use `Gemini API + Veo 3.1` when:
- you want deterministic prompts in source control
- you need portrait video from an API
- you want a reusable engineering-grade asset generation pipeline
- you want to minimize UI-side drift on technical messaging

### Recommended production workflow

1. Develop messaging and scripts first.
2. Generate vertical Reel drafts in InVideo.
3. Review for factual drift, especially acronym confusion.
4. Edit script and visuals using InVideo’s script editing and Magic Box.
5. Only use Flow if a specific scene needs more cinematic custom visuals.
6. If a repeatable engineering workflow is needed, move clip generation to Veo 3.1 API and keep final assembly in an editor.

## Prompting Guidance

### Safe prompt pattern for ACGS in InVideo

Use this pattern:

```text
Create a 15-second vertical Instagram Reel about ACGS, which stands for Advanced Constitutional Governance System.
This is governance infrastructure for AI agents, not ACG Brands and not a consumer company.
Use only the facts in this prompt. Do not invent or research a different company.
```

Then add the exact script or core claims.

### Core claims that held up best in strategy work

- agents should not validate their own outputs
- separation of proposer, validator, executor
- constitutional validation before action
- 560ns median local validation
- governance trail for enterprise systems

## Open Risks

- InVideo generations still require manual review for factual accuracy.
- Flow may be viable later for clip-first workflows, but not yet proven here for direct short-form ACGS generation.
- Export, final render quality, and final share settings were not fully validated in this session.

## Recommended Next Actions

1. Open the three InVideo project URLs and review the generated drafts.
2. Correct any acronym drift or invented claims using InVideo script editing.
3. Export only after script and captions are verified.
4. If more cinematic visuals are required, use Flow to generate specific insert clips, not the whole Reel.
5. If a programmable path is needed, prototype one portrait ACGS clip directly with Veo 3.1 before investing further in Flow UI automation.

## Source Notes

Official sources used:
- Flow landing page: https://labs.google/fx/tools/flow
- Flow FAQ: https://labs.google/fx/tools/flow/faq
- Gemini API video guide: https://ai.google.dev/gemini-api/docs/video
- Veo model page: https://deepmind.google/models/veo/
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing#veo-3.1
- InVideo workflows help: https://help.invideo.io/en/articles/9974576-where-can-i-find-the-flows-in-version-3-0
- InVideo script-to-video help: https://help.invideo.io/en/articles/9382180-how-can-i-create-a-video-using-my-script
- InVideo shorts/reels help: https://help.invideo.io/en/articles/9382184-how-can-i-create-youtube-shorts-instagram-reels-and-tiktok-videos
- InVideo Magic Box help: https://help.invideo.io/en/articles/9387692-what-is-magic-box-and-how-to-use-it
- InVideo script text editing help: https://help.invideo.io/en/articles/9387669-how-can-i-add-edit-or-delete-text-shown-on-my-video

Session-based observations in this document are from live browser automation performed on March 19, 2026.
