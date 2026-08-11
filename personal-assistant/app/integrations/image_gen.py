"""AI Image Generation Integration using Pollinations.ai."""
import logging
import urllib.parse
import httpx

logger = logging.getLogger(__name__)


async def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> str:
    """Generate image and return direct image URL."""
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
    return url
