import os
import requests
import time
from backend.config import SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL, SILICONFLOW_IMAGE_MODEL

def generate_cover_image(prompt: str, output_path: str) -> str:
    """
    Generate a cover image using SiliconFlow's Kolors model.
    Returns the local path to the saved image.
    """
    if not SILICONFLOW_API_KEY:
        print("Warning: SILICONFLOW_API_KEY not set. Skipping cover generation.")
        return ""

    url = f"{SILICONFLOW_BASE_URL}/images/generations"
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": SILICONFLOW_IMAGE_MODEL,
        "prompt": prompt,
        "negative_prompt": "nsfw, low quality, blurry, distorted, text, watermark",
        "image_size": "1024x1024", # Kolors usually supports this
        "batch_size": 1
    }

    try:
        print(f"Generating cover image with SiliconFlow ({SILICONFLOW_IMAGE_MODEL})...")
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        # SiliconFlow returns image URL in data['images'][0]['url'] or data['data'][0]['url']
        # Based on their docs, it's often images[0].url or data[0].url
        image_url = ""
        if "images" in data and len(data["images"]) > 0:
            image_url = data["images"][0].get("url", "")
        elif "data" in data and len(data["data"]) > 0:
            image_url = data["data"][0].get("url", "")

        if not image_url:
            print(f"Failed to find image URL in response: {data}")
            return ""

        # Download image
        img_data = requests.get(image_url).content
        with open(output_path, "wb") as f:
            f.write(img_data)
        
        print(f"Cover image saved to {output_path}")
        return output_path
    except Exception as e:
        print(f"Error generating cover image: {e}")
        return ""

def generate_cover_prompt(user_prompt: str, scene_brief: str, asset_brief: str) -> str:
    """
    Use the selected LLM to turn the user's original idea (plus scene/asset briefs) into a
    high-quality Kolors image prompt. The user's prompt is the ground truth — the cover MUST
    depict the main subject and action from it, not tangential side characters.
    """
    from backend.services.llm import _get_client_config, get_model

    fallback = f"Cinematic movie still of: {user_prompt}. Wide establishing shot, dramatic lighting, photorealistic."

    selection = get_model()
    # For cover prompts, if it's R1, we still fallback to V3 for speed/predictability
    if selection == "deepseek-reasoner":
        selection = "deepseek-chat"

    client, model = _get_client_config(selection)
    if not client:
        return fallback

    system = (
        "You are a cinematic concept artist writing a single English prompt for the Kolors "
        "image model. The user's original idea is GROUND TRUTH: the cover MUST literally "
        "depict its main subject and action (e.g. the vehicle, creature, or event named in "
        "the idea), shot as a wide establishing / hero frame. Do NOT make the cover a "
        "close-up portrait of an operator, pilot, driver, or any incidental human unless the "
        "user explicitly asked for a person. Use the scene and asset briefs only to enrich "
        "environment, lighting, texture, and mood. Output one concise vivid prompt, no lists, "
        "no commentary."
    )
    user = (
        f"USER ORIGINAL IDEA (ground truth, must be depicted): {user_prompt}\n"
        f"Scene brief (environment/mood only): {scene_brief}\n"
        f"Assets/actors (supporting detail only, do not let a human take over the frame): {asset_brief}\n"
        "Write the Kolors prompt now."
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            max_tokens=200
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating image prompt: {e}")
        return fallback


