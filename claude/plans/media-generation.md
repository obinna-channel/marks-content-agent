# Plan: Brand-Consistent Media Generation with Veo 3 & Imagen 3

Integrate Google's Veo 3 (video) and Imagen 3 (image) APIs to generate brand-consistent visuals alongside text content.

---

## Goals

1. Generate images/videos that match Marks brand style
2. Use Figma designs as style references
3. Automate media creation as part of content generation flow
4. Review media in Slack before posting

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Content Generation Flow                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Generate text content (existing)                            │
│     - Topic, pillar, content body                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Analyze content for visual needs                            │
│     - What type of visual? (chart, explainer, announcement)     │
│     - Image or video?                                           │
│     - Key elements to visualize                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Generate media prompt                                       │
│     - Combine content context + brand guidelines                │
│     - Select appropriate reference images                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
┌───────────────────────┐   ┌───────────────────────┐
│  4a. Imagen 3 API     │   │  4b. Veo 3.1 API      │
│  (Static images)      │   │  (Video clips)        │
│  - $0.03-0.13/image   │   │  - $0.40-0.75/sec     │
└───────────────────────┘   └───────────────────────┘
                    │                   │
                    └─────────┬─────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Post to Slack for review                                    │
│     - Show text + media together                                │
│     - Approve / Regenerate / Edit prompt                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. Post to Twitter with media (future)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Brand Reference System

### Reference Image Categories

Store brand reference images that get attached to generation requests:

```
context/
├── marks_context.md          # Text context (existing)
└── brand/
    ├── style_guide.md        # Written brand guidelines
    ├── references/
    │   ├── charts/           # Chart/graph style references
    │   │   ├── price_chart_1.png
    │   │   ├── price_chart_2.png
    │   │   └── data_viz.png
    │   ├── typography/       # Text overlay style
    │   │   ├── headline_style.png
    │   │   └── quote_style.png
    │   ├── colors/           # Color palette references
    │   │   └── brand_colors.png
    │   ├── layouts/          # Composition references
    │   │   ├── announcement.png
    │   │   ├── education.png
    │   │   └── market_update.png
    │   └── logo/             # Logo variations
    │       ├── logo_dark.png
    │       └── logo_light.png
    └── templates/            # Figma export templates
        ├── market_commentary.png
        ├── education.png
        ├── product.png
        └── social_proof.png
```

### Pillar-to-Visual Mapping

| Pillar | Visual Type | Reference Category | Suggested Format |
|--------|-------------|-------------------|------------------|
| market_commentary | Price charts, market visuals | charts/, layouts/market_update | Image or short video |
| education | Explainer graphics, diagrams | layouts/education, typography/ | Image (video for complex topics) |
| product | Feature highlights, UI snippets | layouts/announcement, logo/ | Image |
| social_proof | Metrics, testimonials | typography/, charts/ | Image |

---

## Implementation Steps

### Step 1: Set Up Vertex AI Client

New file: `src/services/vertex_ai.py`

```python
"""Google Vertex AI client for media generation."""

import base64
from pathlib import Path
from typing import Optional, List, Dict, Any

from google.cloud import aiplatform
from google.protobuf import struct_pb2

from src.config import get_settings


class VertexAIMediaClient:
    """Client for Imagen 3 and Veo 3 APIs."""

    def __init__(self):
        settings = get_settings()
        self.project_id = settings.gcp_project_id
        self.location = settings.gcp_location  # e.g., "us-central1"

        aiplatform.init(
            project=self.project_id,
            location=self.location,
        )

    def _load_reference_image(self, path: Path) -> str:
        """Load and base64 encode a reference image."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def generate_image(
        self,
        prompt: str,
        reference_images: List[Path] = None,
        style_description: str = None,
        aspect_ratio: str = "1:1",  # 1:1, 16:9, 9:16
        num_images: int = 1,
    ) -> List[bytes]:
        """Generate images using Imagen 3."""
        # Implementation details...
        pass

    async def generate_video(
        self,
        prompt: str,
        reference_images: List[Path] = None,
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9",  # 16:9, 9:16, 1:1
        with_audio: bool = False,
    ) -> bytes:
        """Generate video using Veo 3.1."""
        # Implementation details...
        pass
```

### Step 2: Create Media Prompt Generator

New file: `src/agent/media_prompts.py`

