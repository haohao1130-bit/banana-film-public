"""VNext-specific five-frame motion guide for H3 Audio T8 native AV graph.

Kept independent of legacy motion director. The source continuity helpers
are still used to extract real RGB tail frames.
"""


def add_audio_t8_motion_guide(graph, names, delivered_frames):
    from banana_mv.film_continuity import render_frames, CONTEXT_FRAMES
    if len(names) != CONTEXT_FRAMES or len(set(names)) != CONTEXT_FRAMES:
        raise ValueError("VNext 末五幀必須包含五張不同影格。")
    if graph.get("7", {}).get("class_type") != "MiniMaxH3AudioConditioningT8":
        raise ValueError("VNext 只支援原生 H3 Audio T8 連續性。")
    if "17" in graph:
        raise ValueError("末五幀不能同時使用首幀鎖定。")
    graph["7"]["inputs"]["length"] = render_frames(delivered_frames)
    for i, name in enumerate(names):
        graph[f"motion_frame_{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
    batch = ["motion_frame_0", 0]
    for i in range(1, CONTEXT_FRAMES):
        key = f"motion_batch_{i}"
        graph[key] = {"class_type": "ImageBatch",
                      "inputs": {"image1": batch, "image2": [f"motion_frame_{i}", 0]}}
        batch = [key, 0]
    graph["motion_guide"] = {"class_type": "MiniMaxH3AddGuide",
                            "inputs": {"positive": ["7", 0], "latent": ["7", 1],
                                       "vae": ["3", 0], "image": batch, "frame_idx": 0}}
    graph["9"]["inputs"]["conditioning"] = ["motion_guide", 0]
    return graph
