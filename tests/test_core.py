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
    def test_metric_abbreviation_is_expanded_only_for_unique_printed_definition(self):
        rows = [{"metric_name": "Eval", "note": ""}, {"metric_name": "Rec", "note": ""},
                {"metric_name": "Other", "note": ""}]
        exporter._expand_metric_abbreviations(rows, ["Evaluation (Eval), Recall (Rec), Recollection (Rec)."])
        self.assertEqual([row["metric_name"] for row in rows], ["Evaluation", "Rec", "Other"])
        self.assertIn("Eval", rows[0]["note"])

    def test_distinct_vector_observations_survive_export_with_same_metric_value(self):
        rows = [result(raw_value="~0.3", raw_unit="fraction", source_table="", source_figure="Figure 1",
                       source_fragment="Figure 1:", experiment_id="E1", config_id="C01", dataset_id="DS1",
                       plot_observation=True, note=f"vector point {i}") for i in (1, 2)]
        doc = exporter.build_doc("P1", make_cache([]), ["Figure 1:", ""], Mock(), plot_rows=rows)
        self.assertEqual([r["metric_value"] for r in doc["results"]], ["0.3", "0.3"])
        self.assertEqual([r["duplicate_of"] for r in doc["results"]], ["", ""])

    def test_plot_configuration_keeps_only_printed_generator(self):
        point = result(source_table="", source_figure="Figure 1", source_fragment="Figure 1:",
                       plot_observation=True, plot_generator="Printed Gen")
        doc = exporter.build_doc("P1", make_cache([]), ["Figure 1:", ""], Mock(), plot_rows=[point])
        config_id = doc["results"][0]["config_id"]
        config = next(c for c in doc["configurations"] if c["config_id"] == config_id)
        self.assertEqual((config["generator_model"], config["rag_variant"], config["top_k"]), ("Printed Gen", "", ""))

    def test_plot_panel_conditions_preserve_distinct_partial_configurations(self):
        points = [
            result(source_table="", source_figure="Figure 1", source_fragment="Figure 1:",
                   plot_observation=True, plot_generator="Printed Gen"),
            result(source_table="", source_figure="Figure 2", source_fragment="Figure 2:",
                   plot_observation=True, plot_generator="Printed Gen", plot_conditions=("k=3",)),
        ]
        doc = exporter.build_doc("P1", make_cache([]), ["Figure 1:\nFigure 2:", ""], Mock(), plot_rows=points)
        rows = {row["source_figure"]: row for row in doc["results"]}
        self.assertNotEqual(rows["Figure 1"]["config_id"], rows["Figure 2"]["config_id"])
        configs = {config["config_id"]: config for config in doc["configurations"]}
        for row in rows.values():
            config = configs[row["config_id"]]
            self.assertEqual((config["generator_model"], config["top_k"], row["metric_k"]), ("Printed Gen", "", ""))
        self.assertIn("k=3 (PDF page 1, Figure 2)", configs[rows["Figure 2"]["config_id"]]["note"])

    def test_dataset_version_suffix_is_removed_after_linking(self):
        datasets = [
            {"dataset_id": "DS1", "dataset_name": "ExampleQA v1.2", "dataset_version": "v1.2"},
            {"dataset_id": "DS2", "dataset_name": "ExampleQA (V2.1)", "dataset_version": "v2.1"},
            {"dataset_id": "DS3", "dataset_name": "ExampleQA v3.0", "dataset_version": ""},
            {"dataset_id": "DS4", "dataset_name": "ExampleQA v1.2 / Legal", "dataset_version": "v1.2"},
        ]
        doc = build(make_cache([result(source_fragment="ExampleQA (V2.1) 0.204")], datasets=datasets))
        self.assertEqual([(d["dataset_name"], d["dataset_version"]) for d in doc["datasets"]],
                         [("ExampleQA", "v1.2"), ("ExampleQA", "v2.1"),
                          ("ExampleQA v3.0", ""), ("ExampleQA v1.2 / Legal", "v1.2")])
        self.assertEqual(doc["results"][0]["dataset_id"], "DS2")

    def test_ocr_repair_keeps_exact_number_and_same_page(self):
        cache = make_cache([
            result(raw_value="1.2", source_fragment="Cohort model Recall 1.2 truncated"),
            result(raw_value="1", source_fragment="Model Score 1"),
            result(raw_value="1.5", source_fragment="Other model 1.5"),
        ])
        cache["ocr"] = True
        doc = exporter.build_doc("P1", cache, ["model Recall 1.2 Model Score 10", "Other model 1.5"], Mock())
        rows = doc["results"]
        self.assertEqual(rows[0]["source_fragment"], "model Recall 1.2")
        self.assertEqual(rows[0]["metric_value"], "1.2")
        self.assertEqual(rows[1]["source_fragment"], "")
        self.assertEqual(rows[2]["source_page"], "1")
        for row in rows[1:]:
            self.assertIn("quote not verified in OCR text", row["note"])

    def test_ocr_table_quote_with_different_value_is_logged_without_discarding_result(self):
        cache = make_cache([result(raw_value="0.83", source_fragment="Cohort A 0.65")])
        cache["ocr"] = True
        doc = exporter.build_doc("P1", cache, ["Cohort A 0.65", ""], Mock())
        row = doc["results"][0]
        self.assertEqual((row["raw_value"], row["source_page"], row["source_table"], row["source_fragment"]),
                         ("0.83", "1", "Table 1", ""))
        self.assertTrue(any(issue["record_ids"] == row["result_id"] and "Cohort A 0.65" in issue["description"]
                            and issue["source_fragment"] == "" for issue in doc["issues"]))

    def test_ocr_repair_preserves_result_identity(self):
        cache = make_cache([result(config_id="C01", dataset_id="DS1", source_fragment=prefix + " Model 0.204")
                            for prefix in ("Prefix", "Another")])
        cache["ocr"] = True
        doc = exporter.build_doc("P1", cache, ["Model 0.204", ""], Mock())
        self.assertEqual([r["source_fragment"] for r in doc["results"]], ["Model 0.204", "Model 0.204"])
        self.assertEqual(doc["results"][1]["duplicate_of"], "R001")

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
        self.assertEqual(exporter.k_from_name("Recall", "top-20"), "20")
        self.assertEqual(exporter.k_from_name("Recall", "k = 7."), "7")
        self.assertEqual(exporter.k_from_name("Recall@3", "k = 7"), "")
        self.assertEqual(exporter.k_from_name("OC@0,8", "top-5.5"), "")

    def test_family_labels_require_source_evidence_and_keep_ids(self):
        rows = [{"dataset_id":"DS1", "dataset_name":"Corpus - Biology", "dataset_version":"", "note":""},
                {"dataset_id":"DS2", "dataset_name":"Corpus - Physics", "dataset_version":"", "note":""}]
        exporter._canonicalize_datasets(rows, ["Corpus subsets Biology 100"])
        self.assertEqual(rows[0]["dataset_name"], "Corpus - Biology")
        exporter._canonicalize_datasets(rows, ["Corpus subsets Biology 100 Physics 200"])
        self.assertEqual([(r["dataset_id"], r["dataset_name"]) for r in rows], [("DS1", "Biology"), ("DS2", "Physics")])
        self.assertEqual(rows[0]["note"], "Dataset family: Corpus")

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
    def test_recovery_adds_only_unique_unseen_cells_with_consistent_context(self):
        from decimal import Decimal

        from plugins.rag.table_context import TableCell, recover_missing

        rows = [result(experiment_id="E1", task_id="T1", raw_value="0.204", raw_unit="fraction")]
        def cell(number, dataset="DS2", configs=None):
            return TableCell(dataset, "method", configs or {"C01"}, False, number)

        def key(number, percent=False):
            return ("1", "1", "em", (Decimal(number), percent))

        cells = {key("0.204"): [cell("0.204")], key("0.31"): [cell(".31")],
                 key("0.42"): [cell(".42"), cell(".42", "DS1")], key("0.50"): [cell(".50", configs={"C01", "C02"})],
                 key("0.51"): [cell(".51")], key("0.51", True): [cell(".51%")], key("0.99"): [cell(".99")]}
        pages = ["0.204 .31 .42 .50 .51 .51%"]
        recovered = recover_missing(rows, cells, pages)
        self.assertEqual([(r["dataset_id"], r["config_id"], r["raw_value"], r["source_fragment"]) for r in recovered],
                         [("DS2", "C01", ".31", ".31")])
        conflict = rows + [result(experiment_id="E2", task_id="T1", raw_value="0.204", raw_unit="fraction")]
        self.assertEqual(recover_missing(conflict, cells, pages), [])
        self.assertEqual(recover_missing(rows + [result(result_origin="cited")], cells, pages), [])

    def test_explicit_dataset_aliases_retained_as_candidates_with_conflicts(self):
        from plugins.rag.table_context import dataset_aliases

        aliases = dataset_aliases([("A", "Dataset Alpha"), ("B", "Dataset Beta")], [
            "Dataset Alpha (ALPH) is used here. CTX: Dataset Alpha, BET: Dataset Beta.",
            "Dataset Beta (CTX) is used elsewhere. AL collects unrelated data.",
        ])
        self.assertEqual(aliases, {"alph": {"A"}, "bet": {"B"}, "ctx": {"A", "B"}})

    def test_caption_metric_and_explicit_alias_support_a_single_metric_table(self):
        from core.pdf_processor import TextLine

        layout = {1: [TextLine(x, x + 20, y, name) for x, y, name in [
            (10, 10, "Table 1"), (10, 20, "EM over the test corpora."),
            (10, 30, "Method"), (100, 30, "ALPH"), (200, 30, "BET"), (300, 30, "Overall"),
            (10, 40, "Dense Retrieval"), (100, 40, "0.21"), (200, 40, "0.34"), (300, 40, "0.28"),
            (10, 50, "Sparse Retrieval"), (100, 50, "0.30"), (200, 50, "0.40"), (300, 50, "0.40"),
        ]]}
        configs = [{"config_id": "C01", "rag_variant": "Dense Retrieval", "generator_model": "Acme A"},
                   {"config_id": "C02", "rag_variant": "Sparse Retrieval", "generator_model": "Acme A"}]
        datasets = [{"dataset_id": "DS1", "dataset_name": "Dataset Alpha"},
                    {"dataset_id": "DS2", "dataset_name": "Dataset Beta"}]
        rows = [result(raw_value="0.34", source_fragment="0.34", config_id="C01", dataset_id="DS1"),
                result(raw_value="0.40", source_fragment="0.40", config_id="C02", dataset_id="DS1"),
                result(raw_value="0.34", metric_name="F1", source_fragment="0.34", config_id="C01", dataset_id="DS1")]
        pages = ["Dataset Alpha (ALPH). BET: Dataset Beta. 0.34 0.40", ""]
        doc = exporter.build_doc("P1", make_cache(rows, configs=configs, datasets=datasets), pages, Mock(), table_layout=layout)
        self.assertEqual([(r["dataset_id"], r["config_id"]) for r in doc["results"]],
                         [("DS2", "C01"), ("DS1", "C02"), ("DS1", "C01")])

    def test_positioned_table_relinks_dataset_and_joint_configuration(self):
        from core.pdf_processor import TextLine

        layout = {1: [TextLine(x, x + 20, y, name) for x, y, name in [
            (10, 10, "Table 1: Baselines using Acme A"), (100, 20, "Corpus A"), (200, 20, "Corpus B"),
            (10, 30, "Method"), (100, 30, "EM"), (200, 30, "EM"),
            (10, 40, "Dense Retrieval"), (100, 40, "0.21"), (200, 40, "0.34"),
            (10, 50, "BM25"), (100, 50, "0.34"), (200, 50, "0.34"),
            (10, 60, "Table 2: unrelated experiment"),
        ]]}
        configs = [{"config_id": cid, "rag_variant": method, "generator_model": model}
                   for cid, method, model in [("C01", "Dense Retrieval", "Acme A"),
                                              ("C02", "Dense Retrieval", "Acme B"), ("C03", "BM25", "Acme A")]]
        datasets = [{"dataset_id": "DS1", "dataset_name": "Corpus A"}, {"dataset_id": "DS2", "dataset_name": "Corpus B"}]
        rows = [result(raw_value="0.34", source_fragment="Dense Retrieval 0.34", config_id="C02", dataset_id="DS1"),
                result(raw_value="0.34", source_fragment="BM25 0.34", config_id="C03", dataset_id="DS1"),
                result(raw_value="0.34", source_fragment="0.34", config_id="C02", dataset_id="DS1"),
                result(raw_value="0.34", source_fragment="Dense Retrieval 0.34", config_id="C02", dataset_id="DS1",
                       source_table="Table 2")]
        doc = exporter.build_doc("P1", make_cache(rows, configs=configs, datasets=datasets), None, Mock(), table_layout=layout)
        self.assertEqual([(r["dataset_id"], r["config_id"]) for r in doc["results"]],
                         [("DS2", "C01"), ("DS1", "C03"), ("DS1", "C02"), ("DS1", "C02")])
        self.assertTrue(all(r["metric_value"] == "0.34" for r in doc["results"]))

    def test_indented_option_keeps_parent_configuration_and_checks_its_definition(self):
        from core.pdf_processor import TextLine

        layout = {1: [TextLine(x, x + 20, y, name) for x, y, name in [
            (10, 10, "Table 1: EM over two corpora."),
            (10, 20, "Method"), (100, 20, "Corpus A"), (200, 20, "Corpus B"),
            (10, 30, "Dense"), (100, 30, "0.12"), (200, 30, "0.24"),
            (18, 40, "+ Filter w/o RC"), (100, 40, "0.31"), (200, 40, "0.45"),
            (10, 50, "Sparse"), (100, 50, "0.31"), (200, 50, "0.45"),
        ]]}
        configs = [{"config_id": cid, "rag_variant": name} for cid, name in
                   [("C1", "Dense"), ("C2", "Dense + Filter w/o RC"), ("C3", "Sparse")]]
        datasets = [{"dataset_id": cid, "dataset_name": name} for cid, name in
                    [("D1", "Corpus A"), ("D2", "Corpus B")]]
        rows = [result(raw_value="0.45", source_fragment="0.45", config_id="C2", dataset_id="D1")]
        cache = make_cache(rows, configs=configs, datasets=datasets)
        doc = exporter.build_doc("P1", cache, ["rank cutoff (RC). 0.45", ""], Mock(), table_layout=layout)
        self.assertEqual(doc["results"][0]["dataset_id"], "D2")
        self.assertEqual(doc["configurations"][1]["rag_variant"], "Dense + Filter w/o rank cutoff")
        conflict = exporter.build_doc("P1", cache, ["rank cutoff (RC). reranker confidence (RC). 0.45", ""],
                                      Mock(), table_layout=layout)
        self.assertEqual(conflict["configurations"][1]["rag_variant"], "Dense + Filter w/o RC")

    def test_edition_name_requires_same_program_year_and_track_initials(self):
        expand = exporter._expand_track_edition
        self.assertEqual(expand("Program IR24", ["Program 2024 Information Retrieval track."]),
                         "Program Information Retrieval 2024")
        self.assertEqual(expand("Program IR24", ["Program 2023 Information Retrieval track."]), "Program IR24")
        self.assertEqual(expand("Program IR24", [
            "Program 2024 Information Retrieval track. Program 2024 Image Recognition track.",
        ]), "Program IR24")

    def test_display_labels_keep_split_codes_and_parameter_values_in_the_evidence(self):
        datasets = [{"dataset_name": "Corpus MAIN_TEST", "dataset_version": "", "note": ""},
                    {"dataset_name": "Corpus SECOND_TEST", "dataset_version": "", "note": ""}]
        exporter._canonicalize_datasets(datasets, ["MAIN_TEST is the main evaluation split."])
        self.assertEqual([row["dataset_name"] for row in datasets], ["Corpus MAIN TEST", "Corpus SECOND_TEST"])
        self.assertIn("MAIN_TEST", datasets[0]["note"])

        configs = [{"rag_variant": name} for name in ("Method alpha = 0.5", "Method alpha = 1.0", "Method beta 0.5")]
        exporter._compact_named_parameters(configs, ["The weight was α = 0.5."])
        self.assertEqual([row["rag_variant"] for row in configs], ["Method alpha0.5", "Method alpha = 1.0", "Method beta 0.5"])
        raw = result(source_fragment="Ours (Alpha only) 0.204")
        cache = make_cache([raw], configs=[{"config_id": "C01", "rag_variant": "Ours (Alpha only)"}])
        doc = exporter.build_doc("P1", cache, ["Ours (Alpha only) 0.204", ""], Mock())
        self.assertEqual(doc["configurations"][0]["rag_variant"], "Alpha only")
        self.assertEqual(doc["results"][0]["source_fragment"], raw["source_fragment"])

    def test_model_modes_and_redactions_need_printed_evidence(self):
        configs = [{"rag_variant": "Route", "generator_model": "Acme 2B"},
                   {"rag_variant": "Route-Base", "generator_model": "Acme 2B Base"},
                   {"rag_variant": "Route-Chat", "generator_model": "Acme 2B Instruct"}]
        exporter._strip_repeated_backbone_modes(configs, ["The table shows Route-Base and Route-Chat."])
        self.assertEqual([row["rag_variant"] for row in configs], ["Route", "Route", "Route-Chat"])

        masked = "[模型名称已隐藏]-V3"
        self.assertEqual(exporter.source_generator(masked, ["Compared the Acme-V3 model."]), "Acme-V3")
        self.assertEqual(exporter.source_generator(masked, ["Compared Acme-V3 and Beta-V3."]), "")
        self.assertEqual(exporter.source_generator(masked, ["Compared the Acme-V4 model."]), "")

    def test_parameter_column_and_separate_context_fields(self):
        from core.pdf_processor import TextLine

        table = {1: [TextLine(x, x + 15, y, text) for x, y, text in [
            (10, 10, "Table 1: Parameter sweep"),
            (10, 20, "α"), (80, 20, "Corpus A"), (150, 20, "Corpus B"),
            (10, 30, "0.5"), (80, 30, "1.2"), (150, 30, "2.3"),
            (10, 40, "1.0"), (80, 40, "3.4"), (150, 40, "4.5"),
        ]]}
        configs = [{"rag_variant": "Route alpha = 1.0"}, {"rag_variant": "Route alpha = 0.7"}]
        exporter._compact_named_parameters(configs, [], table)
        self.assertEqual([row["rag_variant"] for row in configs], ["Route alpha1.0", "Route alpha = 0.7"])

        config = {"rag_variant": "Route with News KB w/o rerank", "context_strategy": "retrieve from News KB"}
        exporter._strip_repeated_context_labels([config], ["Route, the base method, uses this variant."])
        self.assertEqual(config["rag_variant"], "Route w/o rerank")
        self.assertIn("Route with News KB w/o rerank", config["note"])

    def test_aggregate_link_requires_unique_cell_and_verified_quote(self):
        from core.pdf_processor import TextLine
        from plugins.rag.table_context import link_aggregates

        layout = {1: [TextLine(x, x + 20, y, text) for x, y, text in [
            (10, 10, "Table 1: EM / F1 results"),
            (10, 20, "Method"), (100, 20, "Corpus A"), (180, 20, "Corpus B"), (260, 20, "Average"),
            (10, 30, "A"), (100, 30, ".31 / .44"), (180, 30, ".50 / .82"), (260, 30, ".40 / .63"),
            (10, 40, "B"), (100, 40, ".41 / .72"), (180, 40, ".40 / .85"), (260, 40, ".40 / .78"),
        ]]}
        base = dict(publication_id="P1", source_page="1", source_table="Table 1", dataset_id="",
                    result_origin="primary", extraction_status="extracted")
        rows = [dict(base, metric_name="F1", raw_value=".63", source_fragment=".40 / .63"),
                dict(base, metric_name="EM", raw_value=".40", source_fragment=".40 / .63"),
                dict(base, metric_name="F1", raw_value=".78", source_fragment="unverified .78")]
        datasets = []
        link_aggregates(rows, layout, [".40 / .63 .40 / .78"], datasets)
        self.assertEqual([row["dataset_id"] for row in rows], ["DSA1", "", ""])
        self.assertEqual(datasets[0]["dataset_name"], "Average")

    def test_scheme_columns_do_not_inherit_neighboring_model_scope(self):
        from core.pdf_processor import TextLine
        from plugins.rag.table_context import link_table_configurations

        layout = {1: [TextLine(10, 140, 1, "Table 1: Interleaved results")]}
        tokens = {1: [TextLine(x, x + 9, y, text) for x, y, text in [
            (40, 5, "LLM"), (110, 5, "Scheme"),
            (20, 10, "Metrics"), (90, 10, "Metrics"),
            (40, 15, "Acme"), (110, 15, "Dense"), (140, 15, "Sparse"),
            (20, 20, "Accuracy"), (40, 20, ".95"), (90, 20, "Coverage"), (110, 20, ".50"), (140, 20, ".70"),
        ]]}
        base = dict(publication_id="P1", source_page="1", source_table="Table 1", dataset_id="D1",
                    config_id="C01", result_origin="primary", extraction_status="extracted")
        rows = [dict(base, metric_name="Coverage", raw_value=".50", source_fragment="Coverage .50"),
                dict(base, metric_name="Accuracy", raw_value=".95", source_fragment="Accuracy .95"),
                dict(base, metric_name="Coverage", raw_value=".70", source_fragment="Coverage .70"),
                dict(base, metric_name="Coverage", raw_value=".70", source_fragment=".70")]
        configs = [dict(publication_id="P1", config_id="C01", rag_variant="Dense", generator_model="Acme")]
        link_table_configurations(rows, layout, tokens, ["Coverage .50 Accuracy .95 Coverage .70"], configs, [])
        self.assertEqual([row["config_id"] for row in rows], ["CS1", "C01", "C01", "C01"])
        self.assertEqual((configs[-1]["rag_variant"], configs[-1]["generator_model"]), ("Dense", ""))

    def test_generator_block_relinks_only_the_same_method_and_settings(self):
        from core.pdf_processor import TextLine
        from plugins.rag.table_context import link_table_configurations

        layout = {1: [TextLine(10, 200, 1, "Table 1: Independent metric blocks")]}
        tokens = {1: [TextLine(x, x + 9, y, text) for x, y, text in [
            (40, 5, "Generator"), (110, 5, "Judge"),
            (20, 10, "Metrics"), (90, 10, "Metrics"),
            (40, 15, "Aurora"), (60, 15, "Nimbus"), (110, 15, "Nimbus"),
            (20, 20, "Accuracy"), (40, 20, ".91"), (60, 20, ".86"), (90, 20, "Coverage"), (110, 20, ".52"),
        ]]}
        base = dict(publication_id="P1", source_page="1", source_table="Table 1", dataset_id="D1",
                    config_id="C01", result_origin="primary", extraction_status="extracted")
        rows = [dict(base, metric_name="Accuracy", raw_value=".86", source_fragment="Accuracy .91 .86"),
                dict(base, metric_name="Coverage", raw_value=".52", source_fragment="Coverage .52"),
                dict(base, metric_name="Accuracy", raw_value=".91", source_fragment="fabricated .91")]
        configs = [dict(config_id="C01", rag_variant="Dense", generator_model="Aurora", top_k="5"),
                   dict(config_id="C02", rag_variant="Dense", generator_model="Nimbus", top_k="5"),
                   dict(config_id="C03", rag_variant="Dense", generator_model="Nimbus", top_k="10")]
        link_table_configurations(rows, layout, tokens, ["Accuracy .91 .86 Coverage .52"], configs, [])
        self.assertEqual([row["config_id"] for row in rows], ["C02", "C01", "C01"])

    def test_ordered_metric_legend_expands_only_unambiguous_names(self):
        rows = [{"metric_name": metric, "note": "", "raw_value": "12.5", "source_fragment": "printed evidence"}
                for metric in ("FAL", "Late", "UNC.", "OTHER")]
        exporter._expand_metric_abbreviations(rows, [
            "FAL, LATE, and UNC. denote false alerts, delayed responses, and unclear-answer rates, respectively.",
            "LATE and ANS denote late retrieval and accepted answers, respectively.",
            "OTHER and BAD denote an incomplete list, respectively.",
        ])
        self.assertEqual([row["metric_name"] for row in rows],
                         ["false alerts rate", "Late", "unclear-answer rate", "OTHER"])
        self.assertTrue(all(row["raw_value"] == "12.5" and row["source_fragment"] == "printed evidence"
                            for row in rows))

    def test_full_rate_and_relative_efficiency_names_keep_their_scopes(self):
        base = dict(source_page="1", source_table="Table 1", metric_unit="%", raw_unit="%",
                    note="", config_id="C1", dataset_id="D1", experiment_id="E1", metric_value="1.00")
        rates = [dict(base, metric_name="Valid Answer"),
                 dict(base, metric_name="Other Signal"),
                 dict(base, metric_name="Valid Answer", metric_unit="fraction")]
        exporter._name_printed_rates(rates, ["The valid-answer rate is measured independently."])
        self.assertEqual([r["metric_name"] for r in rates], ["Valid Answer rate", "Other Signal", "Valid Answer"])

        step = dict(base, metric_name="Step", raw_unit="", metric_unit="")
        time = dict(step, metric_name="Time")
        other_step = dict(step, source_table="Table 2")
        exact_time = dict(time, source_table="Table 2", raw_unit="s", metric_unit="s")
        rows = [step, time, other_step, exact_time]
        exporter._name_efficiency_columns(rows, [
            "Step Time. We measure retrieval-and-generation steps and time for each query relative to the baseline."
        ])
        self.assertEqual([r["metric_name"] for r in rows],
                         ["retrieval and generation steps per query", "relative time per query", "Step", "Time"])
        self.assertTrue(all(r["metric_value"] == "1.00" for r in rows))

    def test_accuracy_uses_the_matching_table_caption_only(self):
        first = dict(metric_name="Accuracy", source_page="2", source_table="Table 3", note="",
                     raw_value="0.85", source_fragment="Method 0.85")
        rows = [first, dict(first, source_table="Table 4"), dict(first, source_page="3"),
                dict(first, metric_name="Accuracy@5")]
        exporter._name_caption_accuracy(rows, {
            ("2", "table 3"): "Table 3: LLM QA accuracy by method.",
            ("2", "table 4"): "Table 4: Results compared against QA accuracy.",
        })
        self.assertEqual([row["metric_name"] for row in rows],
                         ["QA accuracy", "Accuracy", "Accuracy", "Accuracy@5"])
        self.assertEqual((first["raw_value"], first["source_fragment"]), ("0.85", "Method 0.85"))

    def test_role_names_require_a_local_definition(self):
        rows = [dict(metric_name=name, source_page=page, source_table=table, note="")
                for name, page, table in [
                    ("Accuracy", "1", "Table 2(a)"), ("Score", "1", "Table 3"),
                    ("Score", "1", "Table 4"), ("Accuracy", "2", "Table 5"),
                ]]
        pages = [
            "We used accuracy—based on whether the model response matched the correct answer. "
            "Table 2: Results. Values represent accuracy scores. "
            "Table 3: Accuracy and Judge-Score. Score is the score verified by LLM. "
            "Table 4: Another comparison. LLM evaluation frameworks were compared. "
            "Performance was evaluated using the accuracy metric.",
            "The results of the evaluation are summarized in Table 5. Methods compared, measured by accuracy.",
        ]
        exporter._name_caption_accuracy(rows, {
            ("1", "table 2"): "Table 2: Results.",
            ("1", "table 3"): "Table 3: Accuracy and Judge-Score.",
            ("1", "table 4"): "Table 4: Another comparison.",
        }, pages)
        exporter._name_evaluator_accuracy(rows, pages)
        self.assertEqual([r["metric_name"] for r in rows],
                         ["Answer accuracy", "LLM Score", "Score", "Evaluator accuracy"])

    def test_figure_rate_preserves_unknown_correctness_denominator(self):
        base = dict(metric_name="Attempted", source_page="1", source_figure="Figure 3", metric_unit="%", note="")
        rows = [base, dict(base, metric_name="Correct"), dict(base, source_figure="Figure 4")]
        exporter._name_figure_attempts(rows, ["Fig. 3. Comparison showing percent attempts and correct."])
        self.assertEqual([r["metric_name"] for r in rows], ["Attempt rate", "Correct", "Attempted"])

    def test_domain_columns_disambiguate_only_unique_verified_cells(self):
        from core.pdf_processor import TextLine
        from plugins.rag.table_context import link_dataset_domains

        layout = {1: [TextLine(x, x + 10, y, label) for x, y, label in [
            (114, 10, "News"), (214, 10, "Research"), (314, 10, "Overall"),
            (10, 15, "Method"),
            (100, 20, "Acc"), (128, 20, "Score"), (200, 20, "Acc"),
            (228, 20, "Score"), (300, 20, "Acc"), (328, 20, "Score"),
            (10, 30, "Dense"), (100, 30, ".20"), (128, 30, ".14"),
            (200, 30, ".32"), (228, 30, ".14"), (300, 30, ".26"), (328, 30, ".18"),
            (10, 43, "Table 2: Metrics on Corpus across different domains."),
        ]]}
        common = dict(source_page="1", source_table="Table 2", config_id="C1", dataset_id="D1",
                      result_origin="primary", extraction_status="extracted")
        rows = [dict(common, metric_name="Acc", raw_value=".32", source_fragment="Dense .32"),
                dict(common, metric_name="Score", raw_value=".14", source_fragment="Dense .14"),
                dict(common, metric_name="Acc", raw_value=".26", source_fragment="fabricated .26")]
        datasets = [dict(dataset_id="D1", dataset_name="Corpus", note="")]
        link_dataset_domains(rows, layout, ["Dense .32 Dense .14 .26"], datasets,
                             [dict(config_id="C1", rag_variant="Dense")])
        self.assertEqual([r["dataset_id"] for r in rows], ["DSD1", "D1", "D1"])
        self.assertEqual(datasets[-1]["dataset_name"], "Corpus Research")

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

    def test_non_numeric_is_retained_and_linked_to_issue(self):
        d = build(make_cache([result(raw_value="significantly better")]))
        self.assertEqual(len(d["results"]), 1)
        row = d["results"][0]
        self.assertEqual((row["raw_value"], row["metric_value"], row["extraction_status"]),
                         ("significantly better", "", "present_not_extractable"))
        self.assertTrue(any(i["check_name"] == "non_numeric_result" and i["record_ids"] == row["result_id"] for i in d["issues"]))

    def test_table_dataset_inheritance_keeps_ambiguity_and_explicit_ids(self):
        rows = [result(source_table="Table 7", dataset_id="DS1"), result(source_table="Table 7"),
                result(source_table="Table 8", dataset_id="DS1"), result(source_table="Table 8", dataset_id="DS2"),
                result(source_table="Table 8"), result(source_table="Table 9")]
        doc = build(make_cache(rows))
        self.assertEqual([r["dataset_id"] for r in doc["results"]], ["DS1", "DS1", "DS1", "DS2", "", ""])

    def test_duplicate_marking_preserves_experiments_and_variants(self):
        shared = {"config_id": "C01", "dataset_id": "DS1", "task_id": "T1"}
        doc = build(make_cache([result(experiment_id="E1", **shared), result(experiment_id="E1", **shared),
                                result(experiment_id="E2", **shared),
                                result(experiment_id="E1", metric_variant="strict", **shared)]))
        self.assertEqual([r["duplicate_of"] for r in doc["results"]], ["", "R001", "", ""])

    def test_domain_rules_keep_rows_and_clear_unverified_issue_quotes(self):
        rows = [result(metric_name="Recall@5", metric_variant="top-7", raw_value="120%", config_id="C01", dataset_id="DS1"),
                result(metric_name="Latency", raw_value="0", raw_unit="s", baseline_value="0.5"),
                result(metric_name="Accuracy", source_page=9, raw_value="0.5"),
                result(metric_name="Accuracy", raw_value="0.5", baseline_value="50%")]
        cache = make_cache(rows)
        cache["meta"]["issues"] = [{"check_name":"manual_review", "description":"Review", "source_page":1,
                                      "source_fragment":"quoted text absent"}]
        doc = exporter.build_doc("P1", cache, [exporter.norm(TEXT), ""], Mock())
        self.assertEqual([r["metric_value"] for r in doc["results"]], ["120", "0", "", "0.5"])
        self.assertEqual(doc["results"][1]["baseline_value"], "500")
        self.assertEqual(doc["results"][2]["raw_value"], "0.5")
        self.assertEqual(doc["results"][3]["baseline_value"], "")
        rules = {(i["check_name"], i["record_ids"]) for i in doc["issues"]}
        self.assertTrue({("RULE_SCALE_BOUNDS", "R001"), ("RULE_SCALE_BOUNDS", "R002"),
                         ("RULE_AT_K_CONSISTENCY", "R001"), ("RULE_PROVENANCE_COMPLETE", "R003"),
                         ("RULE_UNIT_AMBIGUITY", "R004")} <= rules)
        manual = next(i for i in doc["issues"] if i["check_name"] == "manual_review")
        self.assertEqual((manual["source_page"], manual["source_fragment"]), ("1", ""))

    def test_verify_rows_exported(self):
        c = make_cache([result()])
        c["verify"] = {"1": {"results": [result(raw_value="0.77", source_fragment="Vanilla RAG 0.77")]}}
        self.assertEqual(len(build(c)["results"]), 2)


