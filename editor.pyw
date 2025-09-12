"""
editor.pyw
Map editor for "The special" with Dirt background placement
"""

import pygame
import sys
import json
from pathlib import Path

# Config
SCREEN_W, SCREEN_H = 800, 600
TILE = 48
PLAYER_SPEED = 300  # faster for editor
ASSETS = {
    "player": "player.png",
    "tile": "Grass.png",
    "dirt": "Dirt.png",
    "girlfriend": "Girlfriend.png",
    "john": "John.png",
    "mom": "Mom.png",
    "tree": "Tree.png",
    "tree2": "Tree2.png",
    "treadmill": "Treadmill.png",  # treadmill added
    # goffy dog asset (optional)
    "goffyDog": "goffyDog.png",
}

def load_image(name, colorkey=None):
    path = Path(name)
    if not path.exists():
        raise FileNotFoundError(f"Missing asset: {name}")
    img = pygame.image.load(str(path)).convert_alpha()
    if colorkey is not None:
        img.set_colorkey(colorkey)
    return img

def scale_to_tile(img, tile_w=TILE, tile_h=TILE, keep_aspect=True):
    w, h = img.get_size()
    if keep_aspect:
        scale = min(tile_w / w, tile_h / h) if w and h else 1.0
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
    else:
        nw, nh = int(tile_w), int(tile_h)
    return pygame.transform.scale(img, (nw, nh))

class Camera:
    def __init__(self, screen_w, screen_h):
        self.screen_w, self.screen_h = screen_w, screen_h
        self.offset = pygame.Vector2(0, 0)
    def update(self, target_rect):
        self.offset.x = target_rect.centerx - self.screen_w // 2
        self.offset.y = target_rect.centery - self.screen_h // 2

class WorldObject(pygame.sprite.Sprite):
    def __init__(self, image, tile_w=1, tile_h=1, pos=(0,0), name="", solid=True):
        super().__init__()
        self.raw_image = image
        self.image = scale_to_tile(self.raw_image, int(tile_w*TILE), int(tile_h*TILE))
        self.rect = self.image.get_rect(topleft=pos)
        self.name = name
        self.solid = solid

