from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from typing import Any

from scrapling.fetchers import Fetcher

GQL_URL = "https://gql.tokopedia.com/graphql"

REQ_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "X-Source": "tokopedia-lite",
    "X-Device": "desktop",
    "X-Tkpd-Lite-Service": "zeus",
    "X-Price-Center": "true",
    "X-Tkpd-Pdpb": "0",
    "X-Version": "2a71be3",
    "Bd-Device-Id": "2312119391371541512",
}

REVIEW_LIST_QUERY = """query productReviewList($productID: String!, $page: Int!, $limit: Int!, $sortBy: String, $filterBy: String) {
    productrevGetProductReviewList(productID: $productID, page: $page, limit: $limit, sortBy: $sortBy, filterBy: $filterBy) {
        list {
            id: feedbackID
            variantName
            message
            productRating
            reviewCreateTime
            reviewCreateTimestamp
        }
        hasNext
        totalReviews
    }
}
"""


@dataclass
class Product:
    id: str
    name: str
    url: str


@dataclass
class Review:
    product_id: str
    product_name: str
    review_id: str
    rating: int | None
    text: str
    created_at: str | None
    variant: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def scrape_review(prod_url: str, max_rvw: int | None = None, max_pages: int = 100) -> list[Review]:
    product = Product(
        id=get_product(prod_url),
        name=resolve_slug(prod_url),
        url=prod_url,
    )
    return scrape_product_review(product=product, max_reviews=max_rvw, max_pages=max_pages)


def get_product(url: str) -> str:
    return extract_product_id(url) or fallback_url_extractor(url)


def resolve_slug(url: str) -> str:
    slug = url.split("?")[0].rstrip("/").split("/")[-1]
    slug = re.sub(r"-(\d+)$", "", slug)
    return slug


def extract_product_id(url: str) -> str | None:
    if not url:
        return None
    slug = url.split("?")[0].rstrip("/").split("/")[-1]
    m = re.search(r"-(\d+)$", slug)
    return m.group(1) if m else None


def fallback_url_extractor(url: str) -> str:
    m = re.search(r"tokopedia.\com/([^/]+)/([^/?#]+)", url)
    if not m:
        raise ValueError(f"Unknown product URL: {url}")
    shop_domain, product_key = m.group(1), m.group(2)

    payload = [{
        "operationName": "PDPGetLayoutQuery",
        "variables": {
            "shopDomain": shop_domain,
            "productKey": product_key
        },
        "query": ""
    }]

    data = _gql_call(payload, url)
    try:
        return str(data[0]["data"]["pdpGetLayout"]["basicInfo"]["id"])
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Failed to resolve extractor. Product ID: {e}")


def _gql_call(payload: list[dict], reff: str) -> Any:
    page = Fetcher.post(
        GQL_URL,
        json=payload,
        headers={
            **REQ_HEADERS,
            "Referer": reff
        },
        impersonate="chrome",
        stealthy_headers=True,
        timeout=30,
        retries=3,
        retry_delay=2
    )
    if page.status != 200:
        raise RuntimeError(f"HTTP status from graphql: {page.status}")
    return page.json()


def scrape_product_review(product: Product, max_reviews: int | None = None, max_pages: int = 100) -> list[Review]:
    collected: list[Review] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        payload = [{
            "operationName": "productReviewList",
            "variables": {
                "productId": product.id,
                "page": page,
                "limit": 20,
                "sortBy": "informative_score desc",
                "filterBy": ""
            },
            "query": REVIEW_LIST_QUERY
        }]
        data = _gql_call(payload, product.url or "https://www.tokopedia.com")

        try:
            block = data[0]["data"]["productrevGetProductReviewList"]
            raw_list = block.get("list") or []
            has_next = bool(block.get("hasNext"))
        except (KeyError, IndexError, TypeError):
            break

        for raw in raw_list:
            r = _parse_review(raw, product.id, product.name)
            if r is None or (r.review_id and r.review_id in seen):
                continue
            seen.add(r.review_id)
            collected.append(r)
            if max_reviews is not None and len(collected) >= max_reviews:
                return collected

        if not has_next:
            break

        time.sleep(1.2)

    return collected


def _parse_review(raw: dict[str, Any], prod_id: str, prod_name: str) -> Review | None:
    txt = (raw.get("message") or "").strip()
    if not txt:
        return None
    return Review(
        product_id=prod_id,
        product_name=prod_name,
        review_id=str(raw.get("feedbackID") or raw.get("reviewID") or ""),
        rating=raw.get("productRating"),
        text=txt,
        created_at=raw.get("reviewCreateTimestamp") or raw.get("reviewCreateTime"),
        variant=raw.get("variantName"),
    )