class Pipeline(unittest.TestCase):
    def test_legacy_cache_resumes_only_missing_pages_with_saved_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pdf = root / "PAPER.pdf"
            old = make_cache([result()])
            old.update(version=2, complete=False, mode="text", window=2, n_pages=3)
            old["windows"] = {"1-2": {"results": [result()]}}
            llm_client.save_cache(root, pdf.stem, old)
            info = pdf_processor.PdfInfo(pdf, 3, ["old input", "old input", "last page"])
            with patch.object(pipeline, "inspect_pdf", return_value=info) as inspect, \
                    patch.object(pipeline, "_window", return_value={"results": []}) as extract, \
                    patch.object(pipeline, "_gen") as generate:
                self.assertTrue(pipeline.process_document(pdf, Mock(text_only=True), root, False, 3, "auto")[0])
            inspect.assert_called_once_with(pdf, ocr=False, structured=False)
            generate.assert_not_called()
            self.assertEqual(extract.call_args.args[3:5], (3, 3))
            final = llm_client.load_cache(root, pdf.stem)
            self.assertTrue(final["complete"])
            self.assertEqual(final["windows"]["1-2"], old["windows"]["1-2"])
            self.assertEqual(final["result_plan"], "page-v1")

    def test_plot_context_requires_printed_method_and_no_unmapped_parameter(self):
        from plugins.rag.plot_recovery import _panel_configuration

        configs = [{"config_id": "C1", "rag_variant": "Sparse search", "generator_model": "Model 2"}]
        self.assertEqual(_panel_configuration("Corpus — Sparse search / Model-2", "Model 2", configs), "C1")
        self.assertEqual(_panel_configuration("Corpus — Model-2", "Model 2", configs), "")
        self.assertEqual(_panel_configuration("Sparse search / Model-2 k=12", "Model 2", configs), "")

    def test_unmapped_dataset_header_does_not_shift_neighbor_columns(self):
        from core.pdf_processor import TextLine
        from plugins.rag.table_context import _columns

        heads = [TextLine(i * 100 + 40, i * 100 + 60, 10, name)
                 for i, name in enumerate(["Alpha", "unmapped", "Beta"])]
        metrics = [TextLine(i * 100 + x, i * 100 + x + 10, 20, name)
                   for i in range(3) for x, name in [(25, "EM"), (65, "F1")]]
        result = _columns(heads, metrics, {"alpha": "A", "beta": "B"})
        self.assertEqual([(name, ds) for _, name, ds in result],
                         [("em", "A"), ("f1", "A"), ("em", ""), ("f1", ""), ("em", "B"), ("f1", "B")])

    def test_slice_overlap_keeps_distinct_conditions(self):
        from plugins.rag import pipeline

        row = result(experiment_id="E1", metric_variant="micro", metric_k="5")
        self.assertEqual(len(pipeline._dedupe([row, dict(row, note="overlap"), dict(row, metric_variant="macro"),
                                               dict(row, metric_k="10"), dict(row, experiment_id="E2")])), 4)

    def _run(self, workers):
        names = [pathlib.Path(f"D{i:03d}.pdf") for i in range(1, 9)]

        def fn(p):
            time.sleep(0.02 * (hash(p.stem) % 3))
            return (True, f"ok {p.stem}") if p.stem != "D005" else (None, "SKIPPED_SCAN")
        return pipeline.run_documents(names, fn, workers)

    def test_workers_determinism(self):
        self.assertEqual(self._run(1), self._run(4))

    def test_header_preserved_on_split(self):
        lines = ["4.2 Evaluation results", "Older context", "Shared settings", "Corpus labels",
                 "Table 1: Results", "Method EM F1"] + [f"row{i} 0.{i} 0.{i}" for i in range(30)]
        hdr = pipeline._header(lines, 20)
        self.assertEqual(hdr, ["4.2 Evaluation results", "Shared settings", "Corpus labels", "Table 1: Results", "Method EM F1"])
        contents = lambda _prompt, _first, _last, text: text
        with patch.object(pipeline, "_gen", side_effect=[llm_client.TruncatedResponseError(),
                {"results": []}, llm_client.TruncatedResponseError(), {"results": []}, {"results": []}]) as generate:
            pipeline._part(Mock(), contents, make_cache([])["meta"], 1, lines, "P1")
        for call in generate.call_args_list[2:]:
            self.assertIn("\n".join([pipeline.HDR_MARK, *hdr, pipeline.HDR_END]), call.args[1])

    def test_verify_page_selection(self):
        dense = " ".join(f"{i}.5" for i in range(60))
        cache = {"windows": {"1-2": {"results": [{"source_page": 1, "source_fragment": "a"}] * 3}}}
        self.assertEqual(pipeline.select_verify_pages([dense, "text only"], cache), [1])
        full = {"windows": {"1-2": {"results": [{"source_page": 1, "source_fragment": ""}] * 50}}}
        self.assertEqual(pipeline.select_verify_pages([dense], full), [])


