from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from tokped_scraper import scrape_review

class ScrapeRequest(BaseModel):
    url: str = Field(..., examples=["https://www.tokopedia.com/"])
    max_rvw: int | None = Field(100, ge=1, le=2000, description="Maximum number of reviews to scrape")

    @field_validator("url")
    @classmethod
    def must_be_tokopedia_url(cls, v: str) -> str:
        if not v.startswith("https://www.tokopedia.com/"):
            raise ValueError("URL must be a Tokopedia URL")
        return v


class RvwOut(BaseModel):
    review_id: str
    text: str
    rating: int | None = None
    created_at: str | None = None
    variant: str | None = None


class ScrapeResponse(BaseModel):
    product_id: str
    product_name: str
    product_url: str
    total_reviews: int
    reviews: list[RvwOut]


app = FastAPI(title="Tokopedia Product Review Scraper")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    try:
        rvws = await asyncio.to_thread(
            scrape_review, request.url, request.max_rvw
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Gagal scraping: {e}")

    if not rvws:
        raise HTTPException(404, "No reviews found")

    return ScrapeResponse(
        product_id=rvws[0].product_id,
                product_name=rvws[0].product_name,
                product_url=request.url,
                total_reviews=len(rvws),
                reviews=[
                    RvwOut(
                        review_id=r.review_id,
                        text=r.text,
                        rating=r.rating,
                        created_at=r.created_at,
                        variant=r.variant,
                    )
                    for r in rvws
                ],
    )
