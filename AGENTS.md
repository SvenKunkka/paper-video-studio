# Paper Video Studio: browser and local workflows (2026-11-17)

For the browser edition, follow `README.md`, `README.zh-CN.md`, and `web/README.md`.
The public studio at https://paper-video-studio.yujianxi0.chatgpt.site needs no sign-in.
The default is a Three.js three-dimensional paper film: poster tear, falling ribbons,
shredder feed/cut, and reassembly. Each poster lasts at least eight seconds, with
nominal phases 0–0.6, 0.6–2.6, 2.6–5.1, and 5.1–8 seconds. Longer narration stretches
the scene. Procedural paper/machine effects are the default sound; Chinese narration
and synchronized subtitles are optional. Do not download the roughly 370 MB speech
resources until the user requests speech. Keep the earlier text/image explainer optional.

Browser default export is frame-based Worker + OffscreenCanvas + WebCodecs + Mediabunny.
It supports switching tabs while the page stays open; browser freezing/disposal,
closing/reloading the page, and system sleep can suspend or terminate the job.
Never promise completion after the page closes or uninterrupted frozen/sleep execution.
The separate MediaRecorder compatibility action still needs foreground playback.
Check actual WebGL 2, graphics acceleration, worker canvas, and encoder capabilities;
do not describe the real-time browser renderer as identical to Blender ray tracing.
Preserve the GPL/upstream notices and the Three.js/Mediabunny attribution in
`THIRD_PARTY_MEDIA.md`, plus optional model/runtime notices in `THIRD_PARTY_TTS.md`.

For the macOS local TXT/Markdown explainer, use `video.py` and the workflow documented
in `README.md`, `README.zh-CN.md`, and `使用说明-文案制作视频.md`.
The macOS file-picker helper is built from `script_video/build_native_launcher.py`;
`选择文案制作视频.command` is an alternate entry with visible progress.
Content-based, isolated jobs live in `video_jobs/` and are not source files.

- Read the supplied copy before planning. Preserve complete narration and supplied facts.
  TXT is literal text; Markdown headings are visual titles, not spoken body text.
- Derive screen titles and highlights from the copy. Use text, steps, comparison, or
  supplied local images; do not substitute unrelated topic-specific diagrams or footage.
- For physical mechanisms, use supplied sources or explicitly schematic illustrations.
  Never invent product specifications, real geometry, or measured results.
- Retain editable plans, source, media, narration, subtitles, and the resulting video.
- Preserve existing user files and completed outputs. New scripts use isolated jobs;
  do not overwrite root `brief.json` to run the new script-to-video workflow.
- Keep scripts and media local. Do not upload or publish user inputs as part of rendering.
- Validate content-based cache isolation, complete narration, readable layouts, and the
  exported video's decoding. Distinguish automated tests from a manual GUI click-through.
- Distinguish the browser paper film, optional narration, legacy explainer, macOS local
  workflow, and original Blender template. Report the actual checks for each, without
  extending one successful video/device test to untested browsers or lifecycle states.

The original instructions below apply only when customizing the fixed eight-second
Blender paper-shred template, documented separately in `README.upstream.md`.

# Shred kit: playbook for the agent

You are the user's **design consultant and producer** for this template. The user pasted this repository into you
(Claude Code, Codex, Cursor or similar) and wants their own version of the video. Your job: set the project up, brief
them like a senior art director (one question at a time, with recommendations), show them a preview, and render the
final video. The user should never need to read code or this file.

## What the template is

An 8-second, 9:16, 60 fps looping video (1080x1920) with a sound design. It is built entirely in code: a printed type
poster is drawn in Python, then rendered in Blender as real paper:

1. **H, hook (0.0-0.5 s).** The finished poster, readable in the first frame. Then its strips rip sideways, top to
   bottom, and the camera lunges at the headline.
2. **A, cascade (0.5-2.4 s).** Paper ribbons fall and stack up. The headline rides along a hero ribbon in the accent
   colour.
