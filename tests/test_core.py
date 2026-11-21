"""Zero-PDF tests: synthetic caches + dev_gold schema checks. Run: python -m unittest discover -s tests"""
import csv
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from plugins.rag import exporter, pipeline  # noqa: E402
from core import llm_client, ocr, pdf_processor  # noqa: E402
from scripts import evaluate  # noqa: E402

TEXT = "Table 1: Results\nMethod EM F1\nVanilla RAG 0.204 0.330"


def result(**kw):
    r = dict(metric_name="EM", raw_value="0.204", source_page=1, source_table="Table 1", source_fragment="Vanilla RAG 0.204",
             experiment_id="", config_id="", dataset_id="", task_id="", result_origin="primary", cited_ref="")
    r.update(kw)
    return r


def make_cache(results, configs=None, datasets=None, exps=None, in_scope=True):
    return {"n_pages": 2, "windows": {"1-2": {"results": results}}, "meta": {
        "publication": {"title": "T", "year": "2025", "in_scope": in_scope, "exclusion_reason": ""},
        "configurations": configs if configs is not None else [
            {"config_id": "C01", "rag_variant": "Vanilla RAG Llama 3.1 8B", "generator_model": "Llama 3.1 8B"},
            {"config_id": "C02", "rag_variant": "Retriever-Only", "generator_model": ""}],
        "datasets": datasets if datasets is not None else [
            {"dataset_id": "DS1", "dataset_name": "HotpotQA"}, {"dataset_id": "DS2", "dataset_name": "MuSiQue"}],
        "tasks": [{"task_id": "T1", "task_type": "QA"}],
        "experiments": exps if exps is not None else [
            {"experiment_id": "E1", "evaluation_protocol": "Table 1 main evaluation"},
            {"experiment_id": "E2", "evaluation_protocol": "Table 2 ablation"}],
        "issues": []}}


def build(cache):
    return exporter.build_doc("D999", cache, None, lambda *_: None)


class Normalization(unittest.TestCase):
    def test_strip_generator_from_variant(self):
        self.assertEqual(exporter.strip_names("vanilla rag llama 3.1 8b instruct", "llama 3.1 8b instruct"), "vanilla rag")
        self.assertEqual(exporter.strip_names("Vanilla RAG (Llama 3.1 8B)", "Llama 3.1 8B"), "Vanilla RAG")
        self.assertEqual(exporter.strip_names("RA-CoT", "GPT-4o mini"), "RA-CoT")
        self.assertEqual(exporter.strip_names("GPT-4o mini", "GPT-4o mini"), "GPT-4o mini")  # never empty

    def test_metric_k(self):
        self.assertEqual(exporter.canon_metric("nDCG @ 5"), "nDCG@5")
        self.assertEqual(exporter.k_from_name("NDCG@5"), "5")
        self.assertEqual(exporter.k_from_name("Recall@10 (avg)"), "10")
        self.assertEqual(exporter.k_from_name("OC@0.8"), "")
        self.assertEqual(exporter.k_from_name("Accuracy"), "")

    def test_doc_variant_and_k(self):
        d = build(make_cache([result(metric_name="nDCG @ 5", config_id="C01", dataset_id="DS1", experiment_id="E1", task_id="T1")]))
        self.assertEqual(d["configurations"][0]["rag_variant"], "Vanilla RAG")
        self.assertEqual(d["results"][0]["metric_name"], "nDCG@5")
        self.assertEqual(d["results"][0]["metric_k"], "5")

    def test_scale_kept(self):
        d = build(make_cache([result(raw_value=".204"), result(raw_value="62.4%", metric_name="Accuracy", source_fragment="x 62.4%")]))
        self.assertEqual([(r["metric_value"], r["metric_unit"]) for r in d["results"]], [("0.204", "fraction"), ("62.4", "%")])

    def test_quote_repair_and_grounding(self):
        pages = [exporter.norm(TEXT), exporter.norm("other")]
        frag, page, st = exporter.ground("Vanilla  RAG 0.204", 2, pages)  # wrong page + spacing
        self.assertEqual(page, 1)
        self.assertNotEqual(st, "unverified")

    def test_out_of_scope_has_no_results(self):
        d = build(make_cache([result()], in_scope=False))
        self.assertEqual(d["results"], [])
        self.assertEqual(d["publications"][0]["in_scope"], "false")
        self.assertTrue(d["publications"][0]["exclusion_reason"])