class TableWindows(unittest.TestCase):
    def test_compact_format_round_trips_every_result_field(self):
        from plugins.rag.schemas import COMPACT_FIELDS, CompactWindow, Result
        from pydantic import ValidationError

        self.assertEqual(set(COMPACT_FIELDS), set(Result.model_fields))
        row = Result.model_validate({**dict.fromkeys(COMPACT_FIELDS, ""), **result()}).model_dump()
        data = CompactWindow.model_validate({"results": [[row[field] for field in COMPACT_FIELDS]]})
        self.assertEqual(data.expanded(), {"results": [row]})
        with self.assertRaises(ValidationError):
            CompactWindow.model_validate({"results": [["too short"]]})

    def test_tables_preserve_caption_merged_cells_and_residual_pages(self):
        from plugins.rag.table_windows import plan

        page = ("## Appendix A\nTable 4: Results by corpus\n"
                '<table><tr><th colspan="2">Test</th></tr><tr><td rowspan="2">X</td><td>0.1</td></tr>'
                "<tr><td>0.2</td></tr></table>\nText reports 0.4.\n"
                "| Method | Score |\n| --- | --- |\n| B | 0.3 |\n")
        tables, residual = plan([page, "Appendix final page, 0.5"])
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0].label, "Table 4")
        self.assertIn("## Appendix A", tables[0].source(1, 2))
        self.assertIn('colspan="2"', tables[0].source(1, 2))
        self.assertIn('data-context-only="true">X', tables[0].source(1, 2))
        self.assertNotIn("0.1", tables[0].source(1, 2))
        self.assertEqual(list(tables[0].parts(1)), [(0, 1), (1, 2)])
        self.assertIn("Text reports 0.4.", residual[0])
        self.assertNotIn("0.3", residual[0])
        self.assertEqual(residual[1], "Appendix final page, 0.5")

    def test_truncation_checkpoints_each_table_slice(self):
        from plugins.rag.table_windows import Table

        table = Table(3, 1, "Table 2: Study results", "Table 2", "", (),
                      ("<tr><td>0.1</td></tr>", "<tr><td>0.2</td></tr>"), "html")
        windows, splits = {}, []
        meta = make_cache([])["meta"]
        contents, persist = Mock(), Mock()
        with patch.object(pipeline, "_gen", side_effect=[
            llm_client.TruncatedResponseError(), {"results": [result()]}, llm_client.LLMError("network"),
        ]):
            with self.assertRaises(llm_client.LLMError):
                pipeline._table_part(Mock(), contents, meta, table, 0, 2, "P", windows, splits, persist)
        self.assertEqual(list(windows), ["3-T1-1-1"])
        with patch.object(pipeline, "_gen", return_value={"results": [result()]}) as generate:
            pipeline._table_part(Mock(), contents, meta, table, 0, 2, "P", windows, splits, persist)
        generate.assert_called_once()
        self.assertEqual(windows["3-T1-2-2"]["results"][0]["source_table"], "Table 2")

    def test_captioned_flattened_grid_keeps_both_header_bands(self):
        from plugins.rag.table_windows import plan

        text = ("Table 4: Results\nGroup A\nMethod Recall Accuracy F1\n"
                "X 0.1 0.2 0.3\nY 0.2 0.3 0.4\n"
                "Group B\nMethod Recall Accuracy F1\n"
                "X 0.5 0.6 0.7\nY 0.6 0.7 0.8\n\nSubsequent discussion.\n")
        tables, residual = plan([text])
        self.assertEqual([table.label for table in tables], ["Table 4", "Table 4"])
        self.assertIn("Group B", tables[1].source(0, 2))
        self.assertNotIn("0.3", tables[1].source(0, 2))
        self.assertIn("Subsequent discussion.", residual[0])