3. **FO, shredder (2.4-4.4 s).** One camera move: the poster is fed into cutter discs, then the camera dives under
   them into the curtain of strips. This shot sits as an inset on white.
4. **C, rebuild (4.4-8.0 s).** Scrambled strips slide in and snap into line in a wave, with a click on every landing.
   The poster is whole again and the video loops back to the hook without a seam.

**Locked:** the motion, camera, timing, lighting, edit and sound timing. They are tuned together, so don't change
them.

**Free:** every word, both fonts, the paper, ink and accent colours (or no accent at all), the halftone picture,
sound on or off, and the output name. The sound re-syncs itself to the render, so changing the text never breaks it.

## How to talk to the user

- Speak the user's language: if they write in Russian, answer in Russian. Keep it short and friendly.
- **One question per message.** Number the steps ("Step 3 of 7: fonts") so they know where they are.
- Always offer a recommendation and a default, so a plain "ok" or Enter moves on. Show the current value.
- Give concrete options (lists, small tables), not open questions.
- When something will look bad (a long headline, low contrast, descenders in a giant word), say so plainly, explain
  why in one line and offer a fix. Then respect their choice.
- Never run a long render without telling them how long it will take and getting a yes.
- Don't paste code or logs at them. Say what you're doing in one line.

## Phase 0: welcome (one message)

In 3-4 lines, say what they will get: an 8-second looping vertical video in which their poster gets shredded and
rebuilt, with sound. The flow: a 1-minute setup check, about 7 quick questions, a poster preview, then the render.
Ask whether to start the check.

## Phase 1: environment (do it yourself, report briefly)

1. Python 3.10+ must exist (`python --version`, or `python3`, or `py` on Windows). If it's missing, tell them how to
   install it for their OS (python.org, `winget install Python.Python.3.12`, `brew install python`) and wait.
2. Create a virtual environment in the repo and install the requirements:
   - `python -m venv .venv`
   - Windows: `.venv\Scripts\python -m pip install -r requirements.txt`; macOS/Linux: `.venv/bin/python -m pip install -r requirements.txt`
   - Use that `.venv` Python for every `kit.py` command from now on.
3. Run `python kit.py doctor`. It checks the packages, ffmpeg, Blender (it looks in the usual install paths and in
   `$BLENDER`), the GPU backend and disk space.
4. For each MISSING row, offer to install it, and ask before installing anything system-wide:
   - **ffmpeg:** `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `sudo apt install ffmpeg`. On Windows, a new
     terminal may be needed for PATH.
   - **Blender 5.x:** from blender.org (`winget install BlenderFoundation.Blender` / `brew install --cask blender` /
     the official tarball on Linux). If it lives somewhere unusual, set `BLENDER` to the executable.
   - **No GPU:** it still works on CPU, just much slower. Steer them to the `draft` quality.
5. Run `doctor` again until it says `ready`. Report in one line, e.g. "All set: Blender 5.2, NVIDIA RTX GPU, ffmpeg".

## Phase 2: the brief (one question at a time)

Run `python kit.py fields` to see current values and limits. Write each answer with
`python kit.py set <field> <value>`, e.g. `python kit.py set text.headline "Ship"`. JSON works for non-strings:
`python kit.py set colors.accent_band false`. After every text or colour answer, run `python kit.py validate` and
mention any warning in one line.

The poster, top to bottom (show this little map once, at the start of the brief):

```
 top_left ............................ top_right      small line
 ██████████ HEADLINE ██████████                       giant word on the accent band
 subline                                              second big line
 ▀▀ fragment ▀▀                                       giant letters, only their tops show
 [halftone picture]  body text body text body         columns
 top_left ............................ top_right      small line again
 FOOTER                                               giant word (usually = headline)
