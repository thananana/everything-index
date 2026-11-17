import tempfile
import unittest
from pathlib import Path

from everything_index.store import Index


class MasterIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = Index(self.root)

    def tearDown(self):
        self.index.db.close()
        self.tmp.cleanup()

    def text_of(self, thing_id):
        return self.index.get(thing_id)["text"]

    def test_ids_count_up_in_order_of_ingestion(self):
        self.assertEqual(self.index.ingest_text("a"), (1, True))
        self.assertEqual(self.index.ingest_text("b"), (2, True))

    def test_same_content_is_the_same_thing(self):
        self.index.ingest_text("hello")
        count = self.index.count()  # the word and its four distinct letters
        self.assertEqual(count, 5)
        self.assertEqual(self.index.ingest_text("hello"), (1, False))
        self.assertEqual(self.index.count(), count)

    def test_time_is_recorded(self):
        self.index.ingest_text("hello")
        self.assertRegex(self.index.get(1)["time"], r"^\d{4}-\d\d-\d\dT")

    def test_a_name_is_equivalent_to_its_id(self):
        self.index.ingest_text("hello", name="greeting")
        self.assertEqual(self.index.resolve("greeting"), 1)
        self.assertEqual(self.index.resolve("1"), 1)
        self.assertEqual(self.index.get(1)["names"], ["greeting"])

    def test_a_name_cannot_point_at_two_things(self):
        self.index.ingest_text("a", name="x")
        with self.assertRaises(ValueError):
            self.index.ingest_text("b", name="x")
        self.assertEqual(self.index.count(), 1)  # the failed one took no ID
        self.index.db.close()
        self.index = Index(self.root)
        self.assertEqual(self.index.ingest_text("b"), (2, True))

    def test_a_name_cannot_look_like_an_id(self):
        self.index.ingest_text("one")
        with self.assertRaises(ValueError):
            self.index.name(1, "42")

    def test_naming_an_existing_thing_on_reingest(self):
        self.index.ingest_text("one")
        self.assertEqual(self.index.ingest_text("one", name="uno"), (1, False))
        self.assertEqual(self.index.resolve("uno"), 1)

    def test_files_that_are_not_text(self):
        image = self.root / "dot.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
        thing_id, is_new = self.index.ingest_file(image)
        thing = self.index.get(thing_id)
        self.assertEqual(thing["kind"], "image/png")
        self.assertEqual(thing["source"], "dot.png")
        self.assertEqual(self.index.content(thing_id), image.read_bytes())
        self.assertEqual(self.index.ingest_file(image), (thing_id, False))

    def test_a_text_file_is_the_same_thing_as_its_text(self):
        note = self.root / "note.md"
        note.write_text("same words", encoding="utf-8")
        self.index.ingest_text("same words")
        self.assertEqual(self.index.ingest_file(note), (1, False))

    def test_database_rebuilds_from_the_log(self):
        self.index.ingest_text("the cat sat", name="uno")
        box = self.index.new_index("box")
        self.index.put(1, box)
        before = (self.index.count(), self.index.contents(1), self.index.contents(box))
        self.index.db.close()
        (self.root / "data" / "index.db").unlink()
        self.index = Index(self.root)
        after = (self.index.count(), self.index.contents(1), self.index.contents(box))
        self.assertEqual(before, after)
        self.assertEqual(self.index.resolve("uno"), 1)
        self.assertEqual(self.index.resolve("box.1"), 1)

    def test_database_catches_up_with_new_log_lines(self):
        self.index.ingest_text("a")
        other = Index(self.root)  # a second session writing to the same log
        other.ingest_text("b")
        other.db.close()
        self.index.db.close()
        self.index = Index(self.root)
        self.assertEqual(self.index.count(), 2)

    # --- step 2: tables, parts, instances, addresses ----------------------

    def test_a_sentence_contains_its_words_in_order(self):
        self.index.ingest_text("the cat sat")
        words = [self.text_of(i) for i in self.index.contents(1)]
        self.assertEqual(words, ["the", "cat", "sat"])

    def test_a_word_contains_its_characters(self):
        self.index.ingest_text("cat")
        self.assertEqual(
            [self.text_of(i) for i in self.index.contents(1)], ["c", "a", "t"]
        )

    def test_a_character_contains_nothing(self):
        self.index.ingest_text("a")
        self.assertEqual(self.index.contents(1), [])

    def test_a_shared_word_is_one_thing_with_two_instances(self):
        first, _ = self.index.ingest_text("the cat sat")
        second, _ = self.index.ingest_text("the cat ran")
        the = self.index.resolve(f"{first}.1")
        self.assertEqual(self.index.resolve(f"{second}.1"), the)
        self.assertEqual(self.index.instances(the), [(first, 1), (second, 1)])

    def test_a_repeated_word_keeps_every_position(self):
        self.index.ingest_text("no no yes")
        no = self.index.resolve("1.1")
        self.assertEqual(self.index.instances(no), [(1, 1), (1, 2)])

    def test_paragraphs_sentences_words(self):
        self.index.ingest_text("One two. Three four!\n\nFive six.")
        paragraphs = self.index.contents(1)
        self.assertEqual(
            [self.text_of(i) for i in paragraphs],
            ["One two. Three four!", "Five six."],
        )
        sentences = self.index.contents(paragraphs[0])
        self.assertEqual(
            [self.text_of(i) for i in sentences], ["One two.", "Three four!"]
        )
        self.assertEqual(
            [self.text_of(i) for i in self.index.contents(sentences[0])],
            ["One", "two", "."],
        )

    def test_period_addresses_walk_down_the_tables(self):
        self.index.ingest_text("One two. Three four!", name="doc")
        self.assertEqual(self.text_of(self.index.resolve("doc.2")), "Three four!")
        self.assertEqual(self.text_of(self.index.resolve("1.2.1")), "Three")
        self.assertEqual(self.text_of(self.index.resolve("1.2.1.2")), "h")
        self.assertIsNone(self.index.resolve("1.9"))

    def test_reingesting_adds_nothing(self):
        self.index.ingest_text("the cat sat")
        count = self.index.count()
        log = (self.root / "index" / "log.jsonl").read_bytes()
        self.index.ingest_text("the cat sat")
        self.assertEqual(self.index.count(), count)
        self.assertEqual((self.root / "index" / "log.jsonl").read_bytes(), log)

    def test_an_index_is_an_anchor_whose_contents_change(self):
        box = self.index.new_index("projects")
        a, _ = self.index.ingest_text("a")
        b, _ = self.index.ingest_text("b")
        self.assertEqual(self.index.put(a, box), f"{box}.1")
        self.assertEqual(self.index.put(b, box), f"{box}.2")
        self.assertEqual(self.index.contents(box), [a, b])
        self.assertEqual(self.index.resolve("projects"), box)
        self.assertEqual(self.index.resolve("projects.2"), b)
        self.assertEqual(self.index.instances(a), [(box, 1)])

    def test_two_empty_indexes_are_different_things(self):
        self.assertNotEqual(self.index.new_index(), self.index.new_index())

    def test_anything_can_gather_things(self):
        image = self.root / "dot.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
        picture, _ = self.index.ingest_file(image)
        caption, _ = self.index.ingest_text("diagram for personal OS")
        self.index.put(caption, picture)
        self.assertEqual(self.index.contents(picture), [caption])

    def test_a_name_cannot_contain_a_period(self):
        self.index.ingest_text("a")
        with self.assertRaises(ValueError):
            self.index.name(1, "a.b")

    def test_empty_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.index.ingest_text("")


if __name__ == "__main__":
    unittest.main()
