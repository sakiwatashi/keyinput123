import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core.sync import (
    CONTEXTS_NAME,
    HIDDEN_NAME,
    PHRASES_NAME,
    PINS_NAME,
    USAGE_NAME,
    WORD_USAGE_NAME,
    merge_contexts,
    merge_hidden,
    merge_phrases,
    merge_pins,
    merge_usage,
    merge_word_usage,
    sync_directories,
)


class MergeUsageTests(unittest.TestCase):
    def test_takes_the_larger_count_rather_than_the_sum(self) -> None:
        # Summing is the tempting merge. It is wrong because sync runs on a
        # schedule: the same remote snapshot arrives again and again, and a
        # summed count grows without bound until that entry outranks
        # everything the user actually types.
        local = {"寫程式": {"n": 7, "last": 100}}
        remote = {"寫程式": {"n": 4, "last": 250}}

        merged = merge_usage(local, remote)

        self.assertEqual({"n": 7, "last": 250}, merged["寫程式"])

    def test_merging_the_same_remote_twice_changes_nothing(self) -> None:
        local = {"測試": {"n": 3, "last": 10}}
        remote = {"測試": {"n": 5, "last": 20}, "同步": {"n": 1, "last": 30}}

        once = merge_usage(local, remote)
        twice = merge_usage(once, remote)

        self.assertEqual(once, twice)

    def test_damaged_entries_do_not_stop_the_merge(self) -> None:
        merged = merge_usage({"壞": "not a dict"}, {"壞": {"n": 2, "last": 5}})
        self.assertEqual({"n": 2, "last": 5}, merged["壞"])


class MergePhrasesTests(unittest.TestCase):
    def test_remote_only_entries_are_added(self) -> None:
        merged = merge_phrases({"ㄕㄨˋ ㄧㄝˋ": "樹葉"}, {"ㄍㄨㄥ ㄕˋ": "公式"})
        self.assertEqual({"ㄕㄨˋ ㄧㄝˋ": "樹葉", "ㄍㄨㄥ ㄕˋ": "公式"}, merged)

    def test_conflict_without_usage_evidence_keeps_the_local_value(self) -> None:
        merged = merge_phrases({"ㄍㄨㄥ ㄕˋ": "公式"}, {"ㄍㄨㄥ ㄕˋ": "公事"})
        self.assertEqual("公式", merged["ㄍㄨㄥ ㄕˋ"])

    def test_conflict_is_decided_by_how_much_each_string_is_used(self) -> None:
        # The laptop learned 公事 and uses it constantly; the desktop learned
        # 公式 once. Without this the merge would keep whichever side happened
        # to be local, which is how a sync quietly undoes real learning.
        usage = {"公式": {"n": 1, "last": 10}, "公事": {"n": 40, "last": 90}}

        merged = merge_phrases(
            {"ㄍㄨㄥ ㄕˋ": "公式"}, {"ㄍㄨㄥ ㄕˋ": "公事"}, usage
        )

        self.assertEqual("公事", merged["ㄍㄨㄥ ㄕˋ"])

    def test_conflicts_are_reported_not_silent(self) -> None:
        from bopomofo_core.sync import MergeReport

        report = MergeReport()
        merge_phrases({"ㄍㄨㄥ ㄕˋ": "公式"}, {"ㄍㄨㄥ ㄕˋ": "公事"}, {}, report)

        self.assertEqual(1, len(report.conflicts))
        self.assertEqual("公式", report.conflicts[0].kept)
        self.assertEqual("公事", report.conflicts[0].dropped)

    def test_merge_never_drops_an_entry_either_side_knew(self) -> None:
        local = {f"reading-{i}": f"字{i}" for i in range(50)}
        remote = {f"reading-{i}": f"字{i}" for i in range(25, 75)}

        merged = merge_phrases(local, remote)

        self.assertEqual(75, len(merged))
        for key in set(local) | set(remote):
            self.assertIn(key, merged)


class MergePinsTests(unittest.TestCase):
    def test_local_order_survives_and_remote_pins_are_appended(self) -> None:
        merged = merge_pins({"ㄗˋ": ["字", "自"]}, {"ㄗˋ": ["自", "漬"]})
        self.assertEqual(["字", "自", "漬"], merged["ㄗˋ"])

    def test_readings_only_the_remote_knows_are_carried_over(self) -> None:
        merged = merge_pins({}, {"ㄕˋ": ["是"]})
        self.assertEqual(["是"], merged["ㄕˋ"])

    def test_merging_twice_does_not_duplicate_pins(self) -> None:
        remote = {"ㄗˋ": ["自", "漬"]}
        once = merge_pins({"ㄗˋ": ["字"]}, remote)
        twice = merge_pins(once, remote)
        self.assertEqual(once, twice)


