import tempfile
import unittest
from pathlib import Path

from everything_index.store import Index


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = Index(self.root)

    def tearDown(self):
        self.index.db.close()
        self.tmp.cleanup()

    def reopen(self, delete_database=False):
        self.index.db.close()
        if delete_database:
            (self.root / "data" / "index.db").unlink()
        self.index = Index(self.root)

    def add(self, text, **kwargs):
        return self.index.ingest_text(text, **kwargs)[0]

    def text_of(self, thing_id):
        return self.index.get(thing_id)["text"]

    def texts(self, thing_id, property_name):
        return [self.text_of(i) for i in self.index.row(thing_id, property_name)]


class MasterIndexTest(Base):
    def test_ids_count_up_in_order_of_ingestion(self):
        first = self.add("a")
        self.assertEqual(self.add("b"), first + 1)

    def test_same_content_is_the_same_thing(self):
        hello = self.add("hello")
        count = self.index.count()
        self.assertEqual(self.index.ingest_text("hello"), (hello, False))
        self.assertEqual(self.index.count(), count)

    def test_time_is_recorded(self):
        self.assertRegex(self.index.get(self.add("a"))["time"], r"^\d{4}-\d\d-\d\dT")

    def test_a_name_is_equivalent_to_its_id(self):
        hello = self.add("hello", name="greeting")
        self.assertEqual(self.index.resolve("greeting"), hello)
        self.assertEqual(self.index.resolve(str(hello)), hello)
        self.assertEqual(self.index.get(hello)["names"], ["greeting"])

    def test_a_name_cannot_point_at_two_things(self):
        self.add("a", name="x")
        count = self.index.count()
        with self.assertRaises(ValueError):
            self.add("b", name="x")
        self.assertEqual(self.index.count(), count)  # the failed one took no ID
        self.reopen()
        self.assertEqual(self.add("b"), count + 1)

    def test_names_that_would_be_confusing_are_refused(self):
        a = self.add("a")
        for bad in ("42", "a.b", "#1", " padded", ""):
            with self.assertRaises(ValueError):
                self.index.name(a, bad)

    def test_naming_an_existing_thing_on_reingest(self):
        one = self.add("one")
        self.assertEqual(self.index.ingest_text("one", name="uno"), (one, False))
        self.assertEqual(self.index.resolve("uno"), one)

    def test_files_that_are_not_text(self):
        image = self.root / "dot.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
        thing_id, is_new = self.index.ingest_file(image)
        thing = self.index.get(thing_id)
        self.assertTrue(is_new)
        self.assertEqual(thing["kind"], "image/png")
        self.assertEqual(thing["source"], "dot.png")
        self.assertEqual(self.index.content(thing_id), image.read_bytes())
        self.assertEqual(self.index.ingest_file(image), (thing_id, False))

    def test_a_text_file_is_the_same_thing_as_its_text(self):
        note = self.root / "note.md"
        note.write_text("same words", encoding="utf-8")
        typed = self.add("same words")
        self.assertEqual(self.index.ingest_file(note), (typed, False))

    def test_empty_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.index.ingest_text("")

    def test_database_rebuilds_from_the_log(self):
        story = self.add("the cat sat", name="uno")
        box = self.index.new_index("box")
        self.index.put(story, box)
        before = (self.index.count(), self.index.row(story, "words"),
                  self.index.row(box, "things"))
        self.reopen(delete_database=True)
        after = (self.index.count(), self.index.row(story, "words"),
                 self.index.row(box, "things"))
        self.assertEqual(before, after)
        self.assertEqual(len(before[1]), 3)
        self.assertEqual(self.index.resolve("uno"), story)
        self.assertEqual(self.index.resolve("box.things.0"), story)

    def test_database_catches_up_with_new_log_lines(self):
        self.add("a")
        other = Index(self.root)  # a second session writing to the same log
        b = other.ingest_text("b")[0]
        other.db.close()
        self.reopen()
        self.assertEqual(self.text_of(b), "b")

    def test_reingesting_adds_nothing(self):
        self.add("the cat sat")
        log = (self.root / "index" / "log.jsonl").read_bytes()
        self.add("the cat sat")
        self.assertEqual((self.root / "index" / "log.jsonl").read_bytes(), log)


