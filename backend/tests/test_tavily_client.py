from app.clients.tavily_client import TavilyClient
from app.models.enums import SourceTierEnum


def test_paywalled_major_publications_are_classified_as_premium_news():
    assert TavilyClient._classify_source_tier("https://www.wsj.com/articles/example") == SourceTierEnum.PREMIUM_NEWS
    assert TavilyClient._classify_source_tier("https://www.nytimes.com/2026/04/09/example.html") == SourceTierEnum.PREMIUM_NEWS
    assert TavilyClient._classify_source_tier("https://www.ft.com/content/example") == SourceTierEnum.PREMIUM_NEWS


def test_reuters_remains_reputable_news():
    assert TavilyClient._classify_source_tier("https://www.reuters.com/world/us/example") == SourceTierEnum.REPUTABLE_NEWS