class MergeHiddenTests(unittest.TestCase):
    def test_an_explicit_keep_on_either_machine_beats_a_hide_on_the_other(self) -> None:
        # is_hidden() checks always_show first, so unioning both lists resolves
        # this pair towards showing the character. Being unable to type a
        # character is a worse failure than seeing one too many.
        merged = merge_hidden(
            {"hidden": ["恣"], "always_show": []},
            {"hidden": [], "always_show": ["恣"]},
        )
        self.assertIn("恣", merged["hidden"])
        self.assertIn("恣", merged["always_show"])

    def test_local_frequency_floor_wins(self) -> None:
        merged = merge_hidden({"minimum_frequency": 7}, {"minimum_frequency": 3})
        self.assertEqual(7, merged["minimum_frequency"])

    def test_unset_local_floor_adopts_the_remote_setting(self) -> None:
        merged = merge_hidden({}, {"minimum_frequency": 5})
        self.assertEqual(5, merged["minimum_frequency"])

    def test_fields_this_merge_does_not_understand_are_kept(self) -> None:
        # 實測：合併把控制台寫進 hidden-characters.json 的 "version" 洗掉了，
        # 因為原本的實作直接回傳一個只含三個已知鍵的新字典。同步不該擅自認定
        # 哪些欄位沒有用——那是寫進去的那支程式才知道的事。
        merged = merge_hidden(
            {"version": 1, "hidden": ["恣"], "note": "本機的"},
            {"version": 1, "hidden": ["孳"], "future_flag": True},
        )
        self.assertEqual(1, merged["version"])
        self.assertEqual("本機的", merged["note"])
        self.assertTrue(merged["future_flag"])
        self.assertEqual(["孳", "恣"], merged["hidden"])


class MergeContextsTests(unittest.TestCase):
    def test_the_same_reading_after_different_characters_both_survive(self) -> None:
        # 兩台機器學到的是同一個讀音的不同鄰居，本來就沒有衝突可言。
        merged = merge_contexts(
            {"ㄔㄥˊ ㄕˋ": {"座": "城市"}},
            {"ㄔㄥˊ ㄕˋ": {"寫": "程式"}},
        )
        self.assertEqual({"座": "城市", "寫": "程式"}, merged["ㄔㄥˊ ㄕˋ"])

    def test_same_reading_same_context_is_settled_by_usage(self) -> None:
        usage = {"城市": {"n": 1, "last": 5}, "程式": {"n": 40, "last": 90}}
        merged = merge_contexts(
            {"ㄔㄥˊ ㄕˋ": {"寫": "城市"}},
            {"ㄔㄥˊ ㄕˋ": {"寫": "程式"}},
            usage,
        )
        self.assertEqual("程式", merged["ㄔㄥˊ ㄕˋ"]["寫"])

    def test_without_usage_evidence_the_local_choice_stays(self) -> None:
        merged = merge_contexts(
            {"ㄔㄥˊ ㄕˋ": {"寫": "城市"}}, {"ㄔㄥˊ ㄕˋ": {"寫": "程式"}}
        )
        self.assertEqual("城市", merged["ㄔㄥˊ ㄕˋ"]["寫"])

    def test_merging_twice_changes_nothing(self) -> None:
        remote = {"ㄔㄥˊ ㄕˋ": {"寫": "程式"}}
        once = merge_contexts({"ㄔㄥˊ ㄕˋ": {"座": "城市"}}, remote)
        twice = merge_contexts(once, remote)
        self.assertEqual(once, twice)

    def test_damaged_entries_do_not_stop_the_merge(self) -> None:
        merged = merge_contexts(
            {"ㄔㄥˊ ㄕˋ": "not a dict"}, {"ㄔㄥˊ ㄕˋ": {"寫": "程式"}}
        )
        self.assertEqual({"寫": "程式"}, merged["ㄔㄥˊ ㄕˋ"])


class MergeWordUsageTests(unittest.TestCase):
    def test_takes_the_larger_count(self) -> None:
        merged = merge_word_usage(
            {"ㄧˉ ㄅㄨˋ": {"一步": 7}}, {"ㄧˉ ㄅㄨˋ": {"一步": 4, "一部": 2}}
        )
        self.assertEqual({"一步": 7, "一部": 2}, merged["ㄧˉ ㄅㄨˋ"])

    def test_merging_twice_changes_nothing(self) -> None:
        remote = {"ㄧˉ ㄅㄨˋ": {"一步": 4}}
        once = merge_word_usage({"ㄧˉ ㄅㄨˋ": {"一步": 7}}, remote)
        self.assertEqual(once, merge_word_usage(once, remote))

    def test_damaged_entries_do_not_stop_the_merge(self) -> None:
        merged = merge_word_usage({"ㄧˉ ㄅㄨˋ": "壞的"}, {"ㄧˉ ㄅㄨˋ": {"一步": 3}})
        self.assertEqual({"一步": 3}, merged["ㄧˉ ㄅㄨˋ"])