class Misc(unittest.TestCase):
    def test_masked_vendor_token(self):
        self.assertEqual(exporter.canon_space("[模型名称已隐藏]-4o-mini"), "GPT-4o-mini")

    def test_unprocessed_publication_is_not_an_in_scope_prediction(self):
        stub = exporter.stub_publication("PENDING")
        self.assertEqual(stub["in_scope"], "false")
        self.assertEqual(stub["exclusion_reason"], "Unprocessed: no scope decision")

    def test_schema_coercion(self):
        try:
            from plugins.rag.schemas import Window
        except ImportError:
            self.skipTest("pydantic missing")
        base = {k: "" for k in ("experiment_id", "config_id", "dataset_id", "task_id", "metric_group", "metric_name", "metric_variant",
                                "metric_direction", "metric_k", "raw_value", "raw_unit", "baseline_value", "aggregation", "sample_size",
                                "result_origin", "cited_ref", "source_section", "source_table", "source_figure", "source_fragment",
                                "extraction_status", "note")}
        base.update(source_figure=3, source_table=["Table 1", "Table 2"], source_page="p. 5", metric_k=None)
        v = Window.parse_obj({"results": [base]}) if hasattr(Window, "parse_obj") else Window.model_validate({"results": [base]})
        r = v.results[0]
        self.assertEqual((r.source_figure, r.source_table, r.source_page, r.metric_k), ("3", "Table 1; Table 2", 5, ""))


class Linking(unittest.TestCase):
    def test_multikey_link(self):
        rs = [result(source_fragment="Vanilla RAG Llama 3.1 8B HotpotQA 0.204"),
              result(source_fragment="Retriever-Only MuSiQue 0.100", raw_value="0.100")]
        d = build(make_cache(rs))["results"]
        self.assertEqual((d[0]["config_id"], d[0]["dataset_id"], d[0]["experiment_id"], d[0]["task_id"]), ("C01", "DS1", "E1", "T1"))
        self.assertEqual((d[1]["config_id"], d[1]["dataset_id"]), ("C02", "DS2"))

    def test_ambiguous_stays_blank(self):
        d = build(make_cache([result(source_fragment="0.204", source_table="Table 9")]))["results"]
        self.assertEqual((d[0]["config_id"], d[0]["dataset_id"], d[0]["experiment_id"]), ("", "", ""))

    def test_table_inheritance(self):
        rs = [result(source_table="Table 9", experiment_id="E2"), result(source_table="Table 9", raw_value="0.5", source_fragment="y 0.5")]
        d = build(make_cache(rs))["results"]
        self.assertEqual(d[1]["experiment_id"], "E2")

    def test_non_numeric_goes_to_issues(self):
        d = build(make_cache([result(raw_value="significantly better")]))
        self.assertEqual(d["results"], [])
        self.assertTrue(any(i["check_name"] == "non_numeric_result" for i in d["issues"]))

    def test_verify_rows_exported(self):
        c = make_cache([result()])
        c["verify"] = {"1": {"results": [result(raw_value="0.77", source_fragment="Vanilla RAG 0.77")]}}
        self.assertEqual(len(build(c)["results"]), 2)


class Pipeline(unittest.TestCase):
    def _run(self, workers):
        names = [pathlib.Path(f"D{i:03d}.pdf") for i in range(1, 9)]

        def fn(p):
            time.sleep(0.02 * (hash(p.stem) % 3))
            return (True, f"ok {p.stem}") if p.stem != "D005" else (None, "SKIPPED_SCAN")
        return pipeline.run_documents(names, fn, workers)

    def test_workers_determinism(self):
        self.assertEqual(self._run(1), self._run(4))

    def test_header_preserved_on_split(self):
        lines = ["Table 1: Results", "Method EM F1"] + [f"row{i} 0.{i} 0.{i}" for i in range(30)]
        hdr = pipeline._header(lines, 20)
        self.assertEqual(hdr[0], "Table 1: Results")
        self.assertIn("Method EM F1", hdr)

    def test_verify_page_selection(self):
        dense = " ".join(f"{i}.5" for i in range(60))
        cache = {"windows": {"1-2": {"results": [{"source_page": 1, "source_fragment": "a"}] * 3}}}
        self.assertEqual(pipeline.select_verify_pages([dense, "text only"], cache), [1])
        full = {"windows": {"1-2": {"results": [{"source_page": 1, "source_fragment": ""}] * 50}}}
        self.assertEqual(pipeline.select_verify_pages([dense], full), [])


