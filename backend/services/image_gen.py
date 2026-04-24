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

def generate_cover_prompt(scene_brief: str, asset_brief: str) -> str:
    """
    Use the selected LLM to turn scene/asset descriptions into a high-quality image prompt.
    """
    from backend.services.llm import _get_client_config, get_model
    
    selection = get_model()
    # For cover prompts, if it's R1, we still fallback to V3 for speed/predictability
    if selection == "deepseek-reasoner":
        selection = "deepseek-chat"
        
    client, model = _get_client_config(selection)
    if not client:
        return f"Cinematic movie still, {scene_brief[:100]}"

    system = (
        "You are a cinematic concept artist. Your task is to create a highly detailed, "
        "professional AI image generation prompt for a movie cover. "
        "The prompt should be in English, focused on lighting, texture, and atmosphere. "
        "Keep it concise but vivid. Focus on a single, striking composition."
    )
    user = f"Scene Brief: {scene_brief}\nActors/Assets: {asset_brief}\nGenerate a Kolors image prompt."
    
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            max_tokens=150
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating image prompt: {e}")
        return f"Cinematic movie still, {scene_brief[:100]}"


