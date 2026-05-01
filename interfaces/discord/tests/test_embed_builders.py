import embed_builders


def test_build_foundry_roll_embed_has_title_and_footer():
    embed = embed_builders.build_foundry_roll_embed(
        {
            "outcome": "success",
            "actor_name": "Varek",
            "target_name": "Goblin",
            "roll_total": 18,
            "dc": 16,
        }
    )
    assert "Varek" in (embed.title or "")
    assert "Roll:" in (getattr(embed, "footer_text", "") or "")


def test_build_session_embed_log_type_title():
    embed = embed_builders.build_session_embed({"type": "log", "line": "x"})
    assert embed.title == "Event logged"


def test_build_harvest_embed_sets_title():
    embed = embed_builders.build_harvest_embed({"monsters": [], "aggregated": [], "footer": ""})
    assert "Harvest report" in (embed.title or "")


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
