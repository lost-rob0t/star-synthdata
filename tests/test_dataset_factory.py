import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


mix = load("build_training_mix", "scripts/build_training_mix.py")


class DatasetFactoryTests(unittest.TestCase):
    def test_chunk_text_preserves_nontrivial_chunks(self):
        chunks = mix.chunk_text(("abc def ghi\n" * 100), 128, 32)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.strip()) >= 32 for chunk in chunks))

    def test_prolog_is_classified_separately(self):
        self.assertEqual(mix.path_task("rules/domain.pl", "prolog"), "public_prolog")

    def test_completion_record_has_provenance(self):
        repo = {"full_name": "lost-rob0t/demo", "license": "MIT", "html_url": "https://github.com/lost-rob0t/demo"}
        row = mix.completion_record(repo, "src/x.py", "python", "x = 1\n" * 100, 0)
        self.assertIsNotNone(row)
        self.assertEqual(row["source"]["repository"], "lost-rob0t/demo")
        self.assertEqual(row["messages"][-1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
