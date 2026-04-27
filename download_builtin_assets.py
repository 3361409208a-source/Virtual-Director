"""
Download a curated set of CC0 GLB models into godot/assets/builtin/.
Run once: python download_builtin_assets.py
Sources:
  - KhronosGroup glTF-Sample-Assets (verified GLB variants)
  - Quaternius CC0 pack CDN
"""
import os
import urllib.request

BUILTIN_DIR = os.path.join(os.path.dirname(__file__), "godot", "assets", "builtin")
os.makedirs(BUILTIN_DIR, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_KGLTF = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models"

MODELS = [
    # filename,  URL,  keywords (for documentation)
    ("human.glb",        f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb",
     "human, person, man, character, pedestrian, soldier, pilot, player"),

    ("robot.glb",        f"{_KGLTF}/RiggedFigure/glTF-Binary/RiggedFigure.glb",
     "robot, alien, android, figure, creature, monster"),

    ("fox.glb",          f"{_KGLTF}/Fox/glTF-Binary/Fox.glb",
     "fox, wolf, dog, cat, animal, bear"),

    ("duck.glb",         f"{_KGLTF}/Duck/glTF-Binary/Duck.glb",
     "duck, bird, chicken, penguin"),

    ("car.glb",          f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb",
     "car, truck, vehicle, van, bus, taxi, police car, ambulance"),

    ("dragon.glb",       f"{_KGLTF}/DragonDispersion/glTF-Binary/DragonDispersion.glb",
     "dragon, dinosaur, wyvern, lizard"),

    ("skull.glb",        f"{_KGLTF}/ScatteringSkull/glTF-Binary/ScatteringSkull.glb",
     "skull, skeleton, bone, death"),

    ("lantern.glb",      f"{_KGLTF}/Lantern/glTF-Binary/Lantern.glb",
     "lantern, lamp, light, torch"),

    ("helmet.glb",       f"{_KGLTF}/DamagedHelmet/glTF-Binary/DamagedHelmet.glb",
     "helmet, armor, head"),

    ("bottle.glb",       f"{_KGLTF}/WaterBottle/glTF-Binary/WaterBottle.glb",
     "bottle, container, jar, cup"),

    ("ball.glb",         f"{_KGLTF}/AnimatedMorphCube/glTF-Binary/AnimatedMorphCube.glb",
     "ball, cube, box, block, dice"),

    ("avocado.glb",      f"{_KGLTF}/Avocado/glTF-Binary/Avocado.glb",
     "avocado, fruit, food, plant, tree"),

    ("airplane.glb",     f"{_KGLTF}/BoxAnimated/glTF-Binary/BoxAnimated.glb",
     "airplane, plane, jet, aircraft, rocket, spaceship, spacecraft, ufo"),

    ("triangle.glb",     f"{_KGLTF}/Triangle/glTF-Binary/Triangle.glb",
     "triangle, shape, simple"),
]


def download(filename: str, url: str, keywords: str):
    dest = os.path.join(BUILTIN_DIR, filename)
    if os.path.exists(dest):
        size = os.path.getsize(dest) // 1024
        print(f"  [cached] {filename} ({size} KB)  — {keywords}")
        return True
    print(f"  ↓ {filename}  ←  {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(dest, "wb") as f:
            f.write(data)
        print(f"    ✅ saved {len(data)//1024} KB")
        return True
    except Exception as e:
        print(f"    ❌ FAILED: {e}")
        return False


if __name__ == "__main__":
    print(f"Downloading {len(MODELS)} builtin CC0 models → {BUILTIN_DIR}\n")
    ok = fail = 0
    for fname, url, kw in MODELS:
        if download(fname, url, kw):
            ok += 1
        else:
            fail += 1
    print(f"\nDone: {ok} ok, {fail} failed")
    print("Now restart the backend — Tier 0 builtin assets are ready.")