class EntityPassport(unittest.TestCase):
    def test_compact_passport_expands_to_the_cache_schema(self):
        from plugins.rag.schemas import CompactPassport, Passport

        compact = CompactPassport.model_validate({
            "publication": dict(make_cache([])["meta"]["publication"], doi="", authors=""),
            "configurations": [["C1", "Method", "Generator"]],
            "datasets": [["D1", "Corpus"]],
            "tasks": [], "experiments": [],
            "issues": [["ambiguous", "Check the source", 2]],
            "table_scopes": [],
        })
        result = compact.expanded()
        self.assertEqual(result, Passport.model_validate(result).model_dump())
        self.assertEqual(result["configurations"][0]["generator_model"], "Generator")
        self.assertEqual(result["configurations"][0]["top_k"], "")
        self.assertEqual(result["issues"][0]["source_page"], 2)

    def test_cutoff_requires_same_page_and_table_with_literal_evidence(self):
        scope = {"source_page": 1, "source_table": "Table 1", "metric_cutoffs": [
            {"metric_name": "Recall", "metric_k": "5", "source_fragment": "Recall@5"},
            {"metric_name": "Precision", "metric_k": "3", "source_fragment": "context k=3"},
        ]}
        meta = {"table_scopes": [scope]}
        self.assertEqual(exporter._passport_cutoffs(meta, ["Recall@5 context k=3", ""]),
                         {("1", "table 1", "recall"): "5"})
        self.assertFalse(exporter._passport_cutoffs(meta, ["context k=3", "Recall@5"]))
        self.assertEqual(exporter.metric_identity("nDCG @ 005"), ("nDCG", "5"))
        self.assertEqual(exporter.metric_identity("Recall@0.5"), ("Recall@0.5", ""))

    def test_only_relevant_passport_scopes_are_sent(self):
        meta = make_cache([])["meta"]
        meta["table_scopes"] = [
            {"source_page": 1, "source_table": "Table 1", "metric_cutoffs": [{"metric_k": "11"}]},
            {"source_page": 1, "source_table": "Table 2", "metric_cutoffs": [{"metric_k": "17"}]},
            {"source_page": 2, "source_table": "Table 1", "metric_cutoffs": [{"metric_k": "23"}]},
        ]
        prompt = pipeline.window_user(meta, 1, 1, table_only=True, table_label="Table 1")
        self.assertIn('"metric_k": "11"', prompt)
        self.assertNotIn('"metric_k": "17"', prompt)
        self.assertNotIn('"metric_k": "23"', prompt)

    def test_explicit_model_identifier_and_author_label(self):
        declarations = exporter._model_declarations(["Atlas-2.1 model (atlas-2.1-small-instruct)."])
        self.assertEqual(exporter.canonical_model("Atlas 2.1 Small", declarations), "atlas-2.1-small-instruct")
        self.assertEqual(exporter.canonical_model("Atlas 2.1", declarations), "Atlas 2.1")
        conflicting = declarations + [("Atlas-2.1", "atlas-2.1-small-chat")]
        self.assertEqual(exporter.canonical_model("Atlas 2.1 Small", conflicting), "Atlas 2.1 Small")
        cfg = {"config_id": "C1", "rag_variant": "Method A (Ours)", "generator_model": "Atlas 2.1 Small"}
        doc = exporter.build_doc("P1", make_cache([], configs=[cfg]),
                                 ["Atlas-2.1 model (atlas-2.1-small-instruct)."], Mock())
        self.assertEqual((doc["configurations"][0]["rag_variant"], doc["configurations"][0]["generator_model"]),
                         ("Method A", "atlas-2.1-small-instruct"))

    def test_context_uses_exact_alias_and_matching_model_format(self):
        configs = [
            {"config_id": "C1", "rag_variant": "Method Alpha", "generator_model": "Atlas 2.1 8B"},
            {"config_id": "C2", "rag_variant": "Method Alpha", "generator_model": "Atlas 2.1 4B"},
        ]
        datasets = [{"dataset_id": "D1", "dataset_name": "World of Samples"},
                    {"dataset_id": "D2", "dataset_name": "Another Dataset"}]
        r = result(config_id="", dataset_id="", source_fragment="Method Alpha WoS 0.204",
                   table_caption="Table 1: Atlas2.1-8B comparison")
        cache = make_cache([r], configs=configs, datasets=datasets)
        doc = exporter.build_doc("P1", cache, ["World of Samples (WoS; citation) Method Alpha WoS 0.204", ""], Mock())
        self.assertEqual((doc["results"][0]["config_id"], doc["results"][0]["dataset_id"]), ("C1", "D1"))


