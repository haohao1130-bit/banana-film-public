#!/usr/bin/env python3
"""Manual experimental entrypoint for the independent VNext pipeline.

Example:
 python tools/film_vnext_run.py prepare --story-file story.txt --project /content/vnext/demo --picture actor.png
 python tools/film_vnext_run.py render --project /content/vnext/demo --picture actor.png
"""
import argparse
from pathlib import Path

from banana_mv import server as app
from banana_mv.film_vnext.local_adapter import prepare_local, run_h3
from banana_mv.film_vnext.pipeline import load_ready


def main():
    parser = argparse.ArgumentParser(description="Experimental whole-film-first H3 production")
    parser.add_argument("command", choices=("prepare", "render", "inspect"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--story-file")
    parser.add_argument("--picture", action="append", default=[])
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--genre", default="cinematic")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--no-chain5", action="store_true")
    args = parser.parse_args()
    if args.command == "inspect":
        manifest, prompts = load_ready(args.project)
        print(f"Ready: {manifest['title']} / {len(prompts)} segments / "
              f"{manifest['duration_ms']/1000:.3f}s; camera fallback={manifest['camera_fallback']}")
        return
    cfg = app.backend.load_config()
    if args.command == "prepare":
        if not args.story_file:
            parser.error("prepare needs --story-file")
        story = Path(args.story_file).read_text(encoding="utf-8")
        manifest = prepare_local(cfg,args.project,story,args.picture,
                                 max_seconds=args.max_seconds,genre=args.genre)
        print(f"All {manifest['clip_count']} H3 prompts sealed before filming: {args.project}")
    else:
        movie = run_h3(cfg,args.project,args.picture,
                       size=(args.width,args.height),seed=args.seed,
                       chain5=not args.no_chain5)
        print(f"Film complete: {movie}")


if __name__ == "__main__":
    main()
