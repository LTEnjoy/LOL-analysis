#!/usr/bin/env python3
"""Unit tests for lcu_sync.map_game: mode filtering and win-value mapping."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lcu_sync  # noqa: E402

CHAMPS = {1: "测试英雄"}
CREATED_MS = 1700000000000


def make_detail(teams=None, winning_team=None, count=10, names=None):
    participants = []
    identities = []
    for index in range(count):
        team_id = 100 if index < 5 else 200
        participant_id = index + 1
        participants.append({
            "participantId": participant_id,
            "teamId": team_id,
            "championId": 1,
            "stats": {
                "kills": index,
                "deaths": 1,
                "assists": 2,
                "win": team_id == winning_team,
                "goldEarned": 10000 + index * 100,
                "visionScore": 20 + index,
                "timeCCingOthers": index * 2,
            },
            "timeline": {"lane": "MIDDLE", "role": "SOLO"},
        })
        name = names[index] if names else f"P{index}"
        identities.append({
            "participantId": participant_id,
            "player": {"gameName": name, "puuid": f"puuid-{index}"},
        })
    detail = {
        "gameType": "CUSTOM_GAME",
        "queueId": 3110,
        "mapId": 11,
        "gameMode": "CLASSIC",
        "gameId": 12345,
        "gameCreation": CREATED_MS,
        "gameDuration": 1800,
        "participants": participants,
        "participantIdentities": identities,
    }
    if teams is not None:
        detail["teams"] = teams
    return detail


class MapGameTest(unittest.TestCase):
    def test_win_string_blue(self):
        game, err = lcu_sync.map_game(
            make_detail(teams=[{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}]),
            CHAMPS, False,
        )
        self.assertEqual(err, "")
        self.assertEqual(game["winner"], "blue")

    def test_win_string_red(self):
        game, err = lcu_sync.map_game(
            make_detail(teams=[{"teamId": 100, "win": "Fail"}, {"teamId": 200, "win": "Win"}]),
            CHAMPS, False,
        )
        self.assertEqual(err, "")
        self.assertEqual(game["winner"], "red")

    def test_boolean_teams(self):
        game, _ = lcu_sync.map_game(
            make_detail(teams=[{"teamId": 100, "win": False}, {"teamId": 200, "win": True}]),
            CHAMPS, False,
        )
        self.assertEqual(game["winner"], "red")

    def test_stats_fallback(self):
        game, _ = lcu_sync.map_game(make_detail(winning_team=200), CHAMPS, False)
        self.assertEqual(game["winner"], "red")

    def test_missing_winner(self):
        game, err = lcu_sync.map_game(
            make_detail(teams=[{"teamId": 100, "win": "Fail"}, {"teamId": 200, "win": "Fail"}]),
            CHAMPS, False,
        )
        self.assertIsNone(game)
        self.assertEqual(err, "missing-winner")

    def test_not_5v5(self):
        game, err = lcu_sync.map_game(make_detail(count=9, winning_team=100), CHAMPS, False)
        self.assertIsNone(game)
        self.assertEqual(err, "not-5v5")

    def test_unbalanced_teams_rejected(self):
        detail = make_detail(winning_team=100)
        detail["participants"] = detail["participants"][:8]
        detail["participantIdentities"] = detail["participantIdentities"][:8]
        game, err = lcu_sync.map_game(detail, CHAMPS, False)
        self.assertIsNone(game)
        self.assertEqual(err, "not-5v5")

    def test_hextech_aram_rejected(self):
        detail = make_detail(winning_team=100)
        detail.update({"queueId": 3270, "mapId": 12, "gameMode": "KIWI"})
        game, err = lcu_sync.map_game(detail, CHAMPS, False)
        self.assertIsNone(game)
        self.assertEqual(err, "not-summoners-rift")

    def test_non_classic_mode_rejected(self):
        detail = make_detail(winning_team=100)
        detail.update({"queueId": 3140, "gameMode": "PRACTICETOOL"})
        game, err = lcu_sync.map_game(detail, CHAMPS, False)
        self.assertIsNone(game)
        self.assertEqual(err, "not-summoners-rift")

    def test_missing_map_rejected(self):
        detail = make_detail(winning_team=100)
        del detail["mapId"]
        game, err = lcu_sync.map_game(detail, CHAMPS, False)
        self.assertIsNone(game)
        self.assertEqual(err, "not-summoners-rift")

    def test_duplicate_names(self):
        names = [f"P{i}" for i in range(10)]
        names[9] = names[0]
        game, err = lcu_sync.map_game(make_detail(winning_team=100, names=names), CHAMPS, False)
        self.assertIsNone(game)
        self.assertEqual(err, "duplicate-name")

    def test_positions_optional(self):
        detail = make_detail(winning_team=100)
        game, _ = lcu_sync.map_game(detail, CHAMPS, False)
        self.assertEqual(game["participants"][0]["position"], "")
        game, _ = lcu_sync.map_game(detail, CHAMPS, True)
        self.assertEqual(game["participants"][0]["position"], "中单")

    def test_participant_mapping(self):
        game, _ = lcu_sync.map_game(make_detail(winning_team=100), CHAMPS, False)
        first = game["participants"][0]
        self.assertEqual(first["name"], "P0")
        self.assertEqual(first["team"], "blue")
        self.assertEqual(first["champion"], "测试英雄")
        self.assertEqual((first["kills"], first["deaths"], first["assists"]), (0, 1, 2))
        self.assertRegex(game["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(game["gameId"], 12345)

    def test_rating_fields_passed_through(self):
        game, _ = lcu_sync.map_game(make_detail(winning_team=100), CHAMPS, False)
        p = game["participants"][7]
        self.assertEqual(p["goldEarned"], 10700)
        self.assertEqual(p["visionScore"], 27)
        self.assertEqual(p["timeCCingOthers"], 14)
        self.assertNotIn("totalMinionsKilled", p)  # absent source field is omitted
        self.assertNotIn("win", p)

    def test_negative_and_invalid_stats_clamped(self):
        detail = make_detail(winning_team=100)
        detail["participants"][0]["stats"].update({"goldEarned": -5, "visionScore": "abc", "timeCCingOthers": None})
        game, _ = lcu_sync.map_game(detail, CHAMPS, False)
        p = game["participants"][0]
        self.assertEqual(p["goldEarned"], 0)
        self.assertEqual(p["visionScore"], 0)
        self.assertEqual(p["timeCCingOthers"], 0)


if __name__ == "__main__":
    unittest.main()