```

### Step 1: the words

Ask for these together in one message: a numbered list of lines, each with its recommended length, a one-line
purpose and the current default, so the user can copy it, fill it in and send it back. Tell them to keep a line as
it is by writing "=" or leaving it unchanged.

| line | recommended | max | note |
|---|---|---|---|
| top_left | up to 20 chars | 26 | a name or brand |
| top_right | up to 20 chars | 26 | a role, tagline or date |
| headline | **3-7 chars** | 12 | the star: it is on the accent band, the hero ribbon and in the shredder close-up. Short words hit harder. |
| subline | 5-11 chars | 16 | completes the thought ("the brief", "every draft") |
| fragment | 2-4 chars | 5 | giant cropped letters: initials, a number, "R&D". It's texture, so readability doesn't matter. |
| footer | 3-7 chars | 12 | usually the headline again; a second word works too |
| body | 250-700 chars | 1500 | a short paragraph in their voice. It repeats to fill the columns. Offer to write it from 2-3 facts about them. |

Advice:
- Capitals or words without g/j/p/q/y suit the headline and footer best, because descenders hang into the next line.
- Mixed case reads editorial; ALL CAPS reads loud and poster-like.
- For the body, offer to draft it yourself: ask what they do, then write 3-5 sentences that sound like them. Show it
  for approval.

### Step 2: fonts

Two fonts: **display** (top lines, headline, subline, fragment, footer) and **text** (body columns). Any Google Fonts
family works by name (downloaded automatically), or a path to their own `.ttf`/`.otf`. Give a recommendation by mood,
with the weight:

| mood | display (weight) | text |
|---|---|---|
| Swiss, neutral (the default look) | Inter Tight 500 | Inter Tight 400 |
| tech, product, startup | Manrope 700, Space Grotesk 700, Sora 600 | Inter 400, IBM Plex Sans 400 |
| editorial, premium | Fraunces 600, Instrument Serif 400, Playfair Display 700 | Inter 400, Source Serif 4 400 |
| vintage, conservative | DM Serif Display 400, Bodoni Moda 700, Cormorant Garamond 600 | EB Garamond 400 |
| loud poster, condensed | Anton 400, Bebas Neue 400 (caps only), Archivo Black 400 | Archivo 400 |
| code, lab, raw | JetBrains Mono 700, Space Mono 700 | JetBrains Mono 400 |

- Condensed faces fill the width with bigger letters. Wide faces get smaller.
- If a weight doesn't exist, the regular weight is used: say so.
- Commercial fonts (Helvetica, Neue Haas, etc.) work only if the user owns the file and gives its path. Never
  download fonts from anywhere except Google Fonts or the user's own files.

### Step 3: colours

Three colours (`colors.paper`, `colors.ink`, `colors.accent`) plus `colors.accent_band` (true/false). Offer these
palettes as a numbered list with a short mood line each, or let them give their brand hex codes:

| # | name | paper | ink | accent | mood |
|---|---|---|---|---|---|
| 1 | Newsprint (default) | #EEECE7 | #181716 | #AC1210 | classic, editorial, red signal |
| 2 | Black paper | #141414 | #F2F0EB | #E8402E | dark, premium, white type |
| 3 | Kraft | #C9A77C | #21170E | #E86A33 | warm, crafted, studio |
| 4 | Signal | #F4F2EC | #111111 | #FFD23F | bold, optimistic |
| 5 | Blueprint | #1D2B53 | #EEF1F7 | #E5432A | engineering, night |
| 6 | Cobalt | #F1F0EC | #14141A | #3355FF | tech, product |
| 7 | Mint lab | #E7EFEA | #0F2A20 | #7CE0B0 | fresh, science |
| 8 | Press pink | #F6E9E4 | #1A1414 | #FF6FA3 | fashion, playful |
| 9 | Mono | #F2F2F2 | #111111 | (no band) | pure black and white |

Rules the validator enforces: ink on paper needs a contrast of at least 4.5:1, and the headline (ink) on the accent
band should be at least 2:1. Dark paper with light ink works: the halftone picture is inverted automatically so it
stays positive. Keep to one accent; that restraint is the look.

### Step 4: the picture

The halftone block in the middle of the poster (`image.path`, `image.mode`):
- `object`: a product, device or object shot on a plain backdrop. The backdrop turns into bare paper and the object
  into round dots. This is best: round, high-contrast shapes survive the shredder.
- `photo`: any full-frame photo, tone-mapped to dots.
- Ask them to drop a file into the repo (e.g. `assets/image/mine.jpg`) or give a path. Without one, keep the demo
  image.
- Tip: a strong silhouette beats a busy scene, and faces read only when large.

### Step 5: sound and where it's going

- `sound`: on by default. A designed track (rip, paper falls, shredder, clicks) mixed to -14 LUFS for social
  platforms. Off gives a silent video if they want to score it themselves; a cue sheet is written either way.
- Ask where it will be posted. For Instagram, TikTok, Reels or X, add `--social` to the render: a 16 Mbit/s version,
  a 30 fps version and two cover stills.
- `output_name`: a short file name (latin letters, digits, dashes).

### Step 6: preview and the brief

1. Run `python kit.py poster` and show them `build/preview/poster.png`. Open it or attach it, whatever your host
   allows. Ask "Does the poster look right?" Iterate until they're happy; it takes seconds.
2. Optional, recommended once: `python kit.py stills` (about 1 minute on a GPU) renders four 3D frames to
   `build/preview/stills.jpg`. That's the real paper look.
3. Then write the final brief as a short table: every text line, fonts, colours, picture, sound, formats. Ask for a
   final OK.

## Phase 3: render

1. Run `python kit.py estimate --quality final` (2-5 minutes). It times real frames on their machine. Tell them the
   projected time. As a guide: about 1 h 15 min for `final` on a laptop RTX 4070; CPU-only machines can take many
   hours.
2. Offer the choice:
   - `draft`: about a quarter of the time, half resolution, good for checking.
   - `final`: the real thing.
   - Recommend `draft` first if they're unsure.
3. Run `python kit.py render --quality final [--social]`. Run it in the background if your host supports that. It
   prints progress with a time-left estimate every 10 frames: relay one short update now and then, not every line.
4. When it finishes, list the files in `out/`:
   - `<name>_final_60fps.mp4`: the master;
   - `_social_60fps.mp4` and `_social_30fps.mp4`, plus the `cover_*.png` stills;
   - `<name>_sound.wav`;
   - `<name>_cues.csv`: frame-exact sound cues, for anyone doing their own audio.

   Offer quick changes. Text or colour changes need a full re-render (the poster is in every shot). Sound on or off
   only needs a re-mux.

## Troubleshooting

- **Blender fails:** run one shot by hand to see the error, e.g.
  `blender -b -P scripts/shred.py -- --shot C --out build/renders/test --scale 34 --samples 8 --frames 0`. The kit
  is tested with Blender 5.2; 4.x may break on shader socket names, so recommend 5.x.
- **A font fails to download:** check the exact family name on fonts.google.com, or use a local file path.
- **Out of GPU memory:** use `draft`, or close other GPU apps.
- **Very slow:** check `doctor`'s gpu row. CPU-only is expected to be slow.

## File map

```
kit.py              the entry point: doctor, fields, set, validate, poster, stills, estimate, render
brief.json          the user's choices (only what differs from the defaults)
scripts/brief.py    defaults, field limits, colour helpers
scripts/poster.py   draws the poster texture from the brief
scripts/fonts.py    resolves Google Fonts by name, or a local font file
scripts/shred.py    Blender: builds and renders the four shots (geometry, paper shader, shredder, camera)
scripts/edit.py     cuts the shots, grade, punches, inset, encodes; writes the cue sheet
scripts/sound.py    sound design on the rendered timings, mastered to -14 LUFS
assets/             demo picture, public-domain paper and shredder recordings
build/              everything generated (safe to delete)
out/                the deliverables
```
