from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client
from firecrawl import FirecrawlApp
from dotenv import load_dotenv
from datetime import datetime, timezone
import os
import traceback

# Load your secret keys from .env file
load_dotenv()

# Connect to Supabase
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Connect to Firecrawl
firecrawl = FirecrawlApp(api_key=os.getenv("FIRECRAWL_KEY"))

# Create the FastAPI app
app = FastAPI()

# This defines what data we expect when someone submits a scan
class ScanRequest(BaseModel):
    url: str

# ---- ROUTE 1: Submit a URL to scan ----
@app.post("/scan")
def create_scan(request: ScanRequest):
    try:
        # Check rate limit — max 20 scans per day
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        existing = supabase.table("scans").select("id").gte("created_at", f"{today}T00:00:00Z").execute()
        if len(existing.data) >= 20:
            raise HTTPException(status_code=429, detail="Daily scan limit reached. Max 20 scans per day.")

        # Step 1: Scrape the URL with Firecrawl
        scraped = firecrawl.scrape(request.url)
        title = scraped.metadata.title if hasattr(scraped, 'metadata') and scraped.metadata else "Unknown"
        description = scraped.metadata.description if hasattr(scraped, 'metadata') and scraped.metadata else "Unknown"

        # Step 2: Save to Supabase
        result = supabase.table("scans").insert({
            "url": request.url,
            "verdict": "pending",
            "confidence": 0.0,
            "metrics": f"Title: {title} | Description: {description}"
        }).execute()

        return {"message": "Scan created", "data": result.data}

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ---- ROUTE 2: Get a scan by ID ----
@app.get("/scan/{scan_id}")
def get_scan(scan_id: int):
    try:
        result = supabase.table("scans").select("*").eq("id", scan_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Scan not found")
        return result.data[0]
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ---- ROUTE 3: Submit a vote ----
class VoteRequest(BaseModel):
    scan_id: int
    user_id: str
    vote: str  # "ai" or "not_ai"

@app.post("/vote")
def submit_vote(request: VoteRequest):
    try:
        result = supabase.table("community_votes").insert({
            "scan_id": request.scan_id,
            "user_id": request.user_id,
            "vote": request.vote
        }).execute()
        return {"message": "Vote submitted", "data": result.data}
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ---- ROUTE 4: Get votes for a scan ----
@app.get("/votes/{scan_id}")
def get_votes(scan_id: int):
    try:
        result = supabase.table("community_votes").select("*").eq("scan_id", scan_id).execute()
        ai_votes = sum(1 for v in result.data if v["vote"] == "ai")
        not_ai_votes = sum(1 for v in result.data if v["vote"] == "not_ai")
        return {
            "scan_id": scan_id,
            "ai_votes": ai_votes,
            "not_ai_votes": not_ai_votes,
            "total": len(result.data)
        }
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ---- ROUTE 5: Generate a verdict card ----
@app.post("/card/{scan_id}")
def create_card(scan_id: int):
    try:
        scan = supabase.table("scans").select("*").eq("id", scan_id).execute()
        if not scan.data:
            raise HTTPException(status_code=404, detail="Scan not found")

        card_url = f"https://deepfaket.com/cards/{scan_id}"
        result = supabase.table("verdict_cards").insert({
            "scan_id": scan_id,
            "card_image_url": card_url,
            "share_count": 0
        }).execute()
        return {"message": "Card created", "card_url": card_url}
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))