class OcrFallback(unittest.TestCase):
    pdf = pathlib.Path("synthetic.pdf")
    native = "A full native page with text that exceeds the OCR threshold."
    recognized = "A recovered scan with metric values and their surrounding text."

    def test_rapidocr_preserves_positioned_text_on_the_pdf_page(self):
        page = Mock()
        page.get_text.return_value = "words"
        inject = Mock()
        with patch.dict(sys.modules, {"pymupdf4llm.ocr.exec_ocr_interface": SimpleNamespace(exec_ocr_full=inject)}):
            self.assertEqual(ocr.recognize_page(page, dpi=180), "words")
        inject.assert_called_once_with(page, ocr._recognize_boxes, dpi=180, keep_ocr_text=False)
        page.get_text.assert_called_once_with(sort=True)

    def test_structured_pages_keep_pdf_markers_and_raw_text(self):
        doc = object()
        table = '<table><tr><th colspan="2">Scores</th></tr><tr><td>0.2</td><td>0.3</td></tr></table>'
        convert = Mock(return_value=[{"text": table}, {"text": "## Appendix\nFinal result 0.4"}, {"text": ""}])
        with patch.dict(sys.modules, pymupdf4llm=SimpleNamespace(to_markdown=convert)):
            raw = ["Scores 0.2 0.3", "Appendix Final result 0.4", "Last page survives"]
            structured = pdf_processor._structured_text(doc, raw, set())
        convert.assert_called_once_with(doc, page_chunks=True, use_ocr=False, table_output="html")
        info = pdf_processor.PdfInfo(self.pdf, 3, raw, structured_pages=structured)
        self.assertIn(f"--- PAGE 1 ---\n{table}", info.marked_text())
        self.assertIn("--- PAGE 2 ---\n## Appendix", info.marked_text())
        self.assertIn("--- PAGE 3 ---\nLast page survives", info.marked_text())
        self.assertEqual(info.pages, raw)

    def test_layout_preserves_omitted_numeric_source_text(self):
        markdown = '<table><tr><td colspan="12">0.2</td></tr></table>'
        raw = "Earlier row 0.2\nLater table row 12 and −0.4"
        output = pdf_processor._preserve_numeric_text(markdown, raw)
        self.assertIn("Later table row 12 and −0.4", output)
        self.assertNotIn("Earlier row", output)

    def test_alternate_native_table_layout_recovers_dropped_cells(self):
        native = " ".join(f"{n}.2" for n in range(10))
        table = "<table><tr><td>" + native + "</td></tr></table>"
        convert = Mock(side_effect=[[{"text": "Metric 0.2"}], [{"text": table}]])
        layout = Mock()
        with patch.dict(sys.modules, pymupdf4llm=SimpleNamespace(to_markdown=convert, use_layout=layout)):
            self.assertEqual(pdf_processor._structured_text(object(), [native], set()), [table])
        self.assertEqual(convert.call_args.kwargs["pages"], [0])
        self.assertEqual([call.args for call in layout.call_args_list], [(False,), (True,)])

    def test_collapsed_ocr_table_keeps_row_alignment(self):
        html = "<table><tr><td>Method<br/>A<br/>B</td><td>F1<br/>0.8<br/>0.9</td></tr></table>"
        page = Mock()
        page.get_text.return_value = [
            (10, 10, 40, 15, "Method"), (55, 10, 68, 15, "F1"),
            (10, 20, 14, 25, "A"), (55, 21, 64, 26, "0.8"),
            (10, 30, 14, 35, "B"), (55, 30, 64, 35, "0.9"),
        ]
        chunk = {"text": html + "\n\n", "page_boxes": [
            {"class": "table", "pos": (0, len(html) + 2), "bbox": (5, 5, 80, 40)},
        ]}
        with patch.dict(sys.modules, pymupdf=SimpleNamespace(Rect=lambda rect: rect)):
            text = pdf_processor._add_ocr_table_positions(page, chunk)
        self.assertIn(html, text)
        self.assertIn("x10: A | x55: 0.8", text)
        self.assertIn("x10: B | x55: 0.9", text)

    def test_ocr_for_mixed_pdf_and_unusable_outputs(self):
        # The native scan heuristic alone considers this document text-readable.
        pages = [Mock(get_text=Mock(return_value=t)) for t in [self.native] * 3 + [""]]
        open_pdf = Mock()
        open_pdf.return_value.__enter__ = Mock(return_value=pages)
        open_pdf.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(sys.modules, pymupdf=SimpleNamespace(open=open_pdf)), \
                patch.object(ocr, "ocr_available") as available, \
                patch.object(ocr, "recognize_page") as recognize, patch.object(llm_client, "log") as log:
            recognize.return_value = self.recognized
            info = pdf_processor.inspect_pdf(self.pdf, ocr=True)
            self.assertTrue(info.used_ocr)
            self.assertFalse(info.is_scan)
            self.assertEqual(info.pages[-1], self.recognized)
            recognize.assert_called_once_with(pages[-1])
            for installed, error, warning in [(True, None, "insufficient text on PDF page 4"),
                                               (True, RuntimeError("OCR failed"), "OCR failed"),
                                               (False, None, "OCR unavailable")]:
                with self.subTest(warning=warning):
                    available.return_value = installed
                    recognize.side_effect = error
                    recognize.return_value = "  "
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
    def test_deepseek_splits_malformed_json_at_cap_and_retries_below_cap(self):
        from plugins.rag.schemas import Window

        client = llm_client.DeepSeekClient.__new__(llm_client.DeepSeekClient)
        client.model, client.temperature, client.freq_penalty = "test", 0, 0
        client.max_out, client.max_retries, client.base, client.cap = 100, 1, 1, 1
        client._tok = llm_client.TokenCounter()

        def response(content, tokens):
            return {"usage": {"completion_tokens": tokens},
                    "choices": [{"finish_reason": "stop", "message": {"content": content}}]}

        client._post = Mock(return_value=response('{"resul', 100))
        with self.assertRaises(llm_client.TruncatedResponseError):
            client.generate_json([], "", Window)
        client._post.assert_called_once()
        client._post = Mock(side_effect=[response('{"resul', 20), response('{"results": []}', 105)])
        with patch.object(llm_client.time, "sleep") as sleep:
            self.assertEqual(client.generate_json([], "", Window), {"results": []})
        sleep.assert_called_once()

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


