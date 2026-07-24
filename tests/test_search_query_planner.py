from types import SimpleNamespace
from unittest import TestCase

from services.search_query_planner import (
    build_search_queries,
    merge_search_results,
    normalize_url,
)


class SearchQueryPlannerTest(TestCase):
    def test_builds_multiple_queries_for_museums(self) -> None:
        search_run = SimpleNamespace(
            query="Найди музеи и краеведческие сообщества",
            category="музеи и краеведение",
            country="Россия",
            region="Новосибирская область",
            city=None,
            keywords=["семейная память"],
            search_queries_limit=8,
        )

        queries = build_search_queries(search_run)

        self.assertEqual(len(queries), 8)
        self.assertIn(
            "краеведческие музеи Новосибирская область",
            queries,
        )
        self.assertIn(
            "семейная память Новосибирская область",
            queries,
        )

    def test_merges_duplicate_urls(self) -> None:
        results = [
            {
                "url": "https://www.example.org/museum/?utm_source=test",
                "title": "Музей",
                "content": "Коротко",
                "query": "музеи",
            },
            {
                "url": "https://example.org/museum",
                "title": "Музей",
                "content": "Более подробное описание музея",
                "query": "краеведческие музеи",
            },
        ]

        merged = merge_search_results(results)

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]["matched_queries"],
            ["музеи", "краеведческие музеи"],
        )
        self.assertEqual(
            merged[0]["content"],
            "Более подробное описание музея",
        )

    def test_extracts_region_from_free_text_query(self) -> None:
        search_run = SimpleNamespace(
            query="Найди музеи Новосибирской области",
            category=None,
            country="Россия",
            region=None,
            city=None,
            keywords=[],
            search_queries_limit=8,
        )

        queries = build_search_queries(search_run)

        self.assertIn(
            "краеведческие музеи Новосибирской области",
            queries,
        )

    def test_normalizes_tracking_parameters(self) -> None:
        self.assertEqual(
            normalize_url(
                "https://www.Example.org/page/?utm_source=x&id=1"
            ),
            "//example.org/page?id=1",
        )
