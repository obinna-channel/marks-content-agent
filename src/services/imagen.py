"""Imagen 3 client using Google Gemini API."""

import io
from pathlib import Path
from typing import Optional, List

from google import genai
from google.genai import types

from src.config import get_settings


class ImagenClient:
    """Client for generating images with Imagen 3 via Gemini API."""

    MODEL = "imagen-3.0-generate-002"

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self._client: Optional[genai.Client] = None
        self._style_guide: Optional[str] = None

    def _get_client(self) -> genai.Client:
        """Get or create the Gemini client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _load_style_guide(self) -> str:
        """Load brand style guide from file."""
        if self._style_guide is not None:
            return self._style_guide

        try:
            style_path = Path(__file__).parent.parent.parent / "context" / "brand" / "style_guide.md"
            if style_path.exists():
                self._style_guide = style_path.read_text()
            else:
                self._style_guide = ""
        except Exception as e:
            print(f"Error loading style guide: {e}")
            self._style_guide = ""

        return self._style_guide

    def _build_brand_prompt(self, user_prompt: str) -> str:
        """Build a prompt that incorporates brand style guidelines."""
        brand_context = """Create an image for Marks Exchange, a professional fintech platform for stablecoin FX trading.

BRAND STYLE REQUIREMENTS:
- Color palette: Navy (#18202B), Cream (#FFFEEF), Green accent (#22C55E), Red accent (#EF4444)
- Professional, minimal, clean aesthetic
- Currency symbols as decorative elements
- Global/international feel
- Sophisticated and trustworthy mood
- Abstract representations preferred over literal imagery

"""
        return f"{brand_context}REQUEST: {user_prompt}"

    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        use_brand_style: bool = True,
    ) -> Optional[bytes]:
        """
        Generate an image using Imagen 3.

        Args:
            prompt: Description of the image to generate
            aspect_ratio: Image aspect ratio - "1:1", "16:9", "9:16", "4:3", "3:4"
            use_brand_style: Whether to apply brand style guidelines to the prompt

        Returns:
            Image bytes (PNG format) if successful, None otherwise
        """
        try:
            client = self._get_client()

            # Build the final prompt
            final_prompt = self._build_brand_prompt(prompt) if use_brand_style else prompt

            # Generate the image
            response = client.models.generate_images(
                model=self.MODEL,
                prompt=final_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=aspect_ratio,
                    person_generation="allow_adult",
                ),
            )

            if response.generated_images:
                # Get the PIL image and convert to bytes
                pil_image = response.generated_images[0].image
                buffer = io.BytesIO()
                pil_image.save(buffer, format="PNG")
                return buffer.getvalue()

            return None

        except Exception as e:
            print(f"Error generating image: {e}")
            raise

    async def generate_with_feedback(
        self,
        original_prompt: str,
        feedback: str,
        aspect_ratio: str = "1:1",
    ) -> Optional[bytes]:
        """
        Regenerate an image incorporating user feedback.

        Args:
            original_prompt: The original image description
            feedback: User's feedback/modification request
            aspect_ratio: Image aspect ratio

        Returns:
            Image bytes (PNG format) if successful, None otherwise
        """
        # Combine original prompt with feedback
        modified_prompt = f"{original_prompt}\n\nModification: {feedback}"
        return await self.generate(
            prompt=modified_prompt,
            aspect_ratio=aspect_ratio,
            use_brand_style=True,
        )


# Singleton instance
_imagen_client: Optional[ImagenClient] = None


def get_imagen_client() -> ImagenClient:
    """Get the Imagen client singleton instance."""
    global _imagen_client
    if _imagen_client is None:
        _imagen_client = ImagenClient()
    return _imagen_client