```python
"""Generate prompts for media creation based on content."""

from typing import Optional, List, Tuple
from pathlib import Path

from src.models.content import ContentPillar


# Map pillars to visual styles and reference images
PILLAR_VISUAL_CONFIG = {
    ContentPillar.MARKET_COMMENTARY: {
        "style": "Clean financial data visualization, dark theme with accent colors",
        "references": ["charts/", "layouts/market_update.png"],
        "default_format": "image",
        "aspect_ratio": "16:9",
    },
    ContentPillar.EDUCATION: {
        "style": "Clear explanatory graphics, minimal design, easy to read",
        "references": ["layouts/education.png", "typography/"],
        "default_format": "image",
        "aspect_ratio": "1:1",
    },
    ContentPillar.PRODUCT: {
        "style": "Modern product showcase, clean UI elements, brand colors",
        "references": ["layouts/announcement.png", "logo/"],
        "default_format": "image",
        "aspect_ratio": "1:1",
    },
    ContentPillar.SOCIAL_PROOF: {
        "style": "Testimonial/metrics highlight, professional, trustworthy",
        "references": ["typography/", "charts/"],
        "default_format": "image",
        "aspect_ratio": "1:1",
    },
}


def get_media_prompt(
    pillar: ContentPillar,
    topic: str,
    content: str,
    market_data: Optional[dict] = None,
) -> Tuple[str, List[Path], str]:
    """
    Generate a media prompt based on content.

    Returns:
        Tuple of (prompt, reference_image_paths, format)
    """
    config = PILLAR_VISUAL_CONFIG[pillar]

    # Build the visual prompt
    prompt_parts = [
        f"Create a {config['style']} visual for social media.",
        f"Topic: {topic}",
        f"Style: Professional fintech brand, Marks Exchange",
    ]

    # Add market data context if available
    if market_data:
        prompt_parts.append(f"Include data: {market_data}")

    # Add content-specific elements
    if pillar == ContentPillar.MARKET_COMMENTARY:
        prompt_parts.append("Show price movement or market trend visualization")
    elif pillar == ContentPillar.EDUCATION:
        prompt_parts.append("Create a clear diagram or infographic explaining the concept")
    elif pillar == ContentPillar.PRODUCT:
        prompt_parts.append("Highlight the feature or announcement with clean design")
    elif pillar == ContentPillar.SOCIAL_PROOF:
        prompt_parts.append("Display metrics or achievement in an engaging way")

    prompt = " ".join(prompt_parts)

    # Get reference image paths
    brand_dir = Path(__file__).parent.parent.parent / "context" / "brand" / "references"
    reference_paths = []
    for ref in config["references"]:
        ref_path = brand_dir / ref
        if ref_path.is_dir():
            # Get first image from directory
            for img in ref_path.glob("*.png"):
                reference_paths.append(img)
                break
        elif ref_path.exists():
            reference_paths.append(ref_path)

    return prompt, reference_paths[:3], config["default_format"]
```

### Step 3: Create Media Generation Service

New file: `src/services/media_service.py`

```python
"""Service for generating media for content."""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from uuid import uuid4

from src.models.content import ContentPillar
from src.services.vertex_ai import VertexAIMediaClient
from src.agent.media_prompts import get_media_prompt


class MediaService:
    """Service for generating images and videos for content."""

    def __init__(self):
        self.client = VertexAIMediaClient()
        self.output_dir = Path(__file__).parent.parent.parent / "media_output"
        self.output_dir.mkdir(exist_ok=True)

    async def generate_for_content(
        self,
        pillar: ContentPillar,
        topic: str,
        content: str,
        market_data: Optional[dict] = None,
        force_format: Optional[str] = None,  # "image" or "video"
    ) -> Dict[str, Any]:
        """
        Generate media for a piece of content.

        Returns:
            Dict with media_type, file_path, prompt_used
        """
        # Generate the prompt and get references
        prompt, reference_paths, default_format = get_media_prompt(
            pillar=pillar,
            topic=topic,
            content=content,
            market_data=market_data,
        )

        media_format = force_format or default_format

        # Generate media
        if media_format == "video":
            media_bytes = await self.client.generate_video(
                prompt=prompt,
                reference_images=reference_paths,
                duration_seconds=8,
            )
            extension = "mp4"
        else:
            media_list = await self.client.generate_image(
                prompt=prompt,
                reference_images=reference_paths,
                num_images=1,
            )
            media_bytes = media_list[0]
            extension = "png"

        # Save to file
        file_name = f"{uuid4().hex[:8]}_{pillar.value}.{extension}"
        file_path = self.output_dir / file_name
        with open(file_path, "wb") as f:
            f.write(media_bytes)

        return {
            "media_type": media_format,
            "file_path": str(file_path),
            "prompt_used": prompt,
            "reference_images": [str(p) for p in reference_paths],
        }

    async def regenerate_with_feedback(
        self,
        original_prompt: str,
        feedback: str,
        reference_paths: list,
        media_format: str,
    ) -> Dict[str, Any]:
        """Regenerate media with user feedback incorporated."""
        # Modify prompt based on feedback
        new_prompt = f"{original_prompt} Additional guidance: {feedback}"

        # Generate again
        # ... similar to above
        pass
```

