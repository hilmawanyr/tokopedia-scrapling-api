from __future__ import annotations

import asyncio
import os
import secrets

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field, field_validator

from tokped_scraper import scrape_review

bearer_schema = HTTPBearer(auto_error=False)
APP_TOKEN = os.environ.get("APP_TOKEN", "")

def verif_token(cred: HTTPAuthorizationCredentials | None = Depends(bearer_schema)) -> None:
    if cred is None or not APP_TOKEN or not secrets.compare_digest(cred.credentials, APP_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

class ScrapeRequest(BaseModel):
    url: str = Field(..., examples=["https://www.tokopedia.com/"])
    total_reviews: int | None = Field(100, ge=1, le=2000, description="Maximum number of reviews to scrape")

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


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape", response_model=ScrapeResponse, dependencies=[Depends(verif_token)])
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    try:
        rvws = await asyncio.to_thread(
            scrape_review, request.url, request.total_reviews
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
