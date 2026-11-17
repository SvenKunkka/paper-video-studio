# Browser media export dependency

The frame-based browser exporter uses **Mediabunny 1.66.0** by Vanilagy.

- Source and release: https://github.com/Vanilagy/mediabunny/tree/v1.66.0
- License: Mozilla Public License 2.0 (MPL-2.0).
- The upstream library files are used without source modifications and bundled with this application's browser output. The corresponding library source is available at the versioned source link above and in the exact npm package pinned in `web/package-lock.json`.
- A copy of the license is distributed at `vendor/licenses/MEDIABUNNY-MPL-2.0.txt` in the built website and in the repository under `web/vendor/licenses/`.

The application's own code remains under its project GPL-3.0 license. Browser-provided WebCodecs, canvas, and audio APIs are system components. Chinese TTS has separate notices in `THIRD_PARTY_TTS.md`.

The three-dimensional paper-film renderer uses **Three.js 0.187.0**, an unmodified MIT-licensed dependency. Its corresponding source is available at https://github.com/mrdoob/three.js/tree/r187 and in the exact npm package pinned in `web/package-lock.json`. A copy of its copyright and license notice is distributed at `vendor/licenses/THREE-MIT.txt`. Paper motion, procedural sound effects, poster layout and the browser scene implementation in this project are original extensions inspired by the credited upstream Blender template; they are not a Blender render or a claim of identical rendering quality.