### Step 4: Update Content Generator

Modify `src/agent/generator.py` to optionally generate media:

```python
async def generate_single_post(
    self,
    pillar: ContentPillar,
    topic_hint: Optional[str] = None,
    voice_feedback: str = "",
    generate_media: bool = False,  # NEW
    media_format: Optional[str] = None,  # NEW: "image", "video", or None for auto
) -> Dict[str, Any]:
    """Generate a single post with optional media."""

    # ... existing text generation code ...

    result = {
        "topic": parsed["topic"],
        "angle": parsed.get("angle", ""),
        "content": parsed["content"],
    }

    # Generate media if requested
    if generate_media:
        media_result = await self.media_service.generate_for_content(
            pillar=pillar,
            topic=result["topic"],
            content=result["content"],
            force_format=media_format,
        )
        result["media"] = media_result

    return result
```

### Step 5: Update Slack Bot

Modify `src/integrations/slack_bot.py` to handle media:

```python
@self.app.message(re.compile(r"^!generate\s+(\w+)(?:\s+(.+))?", re.IGNORECASE))
def handle_generate(message, say, context):
    """Handle !generate pillar [topic] [--image|--video]"""
    matches = context["matches"]
    pillar = matches[0].lower()
    rest = matches[1] if len(matches) > 1 and matches[1] else ""

    # Parse flags
    generate_media = "--image" in rest or "--video" in rest
    media_format = "video" if "--video" in rest else "image" if "--image" in rest else None
    topic = rest.replace("--image", "").replace("--video", "").strip() or None

    asyncio.run(self._generate_post(say, pillar, topic, generate_media, media_format))


async def _generate_post(self, say, pillar: str, topic: str = None,
                         generate_media: bool = False, media_format: str = None):
    """Generate a post with optional media."""
    try:
        # ... validation ...

        msg = f"✨ Generating {pillar.replace('_', ' ')} post"
        if generate_media:
            msg += f" with {media_format or 'image'}..."
        say(msg)

        result = await self.generator.generate_single_post(
            pillar=content_pillar,
            topic_hint=topic,
            generate_media=generate_media,
            media_format=media_format,
        )

        # Build response blocks
        blocks = [
            # ... existing text blocks ...
        ]

        # Post text first
        response = say(blocks=blocks, text=f"Generated post: {result.get('topic', '')}")

        # Upload media if generated
        if result.get("media"):
            media = result["media"]
            self.app.client.files_upload_v2(
                channel=message["channel"],
                thread_ts=response["ts"],
                file=media["file_path"],
                title=f"{pillar} - {result['topic']}",
                initial_comment=f"Media prompt: _{media['prompt_used']}_",
            )

        # Track for feedback/iteration
        # ...

    except Exception as e:
        say(f"❌ Error: {str(e)}")
```

### Step 6: Add Configuration

Update `src/config.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Google Cloud / Vertex AI
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    google_application_credentials: Optional[str] = None  # Path to service account JSON

    # Media generation settings
    media_generation_enabled: bool = False
    default_image_aspect_ratio: str = "1:1"
    default_video_duration: int = 8
    veo_tier: str = "standard"  # "fast", "standard", "full"
```

---

## Slack Commands

### Updated Command Syntax

```
!generate market_commentary                    # Text only (existing)
!generate market_commentary --image            # Text + image
!generate market_commentary --video            # Text + 8-sec video
!generate education funding rates --image     # With topic + image
```

### Media Iteration in Threads