class SyncDirectoriesTests(unittest.TestCase):
    def _write(self, root: Path, name: str, value) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )

    def test_both_sides_converge_on_the_same_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "state"
            shared = Path(temp_dir) / "shared"
            self._write(state, PHRASES_NAME, {"ㄕㄨˋ ㄧㄝˋ": "樹葉"})
            self._write(shared, PHRASES_NAME, {"ㄍㄨㄥ ㄕˋ": "公式"})

            sync_directories(state, shared)

            local = json.loads((state / PHRASES_NAME).read_text(encoding="utf-8"))
            remote = json.loads((shared / PHRASES_NAME).read_text(encoding="utf-8"))
            self.assertEqual(local, remote)
            self.assertEqual({"ㄕㄨˋ ㄧㄝˋ": "樹葉", "ㄍㄨㄥ ㄕˋ": "公式"}, local)

    def test_running_sync_again_reports_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "state"
            shared = Path(temp_dir) / "shared"
            self._write(state, PHRASES_NAME, {"ㄕㄨˋ ㄧㄝˋ": "樹葉"})
            self._write(shared, PHRASES_NAME, {"ㄍㄨㄥ ㄕˋ": "公式"})
            self._write(shared, USAGE_NAME, {"version": 1, "counts": {"公式": {"n": 2, "last": 5}}})

            first = sync_directories(state, shared)
            second = sync_directories(state, shared)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)

    def test_dry_run_reports_without_touching_either_side(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "state"
            shared = Path(temp_dir) / "shared"
            self._write(state, PHRASES_NAME, {"ㄕㄨˋ ㄧㄝˋ": "樹葉"})
            self._write(shared, PHRASES_NAME, {"ㄍㄨㄥ ㄕˋ": "公式"})

            report = sync_directories(state, shared, dry_run=True)

            self.assertTrue(report.changed)
            self.assertEqual(
                {"ㄕㄨˋ ㄧㄝˋ": "樹葉"},
                json.loads((state / PHRASES_NAME).read_text(encoding="utf-8")),
            )
            self.assertFalse((state / PINS_NAME).exists())

    def test_two_machines_end_byte_identical_not_merely_equal(self) -> None:
        # The two sides of one sync run are written from the same dict, so they
        # match whatever the key order is -- comparing those proves nothing.
        # Two machines reaching the same content by different merge paths is
        # the case that actually diverges: each ends up with the same entries
        # in a different order. Same content, different bytes still shows up as
        # a change in the shared folder's git history and defeats
        # backup_user_data.ps1's fingerprint check, so every sync spawns a
        # redundant archive.
        with tempfile.TemporaryDirectory() as temp_dir:
            desk = Path(temp_dir) / "desk"
            lap = Path(temp_dir) / "lap"
            shared = Path(temp_dir) / "shared"
            self._write(desk, PHRASES_NAME, {"ㄗ ㄅ": "自B", "ㄚ ㄅ": "阿B"})
            self._write(lap, PHRASES_NAME, {"ㄇ ㄅ": "馬B"})

            sync_directories(desk, shared)
            sync_directories(lap, shared)
            sync_directories(desk, shared)

            for name in (
                PHRASES_NAME,
                PINS_NAME,
                USAGE_NAME,
                HIDDEN_NAME,
                CONTEXTS_NAME,
                WORD_USAGE_NAME,
            ):
                self.assertEqual(
                    (desk / name).read_bytes(), (lap / name).read_bytes(), name
                )

    def test_written_json_carries_no_bom(self) -> None:
        # PIMELauncher dies without a word when it hits a BOM in a JSON file,
        # and the control panel is PowerShell, which adds one by default.
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "state"
            shared = Path(temp_dir) / "shared"
            self._write(state, PHRASES_NAME, {"ㄕㄨˋ ㄧㄝˋ": "樹葉"})

            sync_directories(state, shared)

            for name in (
                PHRASES_NAME,
                PINS_NAME,
                USAGE_NAME,
                HIDDEN_NAME,
                CONTEXTS_NAME,
                WORD_USAGE_NAME,
            ):
                for root in (state, shared):
                    head = (root / name).read_bytes()[:3]
                    self.assertNotEqual(b"\xef\xbb\xbf", head, f"{root.name}/{name}")

    def test_an_empty_shared_folder_seeds_itself_from_the_machine(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "state"
            shared = Path(temp_dir) / "shared"
            self._write(state, PHRASES_NAME, {"ㄕㄨˋ ㄧㄝˋ": "樹葉"})

            report = sync_directories(state, shared)

            self.assertEqual(
                {"ㄕㄨˋ ㄧㄝˋ": "樹葉"},
                json.loads((shared / PHRASES_NAME).read_text(encoding="utf-8")),
            )
            # 這一趟什麼都沒流進本機，但它把整份個人詞庫推了出去。只計算流入
            # 方向的報告會在這裡說「兩邊已經一致，沒有東西需要合併」——正好
            # 是在它做最多事的那一次告訴使用者它什麼都沒做。
            self.assertTrue(report.changed)
            self.assertEqual(1, report.pushed[PHRASES_NAME])
            self.assertEqual({}, report.added)


if __name__ == "__main__":
    unittest.main()
