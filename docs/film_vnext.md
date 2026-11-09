# Film VNext — independent whole-film-first production (experimental)

This is a **new production path**, not a patch to the old `film.py` worker.
The old film and MV workflows remain unchanged.

## Contract and order

1. **Screenwriter**: one local 9B call writes a complete screenplay as JSON, including every chronological beat, every segment's opening/outgoing state, actor identity, actual speaker roles, and the final outcome.
2. **Camera director**: one local 9B call reads the *complete validated screenplay* and returns camera-only JSON for **all** segments. Camera fields are fixed enums (shot size, angle, motion, framing, lighting) plus cut times. No model-authored event prose is accepted.
3. **Compiler**: Python maps each upstream beat into its scheduled shot, creates native six-field MiniMax H3 prompt text for every segment, and seals every file with SHA-256 in `ready.json`.
4. **Renderer**: reads all sealed prompts, uses native H3, optional last-five-frame motion continuation, native sound and durable per-clip progress, then joins the movie. **No 9B/model calls occur while filming.**

For a three-minute script the engine prepares every segment before any H3 queue operation. A 180-second request is a **maximum**, not a mandatory story length. Narrative timing is aligned to H3's 24fps, 5+17k frame grid **before** camera planning; resulting actual duration can be shorter than originally requested.

## Manual experimental run (after starting and configuring ComfyUI)

From repository root:

```bash
python -m tools.film_vnext_run prepare --project /content/film-vnext/demo --story-file story.txt --picture xiaoyu.png --picture master.png
python -m tools.film_vnext_run inspect --project /content/film-vnext/demo
python -m tools.film_vnext_run render --project /content/film-vnext/demo --picture xiaoyu.png --picture master.png
```

The order of `--picture` flags is the authoritative `<Picture N>` mapping.

## Independent modules

- `pipeline.py`: complete-story schema, one-pass camera JSON contract, canonical H3 compiler and sealed manifest.
- `renderer.py`: resumable sealed-prompt rendering only; no model or camera writer.
- `local_adapter.py`: connects local 9B + existing low-level H3 media and five-frame motion tools; does not import the old film director or writer.
- `tools/film_vnext_run.py`: explicit CLI entrypoint separate from the old mobile interface.

## Validation and limitations

- Unit tests: `python -m unittest discover -s tests -p 'test_film_vnext.py' -v`.
- The included tests mock 9B and H3: 18 clips, camera-authority isolation, legal timing, authorized voices, immutable prompt hashes and render resume.
- **These are not proof of real 9B's ability to return a whole 180-second script**, nor of H3 image or motion quality. A real local-model dry run must precede any production rollout.
- An incomplete camera JSON response triggers a **marked** deterministic photographic fallback. It does not substitute new narrative events, but visual quality may be less dynamic.
- The experimental CLI is deliberately **not** wired into the old Film Studio UI/start endpoint; no existing job is migrated.
- VNext doesn't currently support creative script-editing UI or retake-version selection. Do not replace production with it until those features and GPU results are accepted.
- The sealed manifest prevents accidental prompt modification; it does not prove AI interpretation of original human story intent is perfect.