```
User: !generate market_commentary --image

Bot: 📝 Generated Market Commentary Post
     Topic: Naira Weekly Recap
     [text content]

     🖼️ Generated Image:
     [image attachment]
     Prompt: "Clean financial data visualization..."

     💬 Reply to refine text or media. React ✅ when done.

User (thread): regenerate the image with more emphasis on the chart

Bot (thread): 🖼️ Regenerated Image:
     [new image attachment]
     Updated prompt: "...more emphasis on the chart..."

User (thread): perfect
User: reacts ✅

Bot (thread): ✅ Locked! Text + image ready.
```

---

## File Changes Summary

| File | Changes |
|------|---------|
| `src/config.py` | Add GCP settings, media generation config |
| `src/services/vertex_ai.py` | **NEW** - Vertex AI client for Imagen/Veo |
| `src/services/media_service.py` | **NEW** - Media generation orchestration |
| `src/agent/media_prompts.py` | **NEW** - Prompt generation for visuals |
| `src/agent/generator.py` | Add `generate_media` option |
| `src/integrations/slack_bot.py` | Add `--image`/`--video` flags, media upload |
| `context/brand/` | **NEW** - Brand reference images from Figma |
| `requirements.txt` | Add `google-cloud-aiplatform` |

---

## Setup Requirements

### 1. Google Cloud Setup

```bash
# Install gcloud CLI and authenticate
gcloud auth application-default login

# Enable APIs
gcloud services enable aiplatform.googleapis.com

# Create service account (for Railway deployment)
gcloud iam service-accounts create content-agent-media \
    --display-name="Content Agent Media Generation"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:content-agent-media@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# Download key for Railway
gcloud iam service-accounts keys create ./gcp-key.json \
    --iam-account=content-agent-media@$PROJECT_ID.iam.gserviceaccount.com
```

### 2. Environment Variables

```bash
# Add to Railway
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-key.json  # Or use secret mounting
MEDIA_GENERATION_ENABLED=true
```

### 3. Brand Reference Images

Export from Figma:
1. Select key frames representing brand style
2. Export as PNG at 2x resolution
3. Organize into `context/brand/references/` structure
4. Include: charts, typography, layouts, logo, color examples

---

## Cost Estimates

### Per Post

| Content Type | Media | Cost |
|--------------|-------|------|
| Text only | None | $0.00 (text gen ~$0.01) |
| Text + Image | 1 image | ~$0.04-0.15 |
| Text + Video (8s) | 1 video | ~$3.20-6.00 |

### Weekly (7 posts)

| Scenario | Cost |
|----------|------|
| All text only | ~$0.07 |
| All with images | ~$0.35-1.05 |
| Mix (5 images, 2 videos) | ~$7-13 |
| All with videos | ~$22-42 |

### Monthly Budget Recommendations

| Budget Tier | Strategy |
|-------------|----------|
| Low ($10/mo) | Images only, selective use |
| Medium ($50/mo) | Images for all, videos for key announcements |
| High ($150/mo) | Videos for market commentary, images for rest |

---

## Future Enhancements

1. **Auto-select format** - Claude analyzes content and recommends image vs video
2. **Template compositing** - Overlay generated visuals on Figma templates
3. **A/B media options** - Generate 2-3 variations to choose from
4. **Scheduled generation** - Pre-generate weekly batch media
5. **Twitter auto-post** - Post approved content directly with media
6. **Analytics feedback** - Track which visuals perform best, feed back into prompts

---

## Example: Full Flow

```
User: !generate market_commentary --image

Bot: ✨ Generating market commentary post with image...

Bot: 📝 Generated Market Commentary Post
     ─────────────────────
     Topic: Naira Holds Steady Amid CBN Intervention

     Naira traded flat this week at ₦1,580/USD as CBN
     intervention absorbed dollar demand.

     Key levels:
     • Support: ₦1,550
     • Resistance: ₦1,620

     Watch for Thursday's MPC decision.
     ─────────────────────

     🖼️ [Attached: market_commentary_a1b2c3d4.png]

     Media prompt: "Clean financial data visualization, dark theme
     with accent colors. Topic: Naira weekly price action.
     Professional fintech brand, Marks Exchange. Show price
     movement with support/resistance levels highlighted."

     💬 Reply in thread to refine, react ✅ when done

User (thread): the chart should show a flat line, not upward trend

Bot (thread): 🖼️ Regenerating with feedback...

Bot (thread): 🖼️ Revised Image
     [new image with flat trend line]

User: reacts ✅

Bot (thread): ✅ Final version locked!

     Ready to post:
     • Text: 247 characters
     • Media: 1 image (1080x1080)
```