class VectorPlots(unittest.TestCase):
    def test_axis_fit_rejects_nonlinear_and_underconstrained_ticks(self):
        from plugins.rag.plot_recovery import _fit

        self.assertEqual(_fit([(0, 1), (50, .5), (100, 0)], 100), (-.01, 1.0))
        self.assertIsNone(_fit([(0, 1), (50, .05), (100, 0)], 100))
        self.assertIsNone(_fit([(0, 0), (100, 1)], 100))

    def test_scatter_panel_calibrates_ticks_and_keeps_coincident_markers(self):
        from pymupdf import Rect
        from plugins.rag.plot_recovery import Text, _panel

        frame = (100, 100, 220, 220)
        paths = [{"rect": Rect(*segment), "items": [("l",)]} for segment in
                 [(100, 100, 100, 220), (100, 220, 220, 220)]
                 + [(x, 220, x, 223) for x in (100, 160, 220)]
                 + [(97, y, 100, y) for y in (100, 160, 220)]]
        paths.extend({"rect": Rect(129, 159, 131, 161), "items": [("c",)] * 4, "fill": (0, 0, 1)} for _ in range(12))
        texts = [Text((x-3, 222, x+3, 228), value, True) for x, value in zip((100, 160, 220), ("0", ".5", "1"))]
        texts += [Text((90, y-2, 96, y+2), value, True) for y, value in zip((100, 160, 220), ("1", ".5", "0"))]
        texts += [Text((135, 230, 185, 238), "Precision", True), Text((79, 135, 86, 185), "Recall", False)]
        x, y, points = _panel(paths, texts, frame)
        self.assertEqual((x[:2], y[:2], len(points)), (("Precision", "fraction"), ("Recall", "fraction"), 12))
        self.assertAlmostEqual(x[2][0] * points[0][0] + x[2][1], .25)
        self.assertAlmostEqual(y[2][0] * points[0][1] + y[2][1], .5)


