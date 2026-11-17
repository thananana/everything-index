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

    def test_ids_count_up_in_order_of_ingestion(self):
        self.assertEqual(self.index.ingest_text("first"), (1, True))
        self.assertEqual(self.index.ingest_text("second"), (2, True))

    def test_same_content_is_the_same_thing(self):
        self.index.ingest_text("hello")
        self.assertEqual(self.index.ingest_text("hello"), (1, False))
        self.assertEqual(self.index.count(), 1)

    def test_time_is_recorded(self):
        self.index.ingest_text("hello")
        self.assertRegex(self.index.get(1)["time"], r"^\d{4}-\d\d-\d\dT")

    def test_a_name_is_equivalent_to_its_id(self):
        self.index.ingest_text("hello", name="greeting")
        self.assertEqual(self.index.resolve("greeting"), 1)
        self.assertEqual(self.index.resolve("1"), 1)
        self.assertEqual(self.index.get(1)["names"], ["greeting"])

    def test_a_name_cannot_point_at_two_things(self):
        self.index.ingest_text("one", name="x")
        with self.assertRaises(ValueError):
            self.index.ingest_text("two", name="x")
        self.assertEqual(self.index.count(), 1)  # the failed one took no ID

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
        self.index.ingest_text("one", name="uno")
        self.index.ingest_text("two")
        self.index.db.close()
        (self.root / "data" / "index.db").unlink()
        self.index = Index(self.root)
        self.assertEqual(self.index.count(), 2)
        self.assertEqual(self.index.resolve("uno"), 1)
        self.assertEqual(self.index.ingest_text("three"), (3, True))

    def test_database_catches_up_with_new_log_lines(self):
        self.index.ingest_text("one")
        other = Index(self.root)  # a second session writing to the same log
        other.ingest_text("two")
        other.db.close()
        self.index.db.close()
        self.index = Index(self.root)
        self.assertEqual(self.index.count(), 2)

    def test_empty_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.index.ingest_text("")


if __name__ == "__main__":
    unittest.main()
