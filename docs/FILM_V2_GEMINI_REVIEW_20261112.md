# 🍌 BANANA FILM V2｜Public Python-Owned Short Film — Gemini Code Review Handoff
**Date:** 2026-11-12 | **Status:** experimental review branch only; NOT promoted to `main`.

## Entry points
- Public repository: `haohao1130-bit/banana-film-public`
- Review branch: `film-v2-python-owned-public-20261112` (flat branch name for Google Colab)
- **Unique notebook**: `BANANA_FILM_V2_PUBLIC_GEMINI_REVIEW_20261112.ipynb`
- Public notebook URL:
  https://colab.research.google.com/github/haohao1130-bit/banana-film-public/blob/film-v2-python-owned-public-20261112/BANANA_FILM_V2_PUBLIC_GEMINI_REVIEW_20261112.ipynb
- Notebook clones the **public** repo: no private GitHub token.
- Frontend/health: port `8194`, `/api/health` must report `banana-film-v2` and engine `python_owned_film_v2`.
- Colab saved output: `MyDrive/BananaFilmV2/films_v2`, not existing `BananaFilmStudio`.
- No changes to `banana-film-public/main`, `banana-film-studio/main`, 5070 MV or VNEXT/27B.

## Architectural intention
**Old short-film code is NOT the template for story planning.** The existing 9B-led `banana_mv/film.py` has too many mixed responsibilities. The new architecture uses:
1. 9B whole-film *screenwriter*: one structured, user-reviewable screenplay with atomic events, stable cast IDs, dialogue speakers, explicit initial state, per-beat state transitions and duration hints.
2. Python *production controller*: deterministic event grouping, native H3-compatible 24-fps frame counts, scene boundaries, event identity, initial/end state snapshots, no future-plot exposure.
3. 9B *local cinematographer*: receives only this segment's commission and immutable global identities, creates official H3 six-section prompt.
4. Existing H3 *native image+audio* pipeline, Chain5 5-frame visual continuation, FFmpeg frame **and audio** overlap trim, local versioned retakes and output masters.
5. Isolated Notebook, web interface, data and project directory; stable old programs unaffected.

## Review files — recommended reading order
| File | Responsibility |
|---|---|
| `film_v2/production.py` | Pure Python ordered beat-to-clip planner, H3 grid, state ledger and current-only commission |
| `film_v2/directors.py` | Separate 9B whole-script and local-camera model prompts, response parsing / retry / 6-section validation, picture-slot translation |
| `film_v2/service.py` | Job lifecycle, approval/revision, render one clip, native H3 audio + Chain5, resume/retake/select/assemble/save |
| `film_v2/server.py` | Isolated HTTP endpoints, asset upload, status, retake, preview, video download |
| `film_v2/web/index.html`, `film_v2/web/app.js` | UI and client script review, nine stable image positions, local candidate preview / adoption |
| `tools/film_v2_runtime.py` | Colab GPU/ComfyUI startup, port 8194, Drive `BananaFilmV2` |
| `BANANA_FILM_V2_PUBLIC_GEMINI_REVIEW_20261112.ipynb` | Public Git clone, CPU tests before model download, 9B/H3 install and launch |
| `tests/test_film_v2_production.py` | 10 pure-Python contract tests |
| `tests/test_film_v2_integration.py` | 6 offline backend/H3 mock integration tests |
| `.github/workflows/film_v2_public_review.yml` | Branch-only offline CI, notebook validation and JS syntax |

## Shared hardware/transport reused, not copied
- `banana_mv/core.py`: `build_workflow(..., native_audio=True)` with MiniMax H3 Ref2VA. This is **not** a music video and does not lock audio to a song.
- `banana_mv/film_continuity.py`: `prepare_motion_tail`, `add_motion_guide`, `preflight_nodes`; five RGB tail frames.
- `banana_mv/film_media.py`: `trim_native`, `require_audio` (audio survives overlap trim).
- `banana_mv/services.py`: ComfyUI transport, 9B `rewrite_local`, assets and model configuration.
- `banana_mv/server.py`: common GPU queue, ffmpeg/H3 helpers and persistence, **not** the old film planner.
- `banana_mv/masters.py`: immutable finished-video masters.
- `tools/colab_runtime.py`: pinned ComfyUI and model installer.

Private and public main were compared before the port: shared service/core/runtime functions matched; the only differences in several files were trailing newlines. Those shared base files were **not overwritten**.

## Gemini: review priorities (please identify defects, do not assume safe)
1. **Python planner semantics:** Do events remain chronological and appear exactly once? Do duration hints, `cut_after` and the 24 fps H3 `5+17k` frame grid always give valid clips and total durations? Are dialogue lengths respected without silent compression or filler?
2. **State/identity contract:** Do `changes`, `state_at_open`, `state_at_close`, picture/subject bindings and speakers stay correct? Could an LLM put future events inside `shared_setup` and leak the ending to a local camera stage?
3. **9B parsing and retries:** Verify the real `parse_object` return shape against V2 expected JSON and the 9B output limit. Verify six-section H3 prompt, `[Shot N]`, speaker tags, image count, ambient/dialogue mode. Check that a failed model response never deletes an approved script.
4. **H3 native audio:** Confirm `MiniMaxH3ReferenceToVideo` uses the correct nodes and actual reference image count. Test `chain` and `chain5` first-frame/reference order and RGB guide wiring. Confirm each raw/trimmed clip and combined master has sound, frame count and duration.
5. **Continuation and retake:** Detect stale future clips after a previous take is changed; no implicit regeneration. Confirm H3 queued prompts, prompt reuse, stop/resume, source hashes, candidate version storage, rollback if adopting fails, final file archive integrity.
6. **Security / paths:** Public notebook must not embed credentials or clone the private repo. Check file traversal, HTTP upload limits, unauthorized job access on publicly shared Colab ports, command execution, lifecycle locks.
7. **Regression:** Run BOTH new test suites, inspect GitHub Actions logs, and (only after CPU checks) do a live short 9B/H3 480p smoke test. A mocked H3 test is not equivalent to GPU quality verification.

## Current test evidence and limitations
- The design and code were copied from the private experimental branch `film-v2-python-owned`; their GitHub file contents are rechecked after upload.
- Previously reported core tests: 10/10 and 3,000 deterministic/randomized invariants. **Treat these as reported results, not proof of integration or GPU readiness.**
- The private branch GitHub Actions runner was failing before test steps started (no logs or steps), so do **not** claim the entire backend integration suite has passed.
- New public CI workflow is independently defined and its outcome should be checked.
- **No live Colab GPU success has been demonstrated in this handoff.**
- Product is intentionally an EXPERIMENT, not a stable public release.

## Review prompt for Gemini
> Please inspect this branch's actual code (not only the README). Audit the new Python-owned V2 pipeline, especially `film_v2/service.py` and `film_v2/directors.py`, against the intended split of screenwriter/Python scheduler/local cinematographer/native H3. Identify concrete runtime failures, state/timing/audio bugs, safety issues and missing tests. Rank by severity and cite file and function/line. Do not merge into `main`. Propose minimal corrections only on this experiment branch and provide runnable regression tests before any GPU smoke test.
