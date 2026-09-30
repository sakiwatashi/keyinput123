"""自動完成的提示要夠有把握才出現，而且只補大家都同意的那一段。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.completion_store import (
    MAX_ENTRIES,
    MIN_USES,
    TRIM_TO,
    CompletionStore,
    autocomplete_enabled,
)

READINGS = {
    "謝": "ㄒㄧㄝˋ", "您": "ㄋㄧㄣˊ", "的": "ㄉㄜ˙", "協": "ㄒㄧㄝˊ", "助": "ㄓㄨˋ",
    "喔": "ㄛ", "好": "ㄏㄠˇ", "你": "ㄋㄧˇ", "長": "ㄓㄤˇ", "大": "ㄉㄚˋ",
    "度": "ㄉㄨˋ", "很": "ㄏㄣˇ", "高": "ㄍㄠ", "了": "ㄌㄜ˙", "我": "ㄨㄛˇ",
    "們": "ㄇㄣ˙", "明": "ㄇㄧㄥˊ", "天": "ㄊㄧㄢ", "見": "ㄐㄧㄢˋ",
}


def readings_of(text: str) -> list[str]:
    return [READINGS[character] for character in text]


class CompletionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "completions.json"
        self.store = CompletionStore(self.path)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def commit(self, text: str, times: int = 1) -> None:
        for _ in range(times):
            self.store.record(readings_of(text), text)

    def suggest(self, typed: str):
        return self.store.suggest(readings_of(typed), list(typed))

    def test_suggests_after_enough_uses(self) -> None:
        self.commit("謝謝您的協助", MIN_USES)
        self.assertEqual(self.suggest("謝謝"), ("您的協助", readings_of("您的協助")))

    def test_one_use_short_of_the_threshold_suggests_nothing(self) -> None:
        # 門檻本身要能擋住東西，不然 MIN_USES 改成 1 這支測試也不會紅。
        self.commit("謝謝您的協助", MIN_USES - 1)
        self.assertIsNone(self.suggest("謝謝"))

    def test_counts_add_up_across_different_sentences(self) -> None:
        # 三句不同的話都含「謝謝您的協助」，就算用過三次。
        self.commit("好的謝謝您的協助")
        self.commit("謝謝您的協助喔")
        self.commit("我們謝謝您的協助")
        self.assertEqual(self.suggest("謝謝")[0], "您的協助")

    def test_stops_where_the_sentences_stop_agreeing(self) -> None:
        self.commit("謝謝您的協助", MIN_USES - 1)
        self.commit("謝謝您的協助喔", 1)
        # 三次都同意「您的協助」，只有一次接了「喔」。
        self.assertEqual(self.suggest("謝謝")[0], "您的協助")

    def test_a_single_character_of_context_is_not_enough(self) -> None:
        self.commit("謝謝您的協助", MIN_USES + 5)
        self.assertIsNone(self.suggest("謝"))

    def test_a_single_character_completion_is_not_offered(self) -> None:
        # 只補一個字省不到按鍵，卻多一個提示框要看。
        self.commit("我們好", MIN_USES + 5)
        self.assertIsNone(self.suggest("我們"))

    def test_the_context_has_to_be_at_the_end_of_what_was_typed(self) -> None:
        self.commit("謝謝您的協助", MIN_USES)
        # 「謝謝」出現在中間，但結尾是「好」，後面接什麼不知道。
        self.assertIsNone(self.suggest("謝謝好"))

    def test_same_characters_with_different_readings_do_not_match(self) -> None:
        # 「長大」的長唸 ㄓㄤˇ，「長度」的長唸 ㄔㄤˊ。同樣的字，不同的線索。
        for _ in range(MIN_USES):
            self.store.record(
                ["ㄔㄤˊ", "ㄉㄨˋ", "ㄏㄣˇ", "ㄍㄠ"], "長度很高"
            )
        self.assertIsNone(
            self.store.suggest(["ㄓㄤˇ", "ㄉㄨˋ"], ["長", "度"])
        )
        self.assertEqual(
            self.store.suggest(["ㄔㄤˊ", "ㄉㄨˋ"], ["長", "度"])[0], "很高"
        )

    def test_longer_context_wins_over_shorter(self) -> None:
        # 只看「明天」兩個字，兩句一樣多、分不出來；看到「你們明天」「我們明天」
        # 才知道各自後面接什麼。
        self.commit("你們明天見了", MIN_USES)
        self.commit("我們明天好的", MIN_USES)
        self.assertEqual(self.suggest("你們明天")[0], "見了")
        self.assertEqual(self.suggest("我們明天")[0], "好的")

    def test_falls_back_to_a_shorter_context(self) -> None:
        # 長線索沒有對得上的句子時，退回最後兩個字。
        self.commit("明天見了", MIN_USES)
        self.assertEqual(self.suggest("我們明天")[0], "見了")

    def test_survives_a_damaged_file(self) -> None:
        self.path.write_text("{ not json", encoding="utf-8")
        store = CompletionStore(self.path)
        self.assertEqual(len(store), 0)

    def test_skips_entries_whose_readings_do_not_line_up(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": {
                        "謝謝您的協助": {"r": ["ㄒㄧㄝˋ"], "n": 9, "last": 0},
                        "好的謝謝你": {"r": readings_of("好的謝謝你"), "n": 9, "last": 0},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        store = CompletionStore(self.path)
        self.assertEqual(len(store), 1)

    def test_round_trips_through_the_file(self) -> None:
        self.commit("謝謝您的協助", MIN_USES)
        self.store.flush(force=True)
        reloaded = CompletionStore(self.path)
        self.assertEqual(
            reloaded.suggest(readings_of("謝謝"), list("謝謝"))[0], "您的協助"
        )

    def test_stays_bounded(self) -> None:
        for index in range(MAX_ENTRIES + 1):
            # 每筆文字都不同；讀音內容不重要，長度對得上就好。
            text = "謝謝" + chr(0x4E00 + index)
            self.store.record(["ㄒㄧㄝˋ", "ㄒㄧㄝˋ", "ㄧ"], text + "好")
        self.store.flush(force=True)
        self.assertLessEqual(len(self.store), TRIM_TO)


class AutocompletePreferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "autocomplete.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_on_when_the_file_is_missing(self) -> None:
        self.assertTrue(autocomplete_enabled(str(self.path)))

    def test_off_only_when_explicitly_false(self) -> None:
        self.path.write_text('{"enabled": false}', encoding="utf-8")
        self.assertFalse(autocomplete_enabled(str(self.path)))

    def test_reads_a_file_written_with_a_bom(self) -> None:
        # Windows PowerShell 寫的檔帶 BOM；讀不懂就會默默回到預設（開啟），
        # 使用者關掉的開關等於沒關。
        self.path.write_bytes(b"\xef\xbb\xbf" + b'{"enabled": false}')
        self.assertFalse(autocomplete_enabled(str(self.path)))

    def test_a_damaged_file_means_default(self) -> None:
        self.path.write_text("{", encoding="utf-8")
        self.assertTrue(autocomplete_enabled(str(self.path)))


if __name__ == "__main__":
    unittest.main()