class OcrFallback(unittest.TestCase):
    pdf = pathlib.Path("synthetic.pdf")
    native = "A full native page with text that exceeds the OCR threshold."
    recognized = "A recovered scan with metric values and their surrounding text."

    def test_ocr_for_mixed_pdf_and_unusable_outputs(self):
        # The native scan heuristic alone considers this document text-readable.
        pages = [Mock(get_text=Mock(return_value=t)) for t in [self.native] * 3 + [""]]
        open_pdf = Mock()
        open_pdf.return_value.__enter__ = Mock(return_value=pages)
        open_pdf.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(sys.modules, pymupdf=SimpleNamespace(open=open_pdf)), \
                patch.object(ocr, "ocr_available") as available, \
                patch.object(ocr, "ocr_pages") as recognize, patch.object(llm_client, "log") as log:
            recognize.return_value = [self.native] * 3 + [self.recognized]
            info = pdf_processor.inspect_pdf(self.pdf, ocr=True)
            self.assertTrue(info.used_ocr)
            self.assertFalse(info.is_scan)
            self.assertEqual(info.pages[-1], self.recognized)
            for installed, error, warning in [(True, None, "insufficient text on PDF pages 4"),
                                               (True, RuntimeError("OCR failed"), "OCR failed"),
                                               (False, None, "OCR unavailable")]:
                with self.subTest(warning=warning):
                    available.return_value = installed
                    recognize.side_effect = error
                    recognize.return_value = [self.native] * 3 + ["  "]
                    info = pdf_processor.inspect_pdf(self.pdf, ocr=True)
                    self.assertTrue(info.is_scan)
                    self.assertFalse(info.used_ocr)
                    self.assertEqual(info.pages[-1], "")
                    self.assertIn(warning, log.call_args.args[0])

    def test_backend_mode_and_zero_rows_warning(self):
        for text_only, used_ocr in [(False, False), (False, True), (True, False), (True, True)]:
            with self.subTest(text_only=text_only, used_ocr=used_ocr), tempfile.TemporaryDirectory() as tmp:
                info = pdf_processor.PdfInfo(self.pdf, 1, [self.recognized if used_ocr else ""],
                                             is_scan=not used_ocr, used_ocr=used_ocr)
                client = Mock(text_only=text_only)
                meta = make_cache([])["meta"]
                cache_dir = pathlib.Path(tmp)
                with patch.object(pipeline, "inspect_pdf", return_value=info), \
                        patch.object(pipeline, "_gen", side_effect=[meta, {"results": []}]) as generate, \
                        patch.object(pipeline, "log") as log:
                    ok, message = pipeline.process_document(self.pdf, client, cache_dir, False, 3, "auto", ocr=True)
                if text_only and not used_ocr:
                    self.assertIsNone(ok)
                    self.assertIn("SKIPPED_SCAN", message)
                    generate.assert_not_called()
                else:
                    self.assertTrue(ok)
                    cache = llm_client.load_cache(cache_dir, self.pdf.stem)
                    self.assertEqual((cache["version"], cache["mode"], cache["ocr"]),
                                     (2, "text" if used_ocr else "pdf", used_ocr))
                    first_input = generate.call_args_list[0].args[1][0]
                    if used_ocr:
                        self.assertIn(self.recognized, first_input)
                    else:
                        self.assertIs(first_input, client.upload_pdf.return_value)
                        client.delete_file.assert_called_once_with(first_input)
                    self.assertTrue(any("WARN: in-scope publication yielded 0" in c.args[0] for c in log.call_args_list))
                self.assertEqual(client.upload_pdf.call_count, int(not text_only and not used_ocr))