class Player(pygame.sprite.Sprite):
    def __init__(self, image, pos, scale=1):
        super().__init__()
        self.raw_image = image
        self.image = scale_to_tile(self.raw_image, int(TILE*scale), int(TILE*scale))
        self.rect = self.image.get_rect(center=pos)
        self.pos = pygame.Vector2(self.rect.topleft)
        self.vel = pygame.Vector2(0,0)

    def update(self, dt, obstacles):
        keys = pygame.key.get_pressed()
        dir = pygame.Vector2(0,0)
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dir.y = -1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dir.y = 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dir.x = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dir.x = 1
        if dir.length_squared() > 0:
            dir = dir.normalize()
        self.vel = dir * PLAYER_SPEED
        self.pos += self.vel * dt
        self.rect.topleft = (int(self.pos.x), int(self.pos.y))

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("The special - Map Editor")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24, bold=True)

    # Load images robustly (don't crash if optional asset missing)
    imgs = {}
    for k, v in ASSETS.items():
        p = Path(v)
        if p.exists():
            try:
                imgs[k] = load_image(v)
            except Exception as e:
                print(f"Failed to load {v}: {e}")
        else:
            print(f"Warning: asset '{v}' not found — '{k}' will be unavailable in editor.")

    maps_path = Path("Maps.json")
    mapdata = None
    if maps_path.exists():
        with maps_path.open("r", encoding="utf-8") as f:
            mapdata = json.load(f)

    WORLD_TILES_X = mapdata["world"].get("tiles_x", 40) if mapdata else 40
    WORLD_TILES_Y = mapdata["world"].get("tiles_y", 30) if mapdata else 30

    # Ensure tile image exists
    if "tile" not in imgs:
        raise FileNotFoundError("Required asset 'Grass.png' (tile) missing.")
    tile_img = scale_to_tile(imgs["tile"], TILE, TILE)
    objects = pygame.sprite.Group()
    map_objects = []
    background_tiles = pygame.sprite.Group()

    def add_dirt(grid_x, grid_y):
        pos = (grid_x*TILE, grid_y*TILE)
        if "dirt" not in imgs:
            print("Cannot place dirt: 'Dirt.png' missing.")
            return
        obj = WorldObject(imgs["dirt"], tile_w=1, tile_h=1, pos=pos, name="dirt", solid=False)
        background_tiles.add(obj)
        map_objects.append({"type": "dirt", "x": grid_x, "y": grid_y})

    def add_obj(key, grid_x, grid_y, tile_w=1, tile_h=1):
        pos = (grid_x*TILE, grid_y*TILE)
        if key not in imgs:
            print(f"Cannot place '{key}': asset missing.")
            return None
        obj = WorldObject(imgs[key], tile_w, tile_h, pos, name=key)
        objects.add(obj)
        map_objects.append({"type": key, "x": grid_x, "y": grid_y})
        return obj

    # Load objects from map (if present)
    if mapdata and "objects" in mapdata:
        for o in mapdata["objects"]:
            typ = o.get("type")
            x, y = o.get("x",0), o.get("y",0)
            if typ is None:
                continue
            t = typ.lower()
            if t == "tree2":
                add_obj("tree2", x, y, tile_w=6, tile_h=8)
            elif t == "tree":
                add_obj("tree", x, y, tile_w=2, tile_h=2)
            elif t == "treadmill":
                add_obj("treadmill", x, y, tile_w=6, tile_h=8)
            elif t == "dirt":
                add_dirt(x, y)
            elif t == "goffydog" or t == "goffyDog".lower():
                add_obj("goffyDog", x, y, tile_w=2, tile_h=2)
            else:
                # generic object (girlfriend, john, mom, etc.)
                add_obj(typ, x, y)

    # Player
    if mapdata and "player" in mapdata:
        p = mapdata["player"]
        player_start = (p["x"]*TILE, p["y"]*TILE)
    else:
        player_start = (TILE*5, TILE*5)

    if "player" not in imgs:
        raise FileNotFoundError("Required asset 'player.png' missing.")
    player = Player(imgs["player"], player_start, scale=2)

    camera = Camera(SCREEN_W, SCREEN_H)

    # Scrollable object selection. Note: keys must match ASSETS keys (case-sensitive).
    place_keys = ["girlfriend", "john", "mom", "tree", "tree2", "treadmill", "goffyDog", "dirt", "delete"]
    current_index = 0

    running = True
    while running:
        dt = clock.tick(60)/1000
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                gx, gy = int((mx + camera.offset.x)//TILE), int((my + camera.offset.y)//TILE)
                current_obj = place_keys[current_index]
                if ev.button == 1:  # left click
                    if current_obj == "delete":
                        # delete the top object at click world position (if any)
                        wx, wy = mx + camera.offset.x, my + camera.offset.y
                        for obj in list(objects):
                            if obj.rect.collidepoint(wx, wy):
                                # remove from sprite group and map_objects list
                                objects.remove(obj)
                                map_objects = [o for o in map_objects if not (o["x"]==obj.rect.x//TILE and o["y"]==obj.rect.y//TILE)]
                                break
                    elif current_obj == "dirt":
                        add_dirt(gx, gy)
                    elif current_obj == "treadmill":
                        add_obj("treadmill", gx, gy, tile_w=6, tile_h=8)
                    elif current_obj == "tree2":
                        add_obj("tree2", gx, gy, tile_w=6, tile_h=8)
                    elif current_obj == "tree":
                        add_obj("tree", gx, gy, tile_w=2, tile_h=2)
                    elif current_obj == "goffyDog":
                        add_obj("goffyDog", gx, gy, tile_w=2, tile_h=2)
                    else:
                        add_obj(current_obj, gx, gy)
                elif ev.button == 4:  # scroll up
                    current_index = (current_index +1)%len(place_keys)
                elif ev.button == 5:  # scroll down
                    current_index = (current_index -1)%len(place_keys)

        # Player movement
        player.update(dt, [])

        # Camera follows player
        camera.update(player.rect)

        # Draw
        screen.fill((0,0,0))

        # Draw dirt background first
        for obj in background_tiles:
            screen.blit(obj.image, (obj.rect.x - camera.offset.x, obj.rect.y - camera.offset.y))

        # Draw grass tiles on top
        for ty in range(int(camera.offset.y//TILE), int(camera.offset.y//TILE)+SCREEN_H//TILE+2):
            for tx in range(int(camera.offset.x//TILE), int(camera.offset.x//TILE)+SCREEN_W//TILE+2):
                has_dirt = any(obj.rect.x//TILE == tx and obj.rect.y//TILE == ty for obj in background_tiles)
                if not has_dirt:
                    screen.blit(tile_img, (tx*TILE - camera.offset.x, ty*TILE - camera.offset.y))

        # Draw placed objects (sorted by bottom)
        for obj in sorted(objects, key=lambda o:o.rect.bottom):
            screen.blit(obj.image, (obj.rect.x - camera.offset.x, obj.rect.y - camera.offset.y))

        # Draw player
        screen.blit(player.image, (player.rect.x - camera.offset.x, player.rect.y - camera.offset.y))

        # Show selected object
        selected_name = place_keys[current_index]
        # nicer display: show case-correct and friendly label
        label = selected_name
        txt = font.render(f"Selected: {label}", True, (255,255,255))
        screen.blit(txt, (10, 10))

        pygame.display.flip()

    # Save map on exit
    out_map = {
        "world": {"tiles_x": WORLD_TILES_X, "tiles_y": WORLD_TILES_Y},
        "objects": map_objects,
        "player": {"x": player.rect.x//TILE, "y": player.rect.y//TILE}
    }
    with maps_path.open("w", encoding="utf-8") as f:
        json.dump(out_map, f, indent=2)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