class TableTest(Base):
    def test_a_word_has_characters_as_a_property(self):
        cat = self.add("cat")
        characters = self.index.resolve("characters")
        self.assertEqual(self.index.properties(cat), [(characters, 3)])
        self.assertEqual(self.texts(cat, "characters"), ["c", "a", "t"])
        self.assertEqual(self.index.get(characters)["kind"], "index")

    def test_a_sentence_has_words_in_order(self):
        sentence = self.add("the cat sat")
        self.assertEqual(self.texts(sentence, "words"), ["the", "cat", "sat"])
        self.assertEqual(self.index.row(sentence, "characters"), [])

    def test_a_character_has_no_properties(self):
        self.assertEqual(self.index.properties(self.add("a")), [])

    def test_positions_start_at_zero(self):
        cat = self.add("cat", name="cat")
        self.assertEqual(self.text_of(self.index.resolve("cat.characters.0")), "c")
        self.assertEqual(self.text_of(self.index.resolve("cat.characters.2")), "t")
        self.assertIsNone(self.index.resolve("cat.characters.3"))

    def test_a_shared_word_is_one_thing_with_two_instances(self):
        first, second = self.add("the cat sat"), self.add("the cat ran")
        words = self.index.resolve("words")
        the = self.index.resolve(f"{first}.words.0")
        self.assertEqual(self.index.resolve(f"{second}.words.0"), the)
        self.assertEqual(
            self.index.instances(the), [(first, words, 0), (second, words, 0)]
        )

    def test_a_repeated_word_keeps_every_position(self):
        sentence = self.add("no no yes")
        words = self.index.resolve("words")
        no = self.index.resolve(f"{sentence}.words.0")
        self.assertEqual(
            self.index.instances(no), [(sentence, words, 0), (sentence, words, 1)]
        )

    def test_paragraphs_sentences_words(self):
        self.add("One two. Three four!\n\nFive six.", name="doc")
        find = self.index.resolve
        self.assertEqual(
            self.texts(find("doc"), "paragraphs"),
            ["One two. Three four!", "Five six."],
        )
        self.assertEqual(
            self.texts(find("doc.paragraphs.0"), "sentences"),
            ["One two.", "Three four!"],
        )
        self.assertEqual(
            self.texts(find("doc.paragraphs.0.sentences.0"), "words"),
            ["One", "two", "."],
        )

    def test_a_code_is_all_ids_and_a_name_may_replace_any_id(self):
        doc = self.add("One two. Three four!", name="doc")
        find = self.index.resolve
        sentences, words = find("sentences"), find("words")
        by_code = find(f"{doc}.{sentences}.1.{words}.0")
        self.assertEqual(self.text_of(by_code), "Three")
        self.assertEqual(find("doc.sentences.1.words.0"), by_code)
        self.assertEqual(find(f"doc.{sentences}.1.words.0"), by_code)
        self.assertIsNone(find("doc.sentences.9"))
        self.assertIsNone(find("doc.words.0"))    # doc has sentences, not words
        self.assertIsNone(find("doc.sentences"))  # no position given

    def test_a_property_knows_what_holds_it(self):
        cat, dog = self.add("cat"), self.add("dog")
        characters = self.index.resolve("characters")
        self.assertEqual(self.index.holders(characters), [cat, dog])
        self.assertEqual(self.index.holder_count(characters), 2)

    def test_an_index_is_an_anchor_whose_contents_change(self):
        box = self.index.new_index("projects")
        a, b = self.add("a"), self.add("b")
        self.index.put(a, box)
        self.index.put(b, box)
        things = self.index.resolve("things")
        self.assertEqual(self.index.row(box, "things"), [a, b])
        self.assertEqual(self.index.resolve("projects.things.1"), b)
        self.assertEqual(self.index.instances(a), [(box, things, 0)])

    def test_put_under_a_chosen_property(self):
        box = self.index.new_index("projects")
        a, b = self.add("a"), self.add("b")
        self.index.put(a, box, "drafts")  # the name is created on first use
        self.index.put(b, box, "done")
        self.assertEqual(self.index.put(b, box, "drafts").split(".")[-1], "1")
        drafts, done = self.index.resolve("drafts"), self.index.resolve("done")
        self.assertEqual(self.index.properties(box), [(drafts, 2), (done, 1)])
        self.assertEqual(self.index.row(box, "drafts"), [a, b])
        self.assertEqual(self.index.resolve("projects.done.0"), b)
        self.index.put(a, box, done)  # a property may also be given as an ID
        self.assertEqual(self.index.row(box, "done"), [b, a])

    def test_two_empty_indexes_are_different_things(self):
        self.assertNotEqual(self.index.new_index(), self.index.new_index())

    def test_anything_can_gather_things(self):
        image = self.root / "dot.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
        picture, _ = self.index.ingest_file(image)
        caption = self.add("diagram for personal OS")
        self.index.put(caption, picture, "description")
        self.assertEqual(self.index.row(picture, "description"), [caption])


