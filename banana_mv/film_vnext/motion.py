"""VNext five-frame motion continuation on the native H3 Ref2VA graph.

The local H3 renderer uses build_workflow(native_audio=True), which emits
MiniMaxH3ReferenceToVideo, NOT MiniMaxH3AudioConditioningT8.
Reuse the existing production Ref2VA guide builder so VNext and the
legacy one-click film agree on graph node types and VAE connections.
No director or scene-writing code is imported from the legacy film.
"""

from banana_mv.film_continuity import add_motion_guide


def add_audio_t8_motion_guide(graph, names, delivered_frames):
    """Compatibility name for the existing VNext renderer.

    Despite the historical function name, native H3 Ref2VA is the actual
    graph contract. See core.build_workflow(native_audio=True).
    """
    return add_motion_guide(graph, names, delivered_frames)
