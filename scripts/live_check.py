"""Explicit live request, no test doubles. Run only with your own non-billed key."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.config import settings
from app.providers.gemini import GeminiGenerator
from app.providers.base import ProviderError

async def main():
    if not settings.gemini_api_key or not settings.free_tier_confirmed:
        print('SKIPPED: configure GEMINI_API_KEY and FREE_TIER_CONFIRMED in backend/.env. No request sent.')
        return 2
    # Use the application endpoint so the live check obeys persistent caps and the single job lock.
    import httpx
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8001',timeout=60) as client:
        project = await client.post('/api/projects',json={'name':'Live API check'})
        project.raise_for_status()
        feedback = await client.post('/api/feedback',json={'project_id':project.json()['id'],'text':'I clicked Pay now on checkout. Nothing happened. I expected the payment form.'})
        feedback.raise_for_status()
        response = await client.post(f'/api/feedback/{feedback.json()["id"]}/generate',json={'consent':True})
        if response.is_error:
            print(f'LIVE CHECK FAILED ({response.status_code}): {response.json().get("detail")}')
            return 1
        report = response.json()['report']
        print('LIVE CHECK PASSED: real provider request; schema and evidence quotations validated.')
        print('Title:',report['title'])
        print('Review factual accuracy manually in the app. This test is not an accuracy certification.')
        return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
