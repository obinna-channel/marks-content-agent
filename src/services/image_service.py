"""Image generation service orchestrating Imagen 3."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from src.config import get_settings
from src.services.imagen import ImagenClient, get_imagen_client


class ImageSession:
    """Tracks an active image generation session."""

    def __init__(
        self,
        session_id: str,
        original_prompt: str,
        aspect_ratio: str = "1:1",
    ):
        self.session_id = session_id
        self.original_prompt = original_prompt
        self.current_prompt = original_prompt
        self.aspect_ratio = aspect_ratio
        self.iterations: list[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc)
        self.finalized = False

    def add_iteration(self, prompt: str, image_path: str):
        """Record an iteration."""
        self.iterations.append({
            "prompt": prompt,
            "image_path": image_path,
            "created_at": datetime.now(timezone.utc),
        })
        self.current_prompt = prompt

    def finalize(self):
        """Mark session as complete."""
        self.finalized = True


class ImageService:
    """Service for generating and managing images."""

    def __init__(
        self,
        imagen_client: Optional[ImagenClient] = None,
        output_dir: Optional[Path] = None,
    ):
        self.imagen = imagen_client or get_imagen_client()
        self.output_dir = output_dir or Path(__file__).parent.parent.parent / "media_output"
        self.sessions: Dict[str, ImageSession] = {}
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self) -> str:
        """Generate a unique filename for an image."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"marks_{timestamp}_{unique_id}.png"

    def _save_image(self, image_bytes: bytes) -> Path:
        """Save image bytes to file and return path."""
        filename = self._generate_filename()
        filepath = self.output_dir / filename
        filepath.write_bytes(image_bytes)
        return filepath

    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a new image.

        Args:
            prompt: Description of the image to generate
            aspect_ratio: "1:1", "16:9", "9:16", "4:3", "3:4"
            session_id: Optional existing session ID

        Returns:
            Dict with session_id, image_path, and prompt used
        """
        settings = get_settings()
        if not settings.image_generation_enabled:
            raise ValueError("Image generation is not enabled. Set IMAGE_GENERATION_ENABLED=true")

        # Generate the image
        image_bytes = await self.imagen.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            use_brand_style=True,
        )

        if not image_bytes:
            raise ValueError("Failed to generate image")

        # Save the image
        image_path = self._save_image(image_bytes)

        # Create or update session
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
        else:
            session_id = str(uuid.uuid4())
            session = ImageSession(
                session_id=session_id,
                original_prompt=prompt,
                aspect_ratio=aspect_ratio,
            )
            self.sessions[session_id] = session

        session.add_iteration(prompt, str(image_path))

        return {
            "session_id": session_id,
            "image_path": str(image_path),
            "image_bytes": image_bytes,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "iteration": len(session.iterations),
        }

    async def regenerate_with_feedback(
        self,
        session_id: str,
        feedback: str,
    ) -> Dict[str, Any]:
        """
        Regenerate an image with user feedback.

        Args:
            session_id: The session to iterate on
            feedback: User's modification request

        Returns:
            Dict with updated session info
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if session.finalized:
            raise ValueError("Session has been finalized")

        # Generate with feedback
        image_bytes = await self.imagen.generate_with_feedback(
            original_prompt=session.current_prompt,
            feedback=feedback,
            aspect_ratio=session.aspect_ratio,
        )

        if not image_bytes:
            raise ValueError("Failed to generate image")

        # Save the image
        image_path = self._save_image(image_bytes)

        # Build new prompt for tracking
        new_prompt = f"{session.current_prompt}\n\nModification: {feedback}"
        session.add_iteration(new_prompt, str(image_path))

        return {
            "session_id": session_id,
            "image_path": str(image_path),
            "image_bytes": image_bytes,
            "prompt": new_prompt,
            "feedback": feedback,
            "aspect_ratio": session.aspect_ratio,
            "iteration": len(session.iterations),
        }

    def finalize_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Finalize a session, marking it as complete.

        Args:
            session_id: The session to finalize

        Returns:
            Final session info or None if not found
        """
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        session.finalize()

        return {
            "session_id": session_id,
            "original_prompt": session.original_prompt,
            "final_prompt": session.current_prompt,
            "iterations": len(session.iterations),
            "final_image": session.iterations[-1]["image_path"] if session.iterations else None,
        }

    def get_session(self, session_id: str) -> Optional[ImageSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Remove old sessions to free memory."""
        now = datetime.now(timezone.utc)
        to_remove = []

        for session_id, session in self.sessions.items():
            age_hours = (now - session.created_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                to_remove.append(session_id)

        for session_id in to_remove:
            del self.sessions[session_id]


# Singleton instance
_image_service: Optional[ImageService] = None


def get_image_service() -> ImageService:
    """Get the image service singleton instance."""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service
