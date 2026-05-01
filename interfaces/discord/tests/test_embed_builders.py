import embed_builders


def test_build_stat_embed_sets_footer_mood():
    embed = embed_builders.build_stat_embed(
        {
            "fields": {"name": "Varek", "level": 2, "ancestry": "Gnome", "class": "Rogue", "mood": "grim"},
            "stats": {},
        }
    )
    assert getattr(embed, "footer_text", "") == "Mood: grim"


def test_build_ruling_embed_declined_marker_banner():
    embed = embed_builders.build_ruling_embed(
        {
            "marker": "declined",
            "question": "q",
            "answer": "a",
            "why": "",
            "citations": [],
            "topic": "t",
        }
    )
    assert "declined" in (embed.description or "").lower() or "pf1" in (embed.description or "").lower()