class SubmissionCompliance(unittest.TestCase):
    def test_partial_cache_export_requires_opt_in_and_keeps_cache_incomplete(self):
        import check_submission as cs
        from core.validator import PARTIAL_EXTRACTION
        from main import main

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source, cache_dir, output = root / "input", root / "cache", root / "out"
            source.mkdir()
            (source / "PART.pdf").touch()
            cache = make_cache([result()])
            cache.update(version=2, complete=False, mode="pdf")
            llm_client.save_cache(cache_dir, "PART", cache)
            args = ["--input", str(source), "--output", str(output), "--cache", str(cache_dir), "--rebuild-csv-only"]
            self.assertEqual(main(args), 1)
            self.assertEqual(evaluate.read(output, "results"), [])
            self.assertEqual(main([*args, "--include-partial-cache"]), 1)
            self.assertEqual(len(evaluate.read(output, "results")), 1)
            self.assertIn(PARTIAL_EXTRACTION, {row["check_name"] for row in evaluate.read(output, "issues")})
            report = cs.validate(output)
            self.assertEqual(report["errors"], [])
            self.assertTrue(any("partial extraction" in warning for warning in report["warnings"]))
            self.assertEqual(llm_client.load_cache(cache_dir, "PART"), cache)

    def test_cache_rebuild_can_repair_ocr_quote_without_api(self):
        from main import main

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source, cache_dir, output = root / "input", root / "cache", root / "out"
            source.mkdir()
            pdf = source / "SCAN.pdf"
            pdf.touch()
            cache = make_cache([result(source_fragment="prefix Vanilla RAG 0.204 suffix")])
            cache.update(version=2, complete=True, mode="text", ocr=True)
            llm_client.save_cache(cache_dir, "SCAN", cache)
            with patch.object(ocr, "ocr_pages", return_value=[TEXT, ""]) as local_ocr:
                self.assertEqual(main(["--input", str(source), "--output", str(output), "--cache", str(cache_dir),
                                       "--rebuild-csv-only", "--ocr"]), 0)
            local_ocr.assert_called_once_with(pdf)
            rows = evaluate.read(output, "results")
            self.assertEqual((rows[0]["source_fragment"], rows[0]["metric_value"]), ("Vanilla RAG 0.204", "0.204"))

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
            self.assertEqual(report["quote_checks"]["results"], [
                ["GOOD", "R001", "1", "Vanilla RAG 0.204", True],
            ])
            unresolved = cs.validate(output, source, page_reader=lambda _: ["", ""])
            self.assertEqual(unresolved["quote_checks"]["results"], [
                ["GOOD", "R001", "1", "Vanilla RAG 0.204", False],
            ])

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
