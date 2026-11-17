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
        count = self.index.count()
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
        before = (self.index.count(), self.index.row(1, "words"), self.index.row(box, "things"))
        self.index.db.close()
        (self.root / "data" / "index.db").unlink()
        self.index = Index(self.root)
        after = (self.index.count(), self.index.row(1, "words"), self.index.row(box, "things"))
        self.assertEqual(before, after)
        self.assertEqual(len(before[1]), 3)
        self.assertEqual(self.index.resolve("uno"), 1)
        self.assertEqual(self.index.resolve("box.things.1"), 1)

    def test_database_catches_up_with_new_log_lines(self):
        self.index.ingest_text("a")
        other = Index(self.root)  # a second session writing to the same log
        other.ingest_text("b")
        other.db.close()
        self.index.db.close()
        self.index = Index(self.root)
        self.assertEqual(self.index.count(), 2)

    # --- tables, properties, instances, addresses ------------------------

    def texts(self, thing_id, property_name):
        return [self.text_of(i) for i in self.index.row(thing_id, property_name)]

    def test_a_word_has_characters_as_a_property(self):
        self.index.ingest_text("cat")
        characters = self.index.resolve("characters")
        self.assertEqual(self.index.properties(1), [(characters, 3)])
        self.assertEqual(self.texts(1, "characters"), ["c", "a", "t"])
        self.assertEqual(self.index.get(characters)["kind"], "index")

    def test_a_sentence_has_words_in_order(self):
        self.index.ingest_text("the cat sat")
        self.assertEqual(self.texts(1, "words"), ["the", "cat", "sat"])
        self.assertEqual(self.index.row(1, "characters"), [])

    def test_a_character_has_no_properties(self):
        self.index.ingest_text("a")
        self.assertEqual(self.index.properties(1), [])

    def test_a_shared_word_is_one_thing_with_two_instances(self):
        first, _ = self.index.ingest_text("the cat sat")
        second, _ = self.index.ingest_text("the cat ran")
        words = self.index.resolve("words")
        the = self.index.resolve(f"{first}.words.1")
        self.assertEqual(self.index.resolve(f"{second}.words.1"), the)
        self.assertEqual(
            self.index.instances(the), [(first, words, 1), (second, words, 1)]
        )

    def test_a_repeated_word_keeps_every_position(self):
        self.index.ingest_text("no no yes")
        words = self.index.resolve("words")
        no = self.index.resolve("1.words.1")
        self.assertEqual(self.index.instances(no), [(1, words, 1), (1, words, 2)])

    def test_paragraphs_sentences_words(self):
        self.index.ingest_text("One two. Three four!\n\nFive six.")
        self.assertEqual(
            self.texts(1, "paragraphs"), ["One two. Three four!", "Five six."]
        )
        first = self.index.resolve("1.paragraphs.1")
        self.assertEqual(self.texts(first, "sentences"), ["One two.", "Three four!"])
        sentence = self.index.resolve("1.paragraphs.1.sentences.1")
        self.assertEqual(self.texts(sentence, "words"), ["One", "two", "."])

    def test_addresses_read_thing_property_position(self):
        self.index.ingest_text("One two. Three four!", name="doc")
        find = self.index.resolve
        self.assertEqual(self.text_of(find("doc.sentences.2")), "Three four!")
        self.assertEqual(self.text_of(find("doc.sentences.2.words.1")), "Three")
        self.assertEqual(
            self.text_of(find("doc.sentences.2.words.1.characters.2")), "h"
        )
        by_id = f"1.{find('sentences')}.2"  # a property may be given as an ID
        self.assertEqual(find(by_id), find("doc.sentences.2"))
        self.assertIsNone(find("doc.sentences.9"))
        self.assertIsNone(find("doc.words.1"))   # doc has sentences, not words
        self.assertIsNone(find("doc.sentences"))  # no position given

    def test_a_property_knows_what_holds_it(self):
        self.index.ingest_text("cat")
        self.index.ingest_text("dog")
        characters = self.index.resolve("characters")
        self.assertEqual(len(self.index.holders(characters)), 2)
        self.assertIn(1, self.index.holders(characters))
        self.assertEqual(self.index.holder_count(characters), 2)

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
        self.index.put(a, box)
        self.index.put(b, box)
        things = self.index.resolve("things")
        self.assertEqual(self.index.row(box, "things"), [a, b])
        self.assertEqual(self.index.resolve("projects.things.2"), b)
        self.assertEqual(self.index.instances(a), [(box, things, 1)])

    def test_put_under_a_chosen_property(self):
        box = self.index.new_index("projects")
        a, _ = self.index.ingest_text("a")
        b, _ = self.index.ingest_text("b")
        self.index.put(a, box, "drafts")  # the name is created on first use
        self.index.put(b, box, "done")
        self.index.put(b, box, "drafts")
        drafts, done = self.index.resolve("drafts"), self.index.resolve("done")
        self.assertEqual(self.index.properties(box), [(drafts, 2), (done, 1)])
        self.assertEqual(self.index.row(box, "drafts"), [a, b])
        self.assertEqual(self.index.resolve("projects.done.1"), b)
        self.index.put(a, box, done)  # a property may also be given as an ID
        self.assertEqual(self.index.row(box, "done"), [b, a])

    def test_two_empty_indexes_are_different_things(self):
        self.assertNotEqual(self.index.new_index(), self.index.new_index())

    def test_anything_can_gather_things(self):
        image = self.root / "dot.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
        picture, _ = self.index.ingest_file(image)
        caption, _ = self.index.ingest_text("diagram for personal OS")
        self.index.put(caption, picture, "description")
        self.assertEqual(self.index.row(picture, "description"), [caption])

    def test_a_name_cannot_contain_a_period(self):
        self.index.ingest_text("a")
        with self.assertRaises(ValueError):
            self.index.name(1, "a.b")

    # --- numbers ----------------------------------------------------------

    def test_a_number_used_by_the_system_becomes_a_thing(self):
        self.assertIsNone(self.index.number(3))
        self.index.ingest_text("cat")  # uses positions 1, 2, 3 and the count 3
        for n in (1, 2, 3):
            self.assertEqual(self.text_of(self.index.number(n)), str(n))
        self.assertIsNone(self.index.number(4))

    def test_numbers_index_themselves(self):
        self.index.ingest_text("a b c d e f g h i j k l")  # twelve words
        numbers = self.index.resolve("numbers")
        row = self.index.row(numbers, numbers)
        self.assertEqual([self.text_of(i) for i in row], [str(n) for n in range(1, 13)])
        self.assertEqual(self.index.resolve("numbers.numbers.7"), self.index.number(7))
        self.assertEqual(self.index.resolve("#7"), self.index.number(7))

    def test_a_number_is_made_of_digits_which_are_numbers(self):
        self.index.ingest_text("a b c d e f g h i j k l")
        twelve = self.index.number(12)
        self.assertEqual(
            self.index.row(twelve, "characters"),
            [self.index.number(1), self.index.number(2)],
        )

    def test_a_numeral_in_text_is_the_same_thing_as_the_number(self):
        self.index.ingest_text("I have 3 cats")
        three_in_text = self.index.resolve("1.words.3")
        self.index.ingest_text("dog")
        self.assertEqual(self.index.number(3), three_in_text)

    def test_the_id_3_and_the_number_3_are_different(self):
        self.index.ingest_text("x")
        self.index.ingest_text("y")
        self.index.ingest_text("z")
        self.index.ingest_text("cat")
        self.assertEqual(self.text_of(self.index.resolve("3")), "z")
        self.assertEqual(self.text_of(self.index.resolve("#3")), "3")
        self.assertIsNone(self.index.as_number(3))
        self.assertEqual(self.index.as_number(self.index.number(3)), 3)

    def test_a_number_read_backwards(self):
        cat, _ = self.index.ingest_text("cat")
        characters = self.index.resolve("characters")
        self.assertIn((cat, characters), self.index.counted_by(3))
        t = self.index.resolve(f"{cat}.characters.3")
        self.assertIn((cat, characters, t), self.index.positioned_at(3))

    def test_intersection_of_properties(self):
        sentence, _ = self.index.ingest_text("the cat sat on a sofa")
        find = self.index.resolve
        words = {self.text_of(i): i for i in self.index.row(sentence, "words")}
        three_characters = self.index.intersect([find("characters"), find("#3")])
        self.assertEqual(
            sorted(self.text_of(i) for i in three_characters), ["cat", "sat", "the"]
        )
        with_a_and_t = self.index.intersect([find(f"{words['cat']}.characters.2"),
                                             find(f"{words['cat']}.characters.3")])
        self.assertEqual(sorted(self.text_of(i) for i in with_a_and_t), ["cat", "sat"])
        self.assertEqual(self.index.intersect([find("words"), find("#6")]), [sentence])

    def test_numbers_survive_a_rebuild_and_keep_counting(self):
        self.index.ingest_text("cat")
        self.index.db.close()
        (self.root / "data" / "index.db").unlink()
        self.index = Index(self.root)
        self.index.ingest_text("horse")
        numbers = self.index.resolve("numbers")
        row = self.index.row(numbers, numbers)
        self.assertEqual([self.text_of(i) for i in row], ["1", "2", "3", "4", "5"])

    def test_a_failed_ingest_does_not_lose_count(self):
        self.index.ingest_text("cat", name="x")
        with self.assertRaises(ValueError):
            self.index.ingest_text("horses", name="x")
        self.assertIsNone(self.index.number(6))
        self.index.ingest_text("horses")
        self.assertEqual(self.text_of(self.index.resolve("numbers.numbers.6")), "6")

    def test_a_name_cannot_start_with_a_hash(self):
        self.index.ingest_text("a")
        with self.assertRaises(ValueError):
            self.index.name(1, "#1")

    def test_empty_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.index.ingest_text("")


if __name__ == "__main__":
    unittest.main()
