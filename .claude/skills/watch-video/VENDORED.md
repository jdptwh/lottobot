Vendored from https://github.com/Newuxtreme/watch-video-skill
Pinned commit: 16313155ba87c22397ed20634766cb0606e2dbaa
Date: 2026-07-09
License: MIT (see LICENSE; bundled scripts per THIRD_PARTY_NOTICES.md)

Local modifications (keep this list current):
- SKILL.md `description:` + "When to invoke" — upstream ships SLASH-COMMAND-ONLY;
  the harness additionally allows deliberate invocation when a task explicitly
  requires frame-level video analysis (visual QA of generated video, absorbing
  reference footage). Casual-mention auto-triggering remains forbidden. (Upstream
  documents the description line as the intended customization point.)