class NetworkRetries(unittest.TestCase):
    def test_gemini_retries_remote_protocol_error(self):
        try:
            from httpx import RemoteProtocolError
        except ImportError:
            self.skipTest("httpx missing")
        error = RemoteProtocolError("Server disconnected without sending a response")
        wrapped = RuntimeError("transport failed")
        wrapped.__cause__ = error
        self.assertTrue(llm_client.is_transient(error))
        self.assertTrue(llm_client.is_transient(wrapped))
        self.assertFalse(llm_client.is_transient(ValueError("400 invalid request")))
        client = llm_client.GeminiClient.__new__(llm_client.GeminiClient)
        client.types, client.client = Mock(), Mock()
        client.model, client.temperature, client.max_out, client.max_retries = "test", 0, 100, 1
        client._sleep = Mock()
        generate = client.client.models.generate_content
        generate.side_effect = [wrapped, SimpleNamespace(text='{"results": []}')]
        self.assertEqual(client.generate_json([], "", object), {"results": []})
        self.assertEqual(generate.call_count, 2)
        client._sleep.assert_called_once()


class EvaluationDiffs(unittest.TestCase):
    def test_loose_diffs_cancel_exact_matches_and_pair_remaining_copies(self):
        strict = ("P1", "corpus", "ablation", "generator", "recall", "5", "0.5")
        other_gold = ("P1", "subset", "ablation", "generator", "recall", "5", "0.5")
        other_pred = ("P1", "subset", "ablation", "generator", "recall", "", "0.5")
        pred = Counter({strict: 1, other_pred: 3})
        gold = Counter({strict: 1, other_gold: 2})
        expected = (("P1", "recall", "0.5"), ("subset", "ablation", "generator", ""),
                    ("subset", "ablation", "generator", "5"))
        self.assertEqual(list(evaluate.loose_diffs(pred, gold)), [expected, expected])
        with patch("builtins.print") as output:
            evaluate.show_loose_diffs(pred, gold, 1)
        report = "\n".join(c.args[0] for c in output.call_args_list)
        self.assertEqual(report.count("metric_k pred='' gold='5'"), 1)
        self.assertIn("Paired rows: 2; shown: 1", report)
        self.assertIn("metric_k=2", report)


class SubmissionCompliance(unittest.TestCase):
    def test_rebuild_marks_missing_and_empty_extractions_as_unprocessed(self):
        import check_submission as cs
        from main import main

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source, cache_dir, output = root / "input", root / "cache", root / "out"
            source.mkdir()
            for pid, results in [("GOOD", [result()]), ("EMPTY", []), ("MISSING", None)]:
                (source / f"{pid}.pdf").touch()
                if results is not None:
                    cache = make_cache(results)
                    cache.update(version=2, complete=True, mode="pdf")
                    llm_client.save_cache(cache_dir, pid, cache)
            self.assertEqual(main(["--input", str(source), "--output", str(output),
                                   "--cache", str(cache_dir), "--rebuild-csv-only"]), 1)
            report = cs.validate(output, source, page_reader=lambda _: [TEXT, ""])
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["exit_code"], 2)
            for pid in ("EMPTY", "MISSING"):
                self.assertTrue(any(w.startswith(f"{pid}: unprocessed publication") for w in report["warnings"]))
            self.assertEqual(report["rows"]["results"], 1)

    def test_check_submission_no_errors_no_review(self):
        import check_submission as cs
        rs = [result(source_fragment="Vanilla RAG Llama 3.1 8B HotpotQA 0.204", config_id="", dataset_id=""),
              result(raw_value="n/a text")]
        doc = build(make_cache(rs))
        with tempfile.TemporaryDirectory() as td:
            w = exporter.TableWriter(pathlib.Path(td))
            w.write_doc(doc)
            w.close(True)
            rep = cs.validate(td, None)
        self.assertEqual(rep["errors"], [])
        self.assertEqual([w for w in rep["warnings"] if "PDF directory not provided" not in w], [])


class GoldSchema(unittest.TestCase):
    def test_gold_conventions(self):
        g = ROOT / "dev_gold"
        if not g.exists():
            self.skipTest("no dev_gold")
        def rd(t):
            with (g / f"{t}.csv").open(encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        self.assertEqual({r["in_scope"] for r in rd("publications")}, {"true"})
        res = rd("results")
        self.assertTrue(all(r["metric_k"].isdigit() for r in res if "@" in r["metric_name"] and r["metric_k"]))
        cols = exporter.columns()
        for t in exporter.TABLES:
            with (g / f"{t}.csv").open(encoding="utf-8-sig") as f:
                self.assertEqual(f.readline().strip().split(","), cols[t])


if __name__ == "__main__":
    unittest.main()
