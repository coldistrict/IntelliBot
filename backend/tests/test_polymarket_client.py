from app.clients.polymarket_client import PolymarketClient


class StubPolymarketClient(PolymarketClient):
    def __init__(self, payload):
        super().__init__(enabled=True)
        self.payload = payload
        self.requests = []

    def _get_json(self, path: str, *, params=None):
        self.requests.append((path, params))
        return self.payload


def test_discovers_active_event_markets_with_browser_metadata():
    client = StubPolymarketClient(
        [
            {
                "slug": "fed-decision-in-june",
                "title": "Fed decision in June",
                "category": "Economics",
                "image": "https://example.com/fed.png",
                "featured": True,
                "markets": [
                    {
                        "id": "fed-cut-june-2026",
                        "question": "Will the Fed cut rates by June 2026?",
                        "description": "Rate cut market",
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.41", "0.59"]',
                        "bestBid": "0.40",
                        "bestAsk": "0.42",
                        "liquidityNum": "25000",
                        "volume24hr": "1200",
                        "endDate": "2026-06-30T00:00:00Z",
                        "active": "true",
                        "closed": "false",
                    }
                ],
            }
        ]
    )

    records = client.discover_markets(view="popular", limit=10)

    assert client.requests[0] == (
        "/events",
        {
            "active": "true",
            "closed": "false",
            "limit": 10,
            "offset": 0,
            "order": "volume",
            "ascending": "false",
        },
    )
    assert len(records) == 1
    assert records[0].polymarket_id == "fed-cut-june-2026"
    assert records[0].title == "Will the Fed cut rates by June 2026?"
    assert records[0].url == "https://polymarket.com/event/fed-decision-in-june"
    assert records[0].yes_bid == 0.40
    assert records[0].yes_ask == 0.42
    assert records[0].spread == 0.02
    assert records[0].category == "Economics"
    assert records[0].event_title == "Fed decision in June"
    assert records[0].featured is True


def test_search_discovery_flattens_event_markets():
    client = StubPolymarketClient(
        {
            "events": [
                {
                    "slug": "bitcoin-markets",
                    "title": "Bitcoin markets",
                    "category": "Crypto",
                    "new": True,
                    "markets": [
                        {
                            "id": "bitcoin-100k",
                            "question": "Will Bitcoin hit $100k?",
                            "outcomes": ["Yes", "No"],
                            "outcomePrices": ["0.34", "0.66"],
                            "active": True,
                        }
                    ],
                }
            ]
        }
    )

    records = client.discover_markets(query="bitcoin", limit=5)

    assert client.requests[0] == ("/public-search", {"q": "bitcoin", "limit": 5})
    assert records[0].polymarket_id == "bitcoin-100k"
    assert records[0].category == "Crypto"
    assert records[0].is_new is True


def test_discovery_filters_closed_child_markets():
    client = StubPolymarketClient(
        [
            {
                "slug": "mixed-event",
                "title": "Mixed event",
                "markets": [
                    {
                        "id": "closed-market",
                        "question": "Closed market?",
                        "closed": "true",
                    },
                    {
                        "id": "inactive-market",
                        "question": "Inactive market?",
                        "active": "false",
                        "closed": "false",
                    },
                    {
                        "id": "active-market",
                        "question": "Active market?",
                        "active": "true",
                    },
                ],
            }
        ]
    )

    records = client.discover_markets(view="popular", limit=10)

    assert [record.polymarket_id for record in records] == ["active-market"]


def test_discovery_sorts_child_markets_for_the_selected_view():
    client = StubPolymarketClient(
        [
            {
                "slug": "mixed-event",
                "title": "Mixed event",
                "markets": [
                    {
                        "id": "slow-market",
                        "question": "Slow market?",
                        "active": "true",
                        "closed": "false",
                        "volume24hr": "20",
                    },
                    {
                        "id": "fast-market",
                        "question": "Fast market?",
                        "active": "true",
                        "closed": "false",
                        "volume24hr": "200",
                    },
                ],
            }
        ]
    )

    records = client.discover_markets(view="trending", limit=10)

    assert client.requests[0][1]["order"] == "volume24hr"
    assert [record.polymarket_id for record in records] == ["fast-market", "slow-market"]


def test_search_discovery_deduplicates_market_and_event_matches():
    matching_market = {
        "id": "bitcoin-100k",
        "question": "Will Bitcoin hit $100k?",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.34", "0.66"],
        "active": True,
    }
    client = StubPolymarketClient(
        {
            "markets": [matching_market],
            "events": [
                {
                    "slug": "bitcoin-markets",
                    "title": "Bitcoin markets",
                    "markets": [matching_market],
                }
            ],
        }
    )

    records = client.discover_markets(query="bitcoin", limit=5)

    assert [record.polymarket_id for record in records] == ["bitcoin-100k"]