class NumberTest(Base):
    def test_digits_are_the_first_things_and_index_themselves(self):
        self.add("x")
        digits = self.index.resolve("digits")
        self.assertEqual(digits, 1)
        self.assertEqual(self.texts(digits, "digits"), list("0123456789"))
        self.assertEqual(self.index.row(digits, digits), list(range(2, 12)))
        for d in range(10):
            at_own_position = self.index.resolve(f"digits.digits.{d}")
            self.assertEqual(self.text_of(at_own_position), str(d))
            self.assertEqual(self.index.resolve(f"#{d}"), at_own_position)

    def test_zero_exists_from_the_start(self):
        self.index.new_index("anything")
        self.assertEqual(self.text_of(self.index.number(0)), "0")

    def test_a_number_is_digits_in_places_left_to_right(self):
        n = self.add("305")
        zero, three, five = (self.index.number(d) for d in (0, 3, 5))
        self.assertEqual(self.index.row(n, "characters"), [three, zero, five])
        self.assertEqual(self.index.resolve("#305.characters.1"), zero)
        self.assertNotEqual(self.add("35"), n)

    def test_a_number_used_by_the_system_becomes_a_thing(self):
        self.assertIsNone(self.index.number(12))
        self.add("a b c d e f g h i j k l")  # twelve words
        for n in (10, 11, 12):
            self.assertEqual(self.text_of(self.index.number(n)), str(n))
        self.assertIsNone(self.index.number(13))
        twelve = self.index.number(12)
        self.assertEqual(
            self.index.row(twelve, "characters"),
            [self.index.number(1), self.index.number(2)],
        )

    def test_a_numeral_in_text_is_the_same_thing_as_the_number(self):
        sentence = self.add("I have 3 cats")
        self.assertEqual(self.index.resolve(f"{sentence}.words.2"), self.index.number(3))

    def test_an_id_and_a_number_are_different(self):
        self.add("x")
        self.assertEqual(self.index.resolve("3"), 3)  # the third thing ingested
        self.assertEqual(self.text_of(3), "1")        # which happens to be digit 1
        self.assertEqual(self.text_of(self.index.resolve("#3")), "3")
        self.assertEqual(self.index.as_number(self.index.number(3)), 3)
        self.assertIsNone(self.index.as_number(self.add("03")))
        self.assertIsNone(self.index.as_number(self.index.resolve("digits")))

    def test_a_number_read_backwards(self):
        cat = self.add("cat")
        characters = self.index.resolve("characters")
        self.assertIn((cat, characters), self.index.counted_by(3))
        t = self.index.resolve(f"{cat}.characters.2")
        self.assertIn((cat, characters, t), self.index.positioned_at(2))
        self.assertEqual(
            [h for h, p, i in self.index.positioned_at(3) if h == cat], []
        )

    def test_intersection_of_properties(self):
        sentence = self.add("the cat sat on a sofa")
        find = self.index.resolve
        three_characters = self.index.intersect([find("characters"), find("#3")])
        self.assertEqual(
            sorted(self.text_of(i) for i in three_characters), ["cat", "sat", "the"]
        )
        a, t = find(f"{sentence}.words.1.characters.1"), find(f"{sentence}.words.1.characters.2")
        self.assertEqual(
            sorted(self.text_of(i) for i in self.index.intersect([a, t])),
            ["cat", "sat"],
        )
        self.assertEqual(self.index.intersect([find("words"), find("#6")]), [sentence])

    def test_numbers_survive_a_rebuild_and_keep_counting(self):
        self.add("a b c d e f g h i j k l")
        self.reopen(delete_database=True)
        self.assertIsNotNone(self.index.number(12))
        self.add("a b c d e f g h i j k l m n")
        self.assertIsNotNone(self.index.number(14))
        self.assertIsNone(self.index.number(15))

    def test_a_failed_ingest_does_not_lose_count(self):
        self.add("a b c d e f g h i j k", name="x")
        with self.assertRaises(ValueError):
            self.add("a b c d e f g h i j k l m", name="x")
        self.assertIsNone(self.index.number(13))
        self.add("a b c d e f g h i j k l m")
        self.assertIsNotNone(self.index.number(13))


if __name__ == "__main__":
    unittest.main()
