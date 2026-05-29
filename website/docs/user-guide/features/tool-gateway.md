---
title: "Nous Tool Gateway"
description: "One subscription, every tool. Web search, image generation, video generation, TTS, and cloud browsers — all routed through Nous Portal with no extra API keys."
sidebar_label: "Tool Gateway"
sidebar_position: 2
---

# Nous Tool Gateway

**One subscription. Every tool built in.**

The Tool Gateway is included with every paid [Nous Portal](https://portal.nousresearch.com) subscription. It routes Hermes' tool calls — web search, image generation, video generation, text-to-speech, and cloud browser automation — through infrastructure Nous already runs, so you don't have to sign up with Firecrawl, FAL, OpenAI, Browser Use, or anyone else just to make your agent useful.

<div style={{display: 'flex', gap: '1rem', flexWrap: 'wrap', margin: '1.5rem 0'}}>
  <a href="https://portal.nousresearch.com/manage-subscription" style={{background: 'var(--ifm-color-primary)', color: 'white', padding: '0.75rem 1.5rem', borderRadius: '6px', textDecoration: 'none', fontWeight: 'bold'}}>Start or manage subscription →</a>
</div>

## What's included

| | Tool | What you get |
|---|---|---|
| 🔍 | **Web search & extract** | Agent-grade web search and full-page extraction via Firecrawl. No rate limits to worry about — the gateway handles scaling. |
| 🎨 | **Image generation** | Nine models under one endpoint: **FLUX 2 Klein 9B**, **FLUX 2 Pro**, **Z-Image Turbo**, **Nano Banana Pro** (Gemini 3 Pro Image), **GPT Image 1.5**, **GPT Image 2**, **Ideogram V3**, **Recraft V4 Pro**, **Qwen Image**. Pick per-generation with a flag, or let Hermes default to FLUX 2 Klein. |
| 🎬 | **Video generation** | Text-to-video and image-to-video through FAL — **Veo 3.1**, **Pixverse v6**, **Kling**, **LTX-2.3** — wired into the `video_generate` tool. No FAL key required. Pick a model with `hermes tools` → Video Generation. |
| 🔊 | **Text-to-speech** | OpenAI TTS voices wired into the `text_to_speech` tool. Drop voice notes into Telegram, generate audio for pipelines, narrate anything. |
| 🌐 | **Cloud browser automation** | Headless Chromium sessions via Browser Use. `browser_navigate`, `browser_click`, `browser_type`, `browser_vision` — all the agent-driving primitives, no Browserbase account required. |

All four are pay-as-you-use billed against your Nous subscription. Use any combination — run the gateway for web and images while keeping your own ElevenLabs key for TTS, or route everything through Nous.

## Why it's here

Building an agent that can actually *do things* means stitching together 5+ API subscriptions — each with their own signup, rate limits, billing, and quirks. The gateway collapses that into one account:

- **One bill.** Pay Nous; we handle the rest.
- **One signup.** No Firecrawl, FAL, Browser Use, or OpenAI audio accounts to manage.
- **One key.** Your Nous Portal OAuth covers every tool.
- **Same quality.** Same backends the direct-key route uses — just fronted by us.

Bring your own keys anytime — per-tool, whenever you want to. The gateway isn't a lock-in, it's a shortcut.

## Get started

The fastest path for a fresh install:

```bash
hermes setup --portal     # Nous OAuth, set Nous as provider, and turn on the Tool Gateway in one go
```

Already have Hermes configured? Just switch your provider:

```bash
hermes model              # Pick Nous Portal — Hermes will offer to turn on the Tool Gateway
```

When you select Nous Portal, Hermes offers to turn on the Tool Gateway. Accept, and you're done — every supported tool is live on the next run.

Check what's active at any time:

```bash
hermes portal status      # Portal auth + Tool Gateway routing summary
hermes portal tools       # Gateway catalog with current routing per tool
hermes status             # Full system status (Tool Gateway is one section)
```

`hermes portal status` shows a section like:

```
◆ Nous Tool Gateway
  Nous Portal     ✓ managed tools available
  Web tools       ✓ active via Nous subscription
  Image gen       ✓ active via Nous subscription
  TTS             ✓ active via Nous subscription
  Browser         ○ active via Browser Use key
```

Tools marked "active via Nous subscription" are going through the gateway. Anything else is using your own keys.

## Eligibility

The Tool Gateway is a **paid-subscription** feature. Free-tier Nous accounts can use Portal for inference but don't include managed tools — [upgrade your plan](https://portal.nousresearch.com/manage-subscription) to unlock the gateway.

## Mix and match

The gateway is per-tool. Turn it on for just what you want:

- **All tools through Nous** — easiest; one subscription, done.
- **Gateway for web + images, bring your own TTS** — keep your ElevenLabs voice, let Nous handle the rest.
- **Gateway only for things you don't have keys for** — "I already pay for Browserbase, but I don't want a Firecrawl account" works fine.

Switch any tool at any time via:

```bash
hermes tools          # Interactive picker for each tool category
```

Select the tool, pick **Nous Subscription** as the provider (or any direct provider you prefer). No config editing required.

## Using individual image models

Image generation defaults to FLUX 2 Klein 9B for speed. Override per-call by passing the model ID to the `image_generate` tool:

| Model | ID | Best for |
|---|---|---|
| FLUX 2 Klein 9B | `fal-ai/flux-2/klein/9b` | Fast, good default |
| FLUX 2 Pro | `fal-ai/flux-2/pro` | Higher fidelity FLUX |
| Z-Image Turbo | `fal-ai/z-image/turbo` | Stylized, fast |
| Nano Banana Pro | `fal-ai/gemini-3-pro-image` | Google Gemini 3 Pro Image |
| GPT Image 1.5 | `fal-ai/gpt-image-1/5` | OpenAI image gen, text+image |
| GPT Image 2 | `fal-ai/gpt-image-2` | OpenAI latest |
| Ideogram V3 | `fal-ai/ideogram/v3` | Strong prompt adherence + typography |
| Recraft V4 Pro | `fal-ai/recraft/v4/pro` | Vector-style, graphic design |
| Qwen Image | `fal-ai/qwen-image` | Alibaba multimodal |

The set evolves — `hermes tools` → Image Generation shows the current live list.

---

## Using individual video models

Video generation routes through FAL the same way image generation does. Set a default model with `hermes tools` → Video Generation, or pin it in `config.yaml` under `video_gen.model`. Use the short family name (not the raw FAL endpoint):

| Model | `video_gen.model` | Tier | Notes |
|---|---|---|---|
| LTX 2.3 (22B) | `ltx-2.3` | cheap | 22B with native audio. Fast (~30-60s). |
| Pixverse v6 | `pixverse-v6` | cheap | Negative prompts, 1-15s durations. |
| Veo 3.1 | `veo3.1` | premium | Google DeepMind. Cinematic, native audio, strong prompt adherence. |
| Seedance 2.0 | `seedance-2.0` | premium | ByteDance. Synchronized audio + lip-sync, 4-15s. |
| Kling v3 4K | `kling-v3-4k` | premium | 4K output, native audio, 3-15s. |
| Happy Horse 1.0 | `happy-horse` | premium | Alibaba. |

Every model supports both text-to-video (omit `image_url`) and image-to-video (pass `image_url`); the active backend auto-routes to the right endpoint. The `video_generate` tool description is rebuilt at session start to reflect the chosen model's real capabilities — aspect ratios, resolutions, duration range, audio support.

Which models are enabled on a given subscription is decided gateway-side, not by your config. If a model returns an HTTP 4xx with *"Nous Subscription gateway rejected endpoint … This model may not yet be enabled,"* it isn't allowlisted on your subscription yet — pick another model, or set `FAL_KEY` in `.env` to hit FAL directly and bypass the gateway allowlist entirely.

---

## Configuration reference

Most users never need to touch this — `hermes model` and `hermes tools` cover every workflow interactively. This section is for writing config.yaml directly or scripting setups.

### Per-tool `use_gateway` flag

Each tool's config block takes a `use_gateway` boolean:

```yaml
web:
  backend: firecrawl
  use_gateway: true

image_gen:
  use_gateway: true

video_gen:
  provider: fal
  use_gateway: true

tts:
  provider: openai
  use_gateway: true

browser:
  cloud_provider: browser-use
  use_gateway: true
```

Precedence: `use_gateway: true` routes through Nous regardless of any direct keys in `.env`. `use_gateway: false` (or absent) uses direct keys if available and only falls back to the gateway when none exist.

### Disabling the gateway

```yaml
web:
  use_gateway: false   # Hermes now uses FIRECRAWL_API_KEY from .env
```

`hermes tools` automatically clears the flag when you pick a non-gateway provider, so this usually happens for you.

### Self-hosted gateway (advanced)

Running your own Nous-compatible gateway? Override endpoints in `~/.hermes/.env`:

```bash
TOOL_GATEWAY_DOMAIN=your-domain.example.com
TOOL_GATEWAY_SCHEME=https
TOOL_GATEWAY_USER_TOKEN=your-token        # normally auto-populated from Portal login
FIRECRAWL_GATEWAY_URL=https://...         # override one endpoint specifically
```

These knobs exist for custom infrastructure setups (enterprise deployments, dev environments). Regular subscribers never set them.

## FAQ

### Does it work with Telegram / Discord / the other messaging gateways?

Yes. Tool Gateway operates at the tool-execution layer, not the CLI. Every interface that can call a tool — CLI, Telegram, Discord, Slack, IRC, Teams, the API server, anything — benefits from it transparently.

### What happens if my subscription expires?

Tools routed through the gateway stop working until you renew or swap in direct API keys via `hermes tools`. Hermes shows a clear error pointing at the portal.

### Can I see usage or costs per tool?

Yes — the [Nous Portal dashboard](https://portal.nousresearch.com) breaks usage down by tool so you can see what's driving your bill.

### Is Modal (serverless terminal) included?

Modal is available as an **optional add-on** through the Nous subscription, not part of the default Tool Gateway bundle. Configure it via `hermes setup terminal` or directly in `config.yaml` when you want a remote sandbox for shell execution.

### Do I need to delete my existing API keys when I enable the gateway?

No — keep them in `.env`. When `use_gateway: true`, Hermes skips direct keys and uses the gateway. Flip the flag back to `false` and your keys become the source again. The gateway isn't a lock-in.
