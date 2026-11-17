"""The visual direction follows the inferred motif, cover and audio profile."""
from __future__ import annotations

from scene_director import MOTIFS


def make(profile=None, cover_lum=.5, motif=""):
    profile = profile or {}
    energy = float(profile.get("energy", .5))
    hyper = "hyperpop" in (profile.get("families") or [])
    saturated = energy >= .65 or hyper
    dark = cover_lum < .24 and saturated
    return {
        "dark": dark,
        "fonts": ["Bahnschrift", "Segoe UI"] if saturated else [""],
        "card": "glass",
        "mark": "color",
        "frame": "round",
        "layout": "split",
        "pattern": "grid" if saturated else "blobs",
        "particles": MOTIFS[motif].particles if motif in MOTIFS else "dust",
        "tempo": energy,
        "pulse": .68 + energy * 1.35,
        "speed": .47 - .24 * energy,
    }
