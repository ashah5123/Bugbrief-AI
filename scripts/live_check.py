"""Opt-in live text/vision requests through the application's normal capped endpoints."""
import argparse
import asyncio
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.config import settings
from app.auth import access_code

async def main(args):
    if not settings.gemini_api_key or not settings.free_tier_confirmed:
        print('SKIPPED: configure GEMINI_API_KEY and FREE_TIER_CONFIRMED in backend/.env. No request sent.')
        return 2
    image = None
    if args.screenshot:
        if not args.reviewed:
            print('SKIPPED: inspect/redact the screenshot, then pass --reviewed. Nothing was sent.')
            return 2
        path = Path(args.screenshot)
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            print('SKIPPED: screenshot must exist and be at most 2 MiB. Nothing was sent.')
            return 2
        mime = 'image/jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else 'image/png'
        image = (path.name, path.read_bytes(), mime)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8001', timeout=100, headers={'X-Agency-Key': access_code()}) as client:
        project = await client.post('/api/projects', json={'name': 'Live API check'})
        project.raise_for_status()
        feedback = await client.post('/api/feedback', json={'project_id': project.json()['id'], 'text': 'I clicked Pay now on checkout. Nothing happened. I expected the payment form.'})
        feedback.raise_for_status()
        feedback_id = feedback.json()['id']
        if image:
            upload = await client.post(f'/api/feedback/{feedback_id}/attachments', params={'reviewed': 'true', 'filename': image[0]}, content=image[1], headers={'Content-Type': image[2]})
            upload.raise_for_status()
            attachment_id = upload.json()['attachments'][0]['id']
            vision = await client.post(f'/api/feedback/{feedback_id}/attachments/{attachment_id}/analyze', json={'consent': True})
            if vision.is_error:
                print(f'LIVE VISION FAILED ({vision.status_code}): {vision.json().get("detail")}')
                return 1
            print('LIVE VISION PASSED: real remote request; structured observations saved. Verify them visually.')
        answer = await client.post(f'/api/feedback/{feedback_id}/clarifications', json={'question': 'What browser and device were used in this test scenario?', 'answer': 'Chrome on a desktop, as supplied for this non-sensitive test scenario.'})
        answer.raise_for_status()
        response = await client.post(f'/api/feedback/{feedback_id}/generate', json={'consent': True})
        if response.is_error:
            print(f'LIVE REPORT FAILED ({response.status_code}): {response.json().get("detail")}')
            return 1
        print('LIVE REPORT PASSED: real hosted request; schema and evidence quotations validated.')
        print('Title:', response.json()['report']['title'])
        print('Review factual accuracy manually. This is not an accuracy certification.')
        return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', help='Optional non-sensitive reviewed PNG/JPEG to upload and analyze before generation')
    parser.add_argument('--reviewed', action='store_true', help='Confirm this screenshot has been reviewed and redacted for external processing')
    arguments = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(main(arguments)))
    except (httpx.HTTPError, OSError):
        print('LIVE CHECK FAILED: local service or file access failed. Check the running backend; existing work is preserved.')
        raise SystemExit(1)
