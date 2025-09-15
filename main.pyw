import pygame
import sys
import json
import random
import math
from pathlib import Path
import array
import io
import wave
import time

# Turn off debug printing/drawing
DEBUG = False

SCREEN_W, SCREEN_H = 800, 600
TILE = 48
PLAYER_SPEED = 180
JOHN_SPEED = PLAYER_SPEED * 0.8
GIRLFRIEND_SPEED = PLAYER_SPEED * 0.8
JOHN_STOP_DISTANCE = 100
GIRLFRIEND_STOP_DISTANCE = 100
ASSETS = {
    "intro1": "find.png",
    "intro2": "begining.png",
    "music": "TheTreadmill.mp3",
    "realisation": "realisation.mp3",
    "player": "Player.png",
    "player1": "Player1.png",
    "tile": "Grass.png",
    "dirt": "Dirt.png",
    "girlfriend": "Girlfriend.png",
    "girlfriend1": "Girlfriend1.png",  # optional - new
    "john": "John.png",
    "john1": "John1.png",              # optional - new
    "mom": "Mom.png",
    "tree": "Tree.png",
    "tree2": "Tree2.png",
    "treadmill": "Treadmill.png",
    "message": "message.png",
    "message2": "message2.png",
    "message3": "message3.png",
    "message4": "Message4.png",
    "end": "end.png",
    "wolf1": "Wolf1.png",
    "wolf2": "Wolf2.png",
    "heart": "TheSpetial.png",
    "goofyDog": "goffyDog.png",
    "unknown": "unknown.png",   # lowercase key
    "checkpoint": "checkpoint.png",  # new asset (optional — placeholder drawn if missing)
}

CHECKPOINT_FILE = Path("checkpoint.txt")


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


def get_collision_rect(obj):
    return getattr(obj, "block_rect", obj.rect)


def get_interaction_rect(obj):
    return getattr(obj, "interaction_rect", obj.rect)


class Camera:
    def __init__(self, screen_w, screen_h):
        self.screen_w, self.screen_h = screen_w, screen_h
        self.offset = pygame.Vector2(0, 0)

    def update(self, target_rect):
        self.offset.x = target_rect.centerx - self.screen_w // 2
        self.offset.y = target_rect.centery - self.screen_h // 2


class WorldObject(pygame.sprite.Sprite):
    def __init__(self, image, tile_w=1, tile_h=1, pos=(0, 0), name="", solid=True):
        super().__init__()
        self.raw_image = image
        if self.raw_image is None:
            surf = pygame.Surface((int(tile_w * TILE), int(tile_h * TILE)), pygame.SRCALPHA)
            surf.fill((255, 0, 255, 180))
            pygame.draw.line(surf, (0, 0, 0), (0, 0), (surf.get_width(), surf.get_height()), 2)
            pygame.draw.line(surf, (0, 0, 0), (surf.get_width(), 0), (0, surf.get_height()), 2)
            self.raw_image = surf
        # scale once at creation
        self.image = scale_to_tile(self.raw_image, int(tile_w * TILE), int(tile_h * TILE), keep_aspect=True)
        self.rect = self.image.get_rect(topleft=pos)
        self.name = name
        self.solid = solid


class NPC(pygame.sprite.Sprite):
    def __init__(self, image_down, image_up, tile_w=1, tile_h=1, pos=(0, 0), name="", solid=True, up_sector_deg=90):
        super().__init__()
        if image_down is None:
            image_down = pygame.Surface((int(tile_w * TILE), int(tile_h * TILE)), pygame.SRCALPHA)
            image_down.fill((200, 80, 200, 180))
        if image_up is None:
            image_up = image_down
        self.raw_image_down = image_down
        self.raw_image_up = image_up
        self.pixel_w = int(tile_w * TILE)
        self.pixel_h = int(tile_h * TILE)
        # store scaled images once
        self.img_down_scaled = scale_to_tile(self.raw_image_down, self.pixel_w, self.pixel_h, keep_aspect=True)
        self.img_up_scaled = scale_to_tile(self.raw_image_up, self.pixel_w, self.pixel_h, keep_aspect=True)
        self.image = self.img_down_scaled
        self.rect = self.image.get_rect(topleft=pos)
        self.name = name
        self.solid = solid
        self.last_x_dir = 1
        self.facing_up = False
        self.up_sector_deg = up_sector_deg
        self.up_half_angle = up_sector_deg / 2.0
        self.bump_timer = 0.0
        self.bump_amplitude = 2
        self.bump_step_interval = 0.3
        self.bump_state = 0
        self.visual_offset_y = 0.0

    def set_direction(self, dx, dy):
        if dx < 0:
            self.last_x_dir = -1
        elif dx > 0:
            self.last_x_dir = 1
        vx = float(dx)
        vy = float(dy)
        mag = math.hypot(vx, vy)
        if mag < 1e-6:
            return
        cos_theta = max(-1.0, min(1.0, (-vy) / mag))
        angle_deg = math.degrees(math.acos(cos_theta))
        self.facing_up = (angle_deg <= self.up_half_angle)
        self.image = self.img_up_scaled if self.facing_up else self.img_down_scaled

    def update_bump(self, dt, moving: bool):
        if moving:
            self.bump_timer += dt
            if self.bump_timer >= self.bump_step_interval:
                intervals = int(self.bump_timer // self.bump_step_interval)
                self.bump_timer -= intervals * self.bump_step_interval
                if intervals % 2 == 1:
                    self.bump_state ^= 1
            self.visual_offset_y = -self.bump_amplitude if self.bump_state else 0
        else:
            self.bump_timer = 0.0
            self.bump_state = 0
            self.visual_offset_y = 0


class Player(pygame.sprite.Sprite):
    def __init__(self, image, image_up, pos, scale=1):
        super().__init__()
        # keep raw originals
        self.raw_image_down = image
        self.raw_image_up = image_up
        # store scale so we can rescale later
        self.scale = scale
        # Pre-scale both facing images once (avoid scaling every frame)
        pixel_w = int(TILE * scale)
        pixel_h = int(TILE * scale)
        self.img_down_scaled = scale_to_tile(self.raw_image_down, pixel_w, pixel_h, keep_aspect=True)
        self.img_up_scaled = scale_to_tile(self.raw_image_up, pixel_w, pixel_h, keep_aspect=True)
        # default image
        self.image = self.img_down_scaled
        self.rect = self.image.get_rect(center=pos)
        self.pos = pygame.Vector2(self.rect.topleft)
        self.vel = pygame.Vector2(0, 0)
        self.last_y_dir = 1
        self.facing_up = False
        self.last_x_dir = 1
        self.bump_timer = 0.0
        self.bump_amplitude = 2
        self.bump_step_interval = 0.3
        self.bump_state = 0
        self.visual_offset_y = 0.0

    def set_textures(self, new_down_image, new_up_image=None):
        """Replace player's textures at runtime. new_up_image optional - falls back to new_down_image."""
        if new_down_image is None:
            return
        self.raw_image_down = new_down_image
        self.raw_image_up = new_up_image if (new_up_image is not None) else new_down_image
        pixel_w = int(TILE * self.scale)
        pixel_h = int(TILE * self.scale)
        # rescale new images
        self.img_down_scaled = scale_to_tile(self.raw_image_down, pixel_w, pixel_h, keep_aspect=True)
        self.img_up_scaled = scale_to_tile(self.raw_image_up, pixel_w, pixel_h, keep_aspect=True)
        # update current image according to facing
        self.image = self.img_up_scaled if self.facing_up else self.img_down_scaled

    def update(self, dt, nearby_obstacles):
        keys = pygame.key.get_pressed()
        dir = pygame.Vector2(0, 0)
        up_pressed = keys[pygame.K_w] or keys[pygame.K_UP]
        down_pressed = keys[pygame.K_s] or keys[pygame.K_DOWN]
        left_pressed = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right_pressed = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        if up_pressed:
            dir.y = -1
        if down_pressed:
            dir.y = 1
        if left_pressed:
            dir.x = -1
            self.last_x_dir = -1
        if right_pressed:
            dir.x = 1
            self.last_x_dir = 1
        if dir.length_squared() > 0:
            dir = dir.normalize()
        self.vel = dir * PLAYER_SPEED
        new_pos = self.pos + self.vel * dt
        if up_pressed:
            self.facing_up = True
        elif down_pressed or left_pressed or right_pressed:
            self.facing_up = False

        # move X and test collisions only against nearby obstacles (improves perf)
        self.rect.topleft = (new_pos.x, self.pos.y)
        collided = [o for o in nearby_obstacles if getattr(o, "solid", False) and self.rect.colliderect(get_collision_rect(o))]
        if collided:
            if self.vel.x > 0:
                self.rect.right = min(get_collision_rect(o).left for o in collided)
            elif self.vel.x < 0:
                self.rect.left = max(get_collision_rect(o).right for o in collided)
            new_pos.x = self.rect.x

        # move Y and test collisions
        self.rect.topleft = (new_pos.x, new_pos.y)
        collided = [o for o in nearby_obstacles if getattr(o, "solid", False) and self.rect.colliderect(get_collision_rect(o))]
        if collided:
            if self.vel.y > 0:
                self.rect.bottom = min(get_collision_rect(o).top for o in collided)
            elif self.vel.y < 0:
                self.rect.top = max(get_collision_rect(o).bottom for o in collided)
            new_pos.y = self.rect.y

        self.pos = pygame.Vector2(new_pos)
        self.rect.topleft = (int(self.pos.x), int(self.pos.y))

        # set pre-scaled image (no per-frame scaling)
        self.image = self.img_up_scaled if self.facing_up else self.img_down_scaled

        moving = self.vel.length_squared() > 0.5
        if moving:
            self.bump_timer += dt
            if self.bump_timer >= self.bump_step_interval:
                intervals = int(self.bump_timer // self.bump_step_interval)
                self.bump_timer -= intervals * self.bump_step_interval
                if intervals % 2 == 1:
                    self.bump_state ^= 1
            self.visual_offset_y = -self.bump_amplitude if self.bump_state else 0
        else:
            self.bump_timer = 0.0
            self.bump_state = 0
            self.visual_offset_y = 0


class Wolf(pygame.sprite.Sprite):
    def __init__(self, images, y, speed):
        super().__init__()
        self.images = [scale_to_tile(img, TILE * 2, TILE * 2) for img in images]
        self.image = self.images[0]
        self.rect = self.image.get_rect(midright=(0, y))
        self.anim_time = 0
        self.anim_index = 0
        self.speed = speed
        self.active = False

    def start(self, y, camera_offset_x):
        spawn_x = int(camera_offset_x + SCREEN_W + 100)
        self.rect.midright = (spawn_x, y)
        self.active = True
        self.anim_time = 0
        self.anim_index = 0

    def update(self, dt):
        if not self.active:
            return
        self.rect.x -= int(self.speed * dt)
        self.anim_time += dt
        if self.anim_time > 0.15:
            self.anim_index = (self.anim_index + 1) % 2
            self.image = self.images[self.anim_index]
            self.anim_time = 0
        if self.rect.right < -100:
            self.active = False


def render_wrapped_text(surface, text, font, color, rect, aa=True):
    x, y = rect.topleft
    max_w = rect.width
    words = text.split(' ')
    line = ""
    line_height = font.get_linesize()
    for w in words:
        test = line + ("" if line == "" else " ") + w
        tw, _ = font.size(test)
        if tw <= max_w:
            line = test
        else:
            if line != "":
                surface.blit(font.render(line, aa, color), (x, y))
                y += line_height
            line = w
    if line != "":
        surface.blit(font.render(line, aa, color), (x, y))


def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass

    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("The special beta 0.5")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 28, bold=True)
    try:
        goofy_font = pygame.font.SysFont("Comic Sans MS", 28, bold=True)
    except Exception:
        goofy_font = pygame.font.SysFont("comicsansms", 28, bold=True)
    if goofy_font is None:
        goofy_font = pygame.font.SysFont(None, 28)

    def make_beep(freq_hz, duration_s=0.07, volume=0.6, sr=44100):
        n = int(sr * duration_s)
        amplitude = int(32767 * max(0.0, min(1.0, volume)))
        samples = array.array('h')
        for i in range(n):
            v = int(amplitude * math.sin(2.0 * math.pi * freq_hz * (i / sr)))
            samples.append(v)
            samples.append(v)
        raw = samples.tobytes()
        b = io.BytesIO()
        wf = wave.open(b, 'wb')
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(raw)
        wf.close()
        b.seek(0)
        try:
            return pygame.mixer.Sound(b)
        except Exception:
            try:
                return pygame.mixer.Sound(buffer=raw)
            except Exception:
                empty = io.BytesIO()
                wf2 = wave.open(empty, 'wb')
                wf2.setnchannels(2)
                wf2.setsampwidth(2)
                wf2.setframerate(sr)
                wf2.writeframes(b'')
                wf2.close()
                empty.seek(0)
                return pygame.mixer.Sound(empty)

    message_beeps = [
        make_beep(520, duration_s=0.06, volume=0.7),
        make_beep(380, duration_s=0.06, volume=0.7),
        make_beep(260, duration_s=0.09, volume=0.7),
    ]
    message_beep_playing = False
    message_beep_timer = 0.0
    message_beep_index = 0
    MESSAGE_BEEP_INTERVAL = 0.12

    imgs = {}
    for key, fname in ASSETS.items():
        if key in ("music", "realisation"):
            continue
        p = Path(fname)
        if p.exists():
            try:
                imgs[key] = load_image(fname)
            except Exception:
                pass

    # fallback load for goofy dog if needed
    if "goofyDog" not in imgs:
        try:
            p = Path(ASSETS.get("goofyDog", ""))
            if p.exists():
                imgs["goofyDog"] = load_image(str(p))
        except Exception:
            pass

    # fallback load for unknown if needed
    if "unknown" not in imgs:
        try:
            p = Path(ASSETS.get("unknown", ""))
            if p.exists():
                imgs["unknown"] = load_image(str(p))
        except Exception:
            pass

    # checkpoint image optional
    if "checkpoint" not in imgs:
        try:
            p = Path(ASSETS.get("checkpoint", ""))
            if p.exists():
                imgs["checkpoint"] = load_image(str(p))
        except Exception:
            pass

    # Try to load optional "Cool" textures if present on disk (non-fatal)
    if "cool" not in imgs:
        for fname in ("Cool.png", "cool.png"):
            if Path(fname).exists():
                try:
                    imgs["cool"] = load_image(fname)
                    break
                except Exception:
                    pass
    if "cool1" not in imgs:
        for fname in ("Cool1.png", "cool1.png"):
            if Path(fname).exists():
                try:
                    imgs["cool1"] = load_image(fname)
                    break
                except Exception:
                    pass
    # Note: if only Cool.png exists, Cool1 will fallback to Cool (handled later).

    required = ["intro1", "intro2", "player", "player1", "tile", "dirt", "girlfriend", "john", "message", "message2", "message3", "message4", "end", "wolf1", "wolf2", "heart"]
    for r in required:
        if r not in imgs:
            raise FileNotFoundError(f"Required asset '{r}' not found: expected file '{ASSETS.get(r)}'")

    # --- Try to locate *up* textures for John and Girlfriend ---
    # Prefer keys "john1"/"girlfriend1" loaded into imgs (via ASSETS above).
    # Otherwise look for files named "John1.png"/"john1.png" etc and load them.
    john_up_img = None
    girlfriend_up_img = None

    # 1) check imgs dict keys
    if "john1" in imgs:
        john_up_img = imgs["john1"]
    if "girlfriend1" in imgs:
        girlfriend_up_img = imgs["girlfriend1"]

    # 2) try common filenames on disk if not found in imgs
    if john_up_img is None:
        for fname in ("John1.png", "john1.png"):
            if Path(fname).exists():
                try:
                    john_up_img = load_image(fname)
                    break
                except Exception:
                    pass
    if girlfriend_up_img is None:
        for fname in ("Girlfriend1.png", "girlfriend1.png"):
            if Path(fname).exists():
                try:
                    girlfriend_up_img = load_image(fname)
                    break
                except Exception:
                    pass

    # 3) fallback to main images
    if john_up_img is None:
        john_up_img = imgs.get("john")
    if girlfriend_up_img is None:
        girlfriend_up_img = imgs.get("girlfriend")

    heart_img = scale_to_tile(imgs["heart"], 32, 32, keep_aspect=True)
    intro1 = pygame.transform.scale(imgs["intro1"], (SCREEN_W, SCREEN_H))
    intro2 = pygame.transform.scale(imgs["intro2"], (SCREEN_W, SCREEN_H))

    def draw_image_full(img):
        screen.fill((0, 0, 0))
        screen.blit(img, (0, 0))
        pygame.display.flip()

    draw_image_full(intro1)
    start = pygame.time.get_ticks()
    while pygame.time.get_ticks() - start < 3000:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
        clock.tick(60)

    draw_image_full(intro2)
    if Path(ASSETS["music"]).exists():
        try:
            pygame.mixer.music.load(ASSETS["music"])
            pygame.mixer.music.play(-1)
        except Exception:
            pass

    waiting = True
    while waiting:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                waiting = False
        clock.tick(60)

    maps_path = Path("Maps.json")
    mapdata = None
    if maps_path.exists():
        with maps_path.open("r", encoding="utf-8") as f:
            mapdata = json.load(f)

    WORLD_TILES_X = mapdata["world"].get("tiles_x", 40) if mapdata else 40
    WORLD_TILES_Y = mapdata["world"].get("tiles_y", 30) if mapdata else 30

    tile_img = scale_to_tile(imgs["tile"], TILE, TILE)

    objects = pygame.sprite.Group()
    obstacles_list = []
    background_tiles = pygame.sprite.Group()
    treadmill_obj = None
    john_obj = None
    tree_obj = None
    girlfriend_obj = None
    tree_objs = []
    tree2_objs = []
    goofy_objs = []   # supports multiple goofy dogs
    unknown_objs = []  # supports multiple unknown entities
    checkpoint_objs = []  # new

    def add_dirt(grid_x, grid_y):
        img = imgs["dirt"]
        pos = (int(grid_x * TILE), int(grid_y * TILE))
        obj = WorldObject(img, tile_w=1, tile_h=1, pos=pos, name="dirt", solid=False)
        background_tiles.add(obj)

    def add_obj(key, grid_x, grid_y, tile_w=1, tile_h=1, solid=True):
        img_down = imgs.get(key)
        if img_down is None:
            img_down = imgs.get(key.lower())
        pos = (int(grid_x * TILE), int(grid_y * TILE))
        if key == "john":
            obj = NPC(img_down, john_up_img, tile_w=tile_w, tile_h=tile_h, pos=pos, name=key, solid=solid, up_sector_deg=90)
        elif key == "girlfriend":
            obj = NPC(img_down, girlfriend_up_img, tile_w=tile_w, tile_h=tile_h, pos=pos, name=key, solid=solid, up_sector_deg=90)
        else:
            obj = WorldObject(img_down, tile_w=tile_w, tile_h=tile_h, pos=pos, name=key, solid=solid)
        objects.add(obj)
        if solid:
            obstacles_list.append(obj)
        return obj

    if mapdata and "objects" in mapdata:
        for o in mapdata["objects"]:
            typ = o.get("type")
            x, y = o.get("x", 0), o.get("y", 0)
            t = typ.lower() if isinstance(typ, str) else ""
            if t == "dirt":
                add_dirt(x, y)
            elif t == "john":
                john_obj = add_obj("john", x, y, tile_w=2, tile_h=2, solid=False)
            elif t == "girlfriend":
                girlfriend_obj = add_obj("girlfriend", x, y, tile_w=2, tile_h=2, solid=False)
            elif t == "mom":
                add_obj("mom", x, y, tile_w=2, tile_h=2)
            elif t == "tree2":
                tree2_obj = add_obj("tree2", x, y, tile_w=6, tile_h=8, solid=True)
                tree2_objs.append(tree2_obj)
            elif t == "tree":
                tree_obj = add_obj("tree", x, y, tile_w=2, tile_h=2.5, solid=False)
                tree_objs.append(tree_obj)
            elif t == "treadmill":
                treadmill_obj = add_obj("treadmill", x, y, tile_w=6, tile_h=8, solid=False)
            elif t in ("goofydog", "goofy dog", "goofy_dog", "goffydog", "goffy dog", "goffy_dog"):
                g = add_obj("goofyDog", x, y, tile_w=2, tile_h=2, solid=False)
                goofy_objs.append(g)
            elif ("goof" in t or "goff" in t) and "dog" in t:
                g = add_obj("goofyDog", x, y, tile_w=2, tile_h=2, solid=False)
                goofy_objs.append(g)
            elif t == "unknown":
                u = add_obj("unknown", x, y, tile_w=2, tile_h=2, solid=False)
                unknown_objs.append(u)
            elif t == "checkpoint":
                c = add_obj("checkpoint", x, y, tile_w=2, tile_h=2, solid=False)
                checkpoint_objs.append(c)
            else:
                if typ in ASSETS:
                    add_obj(typ, x, y)
                elif t in ASSETS:
                    add_obj(t, x, y)
                else:
                    pass
    else:
        girlfriend_obj = add_obj("girlfriend", 10, 8, 2, 2, solid=False)
        john_obj = add_obj("john", 12, 10, 2, 2, solid=False)
        add_obj("mom", 9, 12, 2, 2)
        tree_obj = add_obj("tree", 15, 7, 2, 2.5, solid=False)
        tree_objs.append(tree_obj)
        tree2_obj = add_obj("tree2", 18, 15, 6, 8, solid=True)
        tree2_objs.append(tree2_obj)
        treadmill_obj = add_obj("treadmill", 22, 10, 6, 8, solid=False)
        g = add_obj("goofyDog", 14, 9, 2, 2, solid=False)
        goofy_objs.append(g)
        u = add_obj("unknown", 16, 9, 2, 2, solid=False)
        unknown_objs.append(u)
        # default checkpoint in fallback map
        c = add_obj("checkpoint", 8, 8, 2, 2, solid=False)
        checkpoint_objs.append(c)

    if mapdata and "player" in mapdata:
        p = mapdata["player"]
        p_x, p_y = p.get("x", WORLD_TILES_X // 2), p.get("y", WORLD_TILES_Y // 2)
        player_start = (int(p_x * TILE), int(p_y * TILE))
    else:
        player_start = (TILE * 5, TILE * 5)
    player = Player(imgs["player"], imgs["player1"], player_start, scale=2)
    player_group = pygame.sprite.Group(player)

    initial_player_pos = player_start
    initial_girlfriend_pos = girlfriend_obj.rect.topleft if girlfriend_obj else None
    initial_john_pos = john_obj.rect.topleft if john_obj else None

    for tree in tree_objs:
        tw, th = tree.rect.width, tree.rect.height
        hitbox_w = int(tw / 3)
        hitbox_h = int(th / 4)
        hitbox_x = tree.rect.x + (tw - hitbox_w) // 2
        hitbox_y = tree.rect.y + th - hitbox_h * 2
        tree.block_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
        tree.interaction_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)

    for tree2 in tree2_objs:
        tw, th = tree2.rect.width, tree2.rect.height
        hitbox_w = int(tw / 3)
        hitbox_h = int(th / 4)
        hitbox_x = tree2.rect.x + (tw - hitbox_w) // 2
        hitbox_y = tree2.rect.y + th - hitbox_h * 2
        tree2.block_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
        tree2.interaction_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)

    if treadmill_obj:
        tw, th = treadmill_obj.rect.width, treadmill_obj.rect.height
        hitbox_w = int(tw / 3)
        hitbox_h = int(th / 4)
        hitbox_x = treadmill_obj.rect.x + (tw - hitbox_w) // 2
        hitbox_y = treadmill_obj.rect.y + th - hitbox_h * 2
        treadmill_obj.block_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
        treadmill_obj.interaction_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)

    # For goofy dogs, unknowns, and checkpoints: only create interaction rect (no block_rect so they don't pre-block)
    for g in goofy_objs + unknown_objs + checkpoint_objs:
        tw, th = g.rect.width, g.rect.height
        hitbox_w = int(tw / 2)
        hitbox_h = int(th / 3)
        hitbox_x = g.rect.x + (tw - hitbox_w) // 2
        hitbox_y = g.rect.y + th - hitbox_h * 2
        g.interaction_rect = pygame.Rect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
        # add a helper state flag (previous frame player_near)
        g.player_near = False

    end_img = scale_to_tile(imgs["end"], SCREEN_W, SCREEN_H, keep_aspect=False) if "end" in imgs else None

    message_img = scale_to_tile(imgs["message"], SCREEN_W - 40, 120)
    message2_img = scale_to_tile(imgs["message2"], SCREEN_W - 40, 120)
    message3_img = scale_to_tile(imgs["message3"], SCREEN_W - 40, 120)
    message4_img = scale_to_tile(imgs["message4"], SCREEN_W - 40, 120)

    goofy_img = None
    if "goofyDog" in imgs:
        try:
            goofy_img = scale_to_tile(imgs["goofyDog"], TILE * 2, TILE * 2, keep_aspect=True)
        except Exception:
            goofy_img = imgs["goofyDog"]

    unknown_img = None
    if "unknown" in imgs:
        try:
            unknown_img = scale_to_tile(imgs["unknown"], TILE * 2, TILE * 2, keep_aspect=True)
        except Exception:
            unknown_img = imgs["unknown"]

    checkpoint_img = None
    if "checkpoint" in imgs:
        try:
            checkpoint_img = scale_to_tile(imgs["checkpoint"], TILE * 2, TILE * 2, keep_aspect=True)
        except Exception:
            checkpoint_img = imgs.get("checkpoint")

    showing_message = False
    current_message = None
    john_stopped = False
    girlfriend_following = False
    treadmill_activated = False

    camera = Camera(SCREEN_W, SCREEN_H)

    wolf_imgs = [imgs["wolf1"], imgs["wolf2"]]
    wolf = Wolf(wolf_imgs, SCREEN_H // 2, PLAYER_SPEED * 2)
    wolf_timer = 0
    wolf_next_time = random.uniform(8, 12)

    DAY_DURATION = 60.0
    NIGHT_DURATION = 60.0
    day_night_timer = 0.0
    is_day = True
    DAYNIGHT_TRANS_DUR = 1.0
    daynight_transition = False
    daynight_phase = None
    daynight_t = 0.0
    daynight_overlay_max = 120

    MAX_LIVES = 3
    lives = MAX_LIVES
    invulnerable_timer = 0.0
    INVULNERABLE_DURATION = 1.0

    fading = False
    fade_alpha = 0
    FADE_OUT_DURATION = 1.5
    FADE_IN_DURATION = 0.5
    fade_timer = 0.0
    fade_phase = None

    showing_message = True
    current_message = message4_img
    if not message_beep_playing:
        message_beep_playing = True
        message_beep_timer = 0.0
        message_beep_index = 0
        try:
            message_beeps[0].play()
        except Exception:
            pass

    showing_goofy = False
    goofy_text = ""
    GOOFY_DURATION = 10.0
    goofy_timer = 0.0
    goofy_start_time = 0.0
    GOOFY_CHARS_PER_SEC = 30
    goofy_lines = [
        "i am 20 and i already wasted my life, but at least my socks match.",
        "my white hair is rgb(255, 255, 255) — shiny and confused.",
        "i love developer of this game, Tarik Ganić. now give me snacks!",
        "goofy dog says: that tree owes me 3 belly rubs and a donut.",
        "my goofy developer doesn't clean he's teeth that often.",
        "my goofy developer made me say that he's the best, uh, well he is I guess :/...",
        "goofy wiseness",
        "my hair is 255 255 255, or is it?",
        "i am refrence to developer's dog, named Meri.",
        "warning: 99% puppy energy, 1% existential dread.",
        "i accidentally ate the save file but it's fine, i'm just emotional.",
    ]

    # Unknown fixed message
    unknown_text = "You are trying to find it too? Huh! I became delusional trying. There is no special, hihihihihihi!!!! :::))))"

    # dialog source indicates which image to show: "goofy" or "unknown"
    dialog_source = "goofy"

    # helper: margin for rendering/collision queries (in pixels)
    VIEW_MARGIN = TILE * 2

    def get_visible_rect(cam_offset, margin=VIEW_MARGIN):
        return pygame.Rect(int(cam_offset.x - margin), int(cam_offset.y - margin),
                           SCREEN_W + margin * 2, SCREEN_H + margin * 2)

    def get_nearby_obstacles(reference_rect, obstacles, expand=TILE * 3):
        """Return subset of obstacles whose rect intersects reference_rect inflated by expand.
           This reduces collision checks to nearby objects only."""
        r = reference_rect.inflate(expand, expand)
        return [o for o in obstacles if getattr(o, "solid", False) and r.colliderect(get_collision_rect(o))]

    # ----------------------
    # checkpoint helpers
    # ----------------------
    def save_checkpoint():
        data = {
            "player_pos": [int(player.rect.x), int(player.rect.y)],
            "camera_offset": [float(camera.offset.x), float(camera.offset.y)],
            "is_day": bool(is_day),
            "day_night_timer": float(day_night_timer),
            "girlfriend_following": bool(girlfriend_following),
            "john_stopped": bool(john_stopped),
            "treadmill_activated": bool(treadmill_activated),
            "lives": int(lives),
            "girlfriend_pos": [int(girlfriend_obj.rect.x), int(girlfriend_obj.rect.y)] if girlfriend_obj else None,
            "john_pos": [int(john_obj.rect.x), int(john_obj.rect.y)] if john_obj else None,
            "wolf_active": bool(wolf.active),
            "wolf_rect": [int(wolf.rect.x), int(wolf.rect.y)] if wolf else None,
            # add more fields if you want to persist more things
            "saved_at": time.time(),
        }
        try:
            with CHECKPOINT_FILE.open("w", encoding="utf-8") as f:
                json.dump(data, f)
            return True
        except Exception as e:
            if DEBUG:
                print("Failed to save checkpoint:", e)
            return False

    def load_checkpoint():
        nonlocal is_day, day_night_timer, girlfriend_following, john_stopped, treadmill_activated, lives
        if not CHECKPOINT_FILE.exists():
            return False
        try:
            with CHECKPOINT_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return False
        try:
            pp = data.get("player_pos")
            if pp:
                player.pos = pygame.Vector2(pp[0], pp[1])
                player.rect.topleft = (int(pp[0]), int(pp[1]))
            cam = data.get("camera_offset")
            if cam:
                camera.offset.x = float(cam[0])
                camera.offset.y = float(cam[1])
            is_day = bool(data.get("is_day", True))
            day_night_timer = float(data.get("day_night_timer", 0.0))
            girlfriend_following = bool(data.get("girlfriend_following", False))
            john_stopped = bool(data.get("john_stopped", False))
            treadmill_activated = bool(data.get("treadmill_activated", False))
            lives = int(data.get("lives", MAX_LIVES))
            gp = data.get("girlfriend_pos")
            if gp and girlfriend_obj:
                girlfriend_obj.rect.topleft = (int(gp[0]), int(gp[1]))
            jp = data.get("john_pos")
            if jp and john_obj:
                john_obj.rect.topleft = (int(jp[0]), int(jp[1]))
            if data.get("wolf_active") and wolf:
                wolf.active = True
                wr = data.get("wolf_rect")
                if wr:
                    wolf.rect.x = int(wr[0])
                    wolf.rect.y = int(wr[1])
            return True
        except Exception as e:
            if DEBUG:
                print("Failed to apply checkpoint data:", e)
            return False

    def delete_checkpoint():
        try:
            if CHECKPOINT_FILE.exists():
                CHECKPOINT_FILE.unlink()
        except Exception:
            pass

    # Attempt to load checkpoint (if exists) AFTER objects/player created
    loaded_checkpoint = load_checkpoint()
    if loaded_checkpoint:
        # If checkpoint had treadmill already activated, we shouldn't immediately end,
        # but if the user intended finished state, we'll let existing logic handle it.
        if DEBUG:
            print("Loaded checkpoint from", CHECKPOINT_FILE)

    # short overlay for checkpoint saved notification
    checkpoint_saved_timer = 0.0
    CHECKPOINT_SAVED_DURATION = 2.0

    # --- Secret typing variables ---
    secret = "vudejezakon"
    typing_buffer = ""
    cool_mode = False  # prevents retrigger; set False if you want toggling instead

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        day_night_timer += dt
        if invulnerable_timer > 0:
            invulnerable_timer = max(0.0, invulnerable_timer - dt)
        if message_beep_playing:
            message_beep_timer += dt
            if message_beep_timer >= MESSAGE_BEEP_INTERVAL:
                message_beep_timer -= MESSAGE_BEEP_INTERVAL
                message_beep_index += 1
                if message_beep_index < len(message_beeps):
                    try:
                        message_beeps[message_beep_index].play()
                    except Exception:
                        pass
                else:
                    message_beep_playing = False
        if not daynight_transition and not fading:
            if is_day and day_night_timer >= DAY_DURATION:
                daynight_transition = True
                daynight_phase = "to_night"
                daynight_t = 0.0
            elif (not is_day) and day_night_timer >= NIGHT_DURATION:
                daynight_transition = True
                daynight_phase = "to_day"
                daynight_t = 0.0

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                if showing_message and ev.key == pygame.K_SPACE:
                    showing_message = False
                    for s in message_beeps:
                        try:
                            s.stop()
                        except Exception:
                            pass
                    message_beep_playing = False
                    message_beep_timer = 0.0
                    message_beep_index = 0
                if showing_goofy and ev.key == pygame.K_SPACE:
                    # allow manual close
                    showing_goofy = False
                    goofy_timer = 0.0

                # --- typing-secret handling ---
                # Backspace: remove last char
                if ev.key == pygame.K_BACKSPACE:
                    typing_buffer = typing_buffer[:-1]
                else:
                    # use ev.unicode to get typed char (handles keyboard layout)
                    ch = ev.unicode.lower() if hasattr(ev, "unicode") else ""
                    if ch and ch.isalpha():
                        typing_buffer += ch
                        # keep buffer limited to secret length
                        if len(typing_buffer) > len(secret):
                            typing_buffer = typing_buffer[-len(secret):]

                # check for match (only trigger once)
                if (not cool_mode) and typing_buffer == secret:
                    # attempt to switch textures
                    down_img = imgs.get("cool")
                    up_img = imgs.get("cool1", imgs.get("cool"))
                    # if images weren't preloaded, try loading from disk now
                    if down_img is None and Path("Cool.png").exists():
                        try:
                            down_img = load_image("Cool.png")
                            imgs["cool"] = down_img
                        except Exception:
                            down_img = None
                    if up_img is None and Path("Cool1.png").exists():
                        try:
                            up_img = load_image("Cool1.png")
                            imgs["cool1"] = up_img
                        except Exception:
                            up_img = down_img
                    # apply to player if we have at least a down image
                    if down_img is not None:
                        player.set_textures(down_img, up_img)
                        cool_mode = True
                        # clear buffer so it doesn't retrigger accidentally
                        typing_buffer = ""
                        if DEBUG:
                            print("Secret typed: player textures switched to Cool.png / Cool1.png")
                    else:
                        # no Cool image available; optionally notify in DEBUG
                        if DEBUG:
                            print("Cool.png not found — make sure Cool.png (and optionally Cool1.png) are in the game folder.")

        if treadmill_activated:
            # delete checkpoint when the game is finished (as requested)
            delete_checkpoint()

            screen.fill((0, 0, 0))
            if end_img:
                screen.blit(end_img, (0, 0))
            pygame.display.flip()
            waiting_end = True
            while waiting_end:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                        pygame.quit()
                        sys.exit()
                clock.tick(60)
            continue

        #next logic will preform delete_chekpoint() if r and enter are pressed in the same time and turn off the game so next time game is started it will be restarted
        keys = pygame.key.get_pressed()
        if keys[pygame.K_r] and keys[pygame.K_RETURN]:
            delete_checkpoint()
            running = False
            continue

        if not fading:
            # For collisions, only use nearby obstacles (player-sized vicinity)
            nearby_obs = get_nearby_obstacles(player.rect, obstacles_list + tree2_objs)
            player.update(dt, nearby_obs)

            if john_obj and not john_stopped:
                to_player = pygame.Vector2(player.rect.center) - pygame.Vector2(john_obj.rect.center)
                dist = to_player.length()
                if dist > JOHN_STOP_DISTANCE and dist != 0:
                    move_vec = to_player.normalize() * JOHN_SPEED * dt
                    john_obj.rect.x += int(round(move_vec.x))
                    john_obj.rect.y += int(round(move_vec.y))
                    john_obj.set_direction(move_vec.x, move_vec.y)
                    john_obj.update_bump(dt, moving=True)
                else:
                    if dist != 0:
                        john_obj.set_direction(0, to_player.y)
                    john_obj.update_bump(dt, moving=False)
            if girlfriend_obj and girlfriend_following:
                to_player = pygame.Vector2(player.rect.center) - pygame.Vector2(girlfriend_obj.rect.center)
                dist = to_player.length()
                if dist > GIRLFRIEND_STOP_DISTANCE and dist != 0:
                    move_vec = to_player.normalize() * GIRLFRIEND_SPEED * dt
                    girlfriend_obj.rect.x += int(round(move_vec.x))
                    girlfriend_obj.rect.y += int(round(move_vec.y))
                    girlfriend_obj.set_direction(move_vec.x, move_vec.y)
                    girlfriend_obj.update_bump(dt, moving=True)
                else:
                    if dist != 0:
                        girlfriend_obj.set_direction(0, to_player.y)
                    girlfriend_obj.update_bump(dt, moving=False)

        if daynight_transition:
            daynight_t += dt
            t = min(1.0, daynight_t / DAYNIGHT_TRANS_DUR)
            if daynight_phase == "to_night":
                current_dn_alpha = int(daynight_overlay_max * t)
            else:
                current_dn_alpha = int(daynight_overlay_max * (1.0 - t))
            if daynight_t >= DAYNIGHT_TRANS_DUR:
                if daynight_phase == "to_night":
                    is_day = False
                    wolf_timer = 0
                    wolf_next_time = 5.0
                else:
                    is_day = True
                    wolf_timer = 0
                    wolf_next_time = random.uniform(8, 12)
                day_night_timer = 0.0
                daynight_transition = False
                daynight_phase = None
                daynight_t = 0.0
        else:
            current_dn_alpha = 0 if is_day else daynight_overlay_max

        if girlfriend_following and not fading:
            if is_day:
                wolf.active = False
            else:
                wolf_timer += dt
                if not wolf.active and wolf_timer > wolf_next_time:
                    wolf_y = player.rect.centery
                    wolf.start(wolf_y, camera.offset.x)
                    wolf.rect.x = player.rect.x + SCREEN_W
                    wolf_timer = 0
                    wolf_next_time = 5.0

        wolf.update(dt)

        if wolf.active and not fading and invulnerable_timer <= 0 and wolf.rect.colliderect(player.rect):
            wolf.active = False
            wolf_timer = 0
            wolf_next_time = 5.0 if not is_day else random.uniform(8, 12)
            lives -= 1
            invulnerable_timer = INVULNERABLE_DURATION
            if lives <= 0:
                fading = True
                fade_phase = "out"
                fade_timer = 0.0

        tree1_message_shown = False
        if not fading:
            # Interaction checks only with objects near the player (faster)
            # For trees we keep them in tree_objs list; they are relatively few.
            for tree in tree_objs:
                if player.rect.colliderect(get_interaction_rect(tree)):
                    showing_message = True
                    current_message = message_img
                    tree1_message_shown = True
                    if not message_beep_playing:
                        message_beep_playing = True
                        message_beep_timer = 0.0
                        message_beep_index = 0
                        try:
                            message_beeps[0].play()
                        except Exception:
                            pass
                    break

            if not tree1_message_shown:
                if girlfriend_obj and not girlfriend_following and player.rect.colliderect(get_interaction_rect(girlfriend_obj)):
                    showing_message = True
                    current_message = message2_img
                    john_stopped = True
                    girlfriend_following = True
                    if not message_beep_playing:
                        message_beep_playing = True
                        message_beep_timer = 0.0
                        message_beep_index = 0
                        try:
                            message_beeps[0].play()
                        except Exception:
                            pass
                elif john_obj and john_stopped and player.rect.colliderect(get_interaction_rect(john_obj)):
                    showing_message = True
                    current_message = message3_img
                    if not message_beep_playing:
                        message_beep_playing = True
                        message_beep_timer = 0.0
                        message_beep_index = 0
                        try:
                            message_beeps[0].play()
                        except Exception:
                            pass

            if treadmill_obj and player.rect.colliderect(get_interaction_rect(treadmill_obj)):
                pygame.mixer.music.stop()
                if Path(ASSETS["realisation"]).exists():
                    try:
                        pygame.mixer.music.load(ASSETS["realisation"])
                        pygame.mixer.music.play()
                    except Exception:
                        pass
                treadmill_activated = True

            # NEW: goofy dog entry-trigger handling (supports many goofy dogs)
            for g in goofy_objs:
                now_near = player.rect.colliderect(get_interaction_rect(g))
                prev_near = getattr(g, "player_near", False)
                # Trigger only on entering (edge) and only if no goofy message currently showing
                if now_near and (not prev_near) and (not showing_goofy):
                    showing_goofy = True
                    goofy_text = random.choice(goofy_lines)
                    dialog_source = "goofy"
                    goofy_timer = GOOFY_DURATION
                    goofy_start_time = time.time()
                    if not message_beep_playing:
                        message_beep_playing = True
                        message_beep_timer = 0.0
                        message_beep_index = 0
                        try:
                            message_beeps[0].play()
                        except Exception:
                            pass
                # update stored state
                g.player_near = now_near

            # Unknown entity trigger (behaves like goofy but has fixed text and different image)
            for u in unknown_objs:
                now_near = player.rect.colliderect(get_interaction_rect(u))
                prev_near = getattr(u, "player_near", False)
                if now_near and (not prev_near) and (not showing_goofy):
                    showing_goofy = True
                    goofy_text = unknown_text
                    dialog_source = "unknown"
                    goofy_timer = GOOFY_DURATION
                    goofy_start_time = time.time()
                    if not message_beep_playing:
                        message_beep_playing = True
                        message_beep_timer = 0.0
                        message_beep_index = 0
                        try:
                            message_beeps[0].play()
                        except Exception:
                            pass
                u.player_near = now_near

            # Checkpoint trigger: save when player enters the interaction rect
            for c in checkpoint_objs:
                now_near = player.rect.colliderect(get_interaction_rect(c))
                prev_near = getattr(c, "player_near", False)
                if now_near and (not prev_near):
                    ok = save_checkpoint()
                    checkpoint_saved_timer = CHECKPOINT_SAVED_DURATION
                    # play beep
                    try:
                        message_beeps[0].play()
                    except Exception:
                        pass
                    if DEBUG:
                        print("Checkpoint saved:", CHECKPOINT_FILE if ok else "failed")
                c.player_near = now_near

        camera.update(player.rect)

        # ------------------------
        # RENDERING (culled)
        # ------------------------
        screen.fill((0, 0, 0))
        visible_rect = get_visible_rect(camera.offset)

        # Draw background tiles — iterate using camera offset (restored original tiling loop)
        start_ty = int(camera.offset.y // TILE)
        start_tx = int(camera.offset.x // TILE)
        # draw dirt (only ones in visible_rect)
        for obj in background_tiles:
            if visible_rect.colliderect(obj.rect):
                screen.blit(obj.image, (obj.rect.x - camera.offset.x, obj.rect.y - camera.offset.y))

        # draw grass tiles for area in view (restored loop similar to original)
        for ty in range(start_ty, start_ty + SCREEN_H // TILE + 2):
            for tx in range(start_tx, start_tx + SCREEN_W // TILE + 2):
                has_dirt = any(obj.rect.x // TILE == tx and obj.rect.y // TILE == ty for obj in background_tiles)
                if not has_dirt:
                    screen.blit(tile_img, (tx * TILE - camera.offset.x, ty * TILE - camera.offset.y))

        # Build render list only for visible objects (plus player & active wolf)
        renderables = []
        # objects group may be large; filter by visible_rect
        for obj in objects:
            if visible_rect.colliderect(obj.rect):
                renderables.append(obj)
        for t in tree_objs + tree2_objs:
            if visible_rect.colliderect(t.rect) and t not in renderables:
                renderables.append(t)
        if treadmill_obj and visible_rect.colliderect(treadmill_obj.rect) and treadmill_obj not in renderables:
            renderables.append(treadmill_obj)
        if wolf.active and visible_rect.colliderect(wolf.rect):
            renderables.append(wolf)
        # always render player (it's on screen by camera design)
        renderables.append(player)

        # sort by bottom for correct overlap
        renderables_sorted = sorted(renderables, key=lambda o: o.rect.bottom)

        for ent in renderables_sorted:
            draw_img = getattr(ent, "image", None)
            if draw_img is None:
                continue
            # custom draw for checkpoints to show checkpoint_img if present
            if getattr(ent, "name", None) == "checkpoint" and checkpoint_img is not None:
                draw_img = checkpoint_img
            # flip on the fly only when necessary (cheap compared to scaling)
            if getattr(ent, "last_x_dir", 1) < 0:
                draw_img = pygame.transform.flip(draw_img, True, False)
            visual_offset = getattr(ent, "visual_offset_y", 0)
            screen.blit(draw_img, (ent.rect.x - camera.offset.x, ent.rect.y - camera.offset.y + visual_offset))

        # dialogs and overlays (unchanged logic)
        if showing_goofy:
            goofy_timer -= dt
            elapsed = GOOFY_DURATION - max(0.0, goofy_timer)
            chars = min(len(goofy_text), int(elapsed * GOOFY_CHARS_PER_SEC))
            reveal_text = goofy_text[:chars]
            overlay_h = 140
            overlay = pygame.Surface((SCREEN_W, overlay_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, SCREEN_H - overlay_h))
            img_w = 0
            # Show the appropriate image depending on source
            if (dialog_source == "unknown") and unknown_img:
                img_w = unknown_img.get_width() + 16
                screen.blit(unknown_img, (20, SCREEN_H - overlay_h + 10))
            elif dialog_source == "goofy" and goofy_img:
                img_w = goofy_img.get_width() + 16
                screen.blit(goofy_img, (20, SCREEN_H - overlay_h + 10))
            text_rect = pygame.Rect(20 + img_w, SCREEN_H - overlay_h + 10,
                                   SCREEN_W - (40 + img_w), overlay_h - 20)
            render_wrapped_text(screen, reveal_text, goofy_font, (255, 220, 220), text_rect)
            prompt = font.render("Press SPACE to close", True, (200, 200, 200))
            screen.blit(prompt, (SCREEN_W - prompt.get_width() - 16, SCREEN_H - prompt.get_height() - 8))
            if goofy_timer <= 0:
                showing_goofy = False
                goofy_timer = 0.0
                dialog_source = "goofy"

        if (not showing_goofy) and showing_message and current_message:
            overlay = pygame.Surface((SCREEN_W, current_message.get_height() + 20), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (10, SCREEN_H - overlay.get_height() - 10))
            screen.blit(current_message, (20, SCREEN_H - overlay.get_height()))
            txt = font.render("Press SPACE to close message", True, (255, 255, 255))
            screen.blit(txt, (SCREEN_W - txt.get_width() - 20, SCREEN_H - txt.get_height() - 20))

        if current_dn_alpha > 0:
            night_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            night_overlay.fill((0, 0, 0, current_dn_alpha))
            screen.blit(night_overlay, (0, 0))

        # checkpoint saved small overlay
        if checkpoint_saved_timer > 0:
            checkpoint_saved_timer -= dt
            msg = "Checkpoint saved"
            txt = font.render(msg, True, (200, 255, 200))
            bg = pygame.Surface((txt.get_width() + 20, txt.get_height() + 12), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 180))
            x = (SCREEN_W - bg.get_width()) // 2
            y = 10
            screen.blit(bg, (x, y))
            screen.blit(txt, (x + 10, y + 6))

        # version / day text / hearts (unchanged)
        version_text = "beta 0.5"
        txt = font.render(version_text, True, (255, 255, 255))
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            screen.blit(font.render(version_text, True, (0, 0, 0)), (10 + dx, 10 + dy))
        screen.blit(txt, (10, 10))

        dn_text = "Day" if is_day else "Night"
        dn_color = (255, 255, 0) if is_day else (100, 100, 255)
        dn_txt = font.render(dn_text, True, dn_color)
        dn_x = SCREEN_W - dn_txt.get_width() - 20
        dn_y = 10
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            screen.blit(font.render(dn_text, True, (0, 0, 0)), (dn_x + dx, dn_y + dy))
        screen.blit(dn_txt, (dn_x, dn_y))

        heart_spacing = 6
        for i in range(MAX_LIVES):
            x = 10 + i * (heart_img.get_width() + heart_spacing)
            y = 50
            if i < lives:
                screen.blit(heart_img, (x, y))
            else:
                dim = heart_img.copy()
                dim.fill((80, 80, 80, 160), special_flags=pygame.BLEND_RGBA_MULT)
                screen.blit(dim, (x, y))

        if fading:
            if fade_phase == "out":
                fade_timer += dt
                t = min(1.0, fade_timer / FADE_OUT_DURATION)
                fade_alpha = int(255 * t)
                fade_surf = pygame.Surface((SCREEN_W, SCREEN_H))
                fade_surf.set_alpha(fade_alpha)
                fade_surf.fill((0, 0, 0))
                screen.blit(fade_surf, (0, 0))
                if fade_timer >= FADE_OUT_DURATION:
                    # Try to restore from checkpoint if present
                    restored_from_checkpoint = False
                    if CHECKPOINT_FILE.exists():
                        try:
                            restored_from_checkpoint = load_checkpoint()
                        except Exception:
                            restored_from_checkpoint = False

                    if not restored_from_checkpoint:
                        # No valid checkpoint -> fallback to initial starting state
                        player.pos = pygame.Vector2(initial_player_pos)
                        player.rect.topleft = initial_player_pos
                        player.last_y_dir = 1
                        if girlfriend_obj and initial_girlfriend_pos:
                            girlfriend_obj.rect.topleft = initial_girlfriend_pos
                        if john_obj and initial_john_pos:
                            john_obj.rect.topleft = initial_john_pos
                        girlfriend_following = False
                        john_stopped = False
                        showing_message = False
                        treadmill_activated = False
                        lives = MAX_LIVES
                    else:
                        # Successfully restored from checkpoint:
                        # ensure player.pos/rect are integers and camera offset applied already by load_checkpoint()
                        player.pos = pygame.Vector2(int(player.rect.x), int(player.rect.y))
                        player.rect.topleft = (int(player.rect.x), int(player.rect.y))
                        # invulnerable and timers reset so player doesn't immediately die again
                        invulnerable_timer = INVULNERABLE_DURATION
                        showing_message = False
                        # do NOT overwrite lives (load_checkpoint already set it)

                    fade_phase = "in"
                    fade_timer = 0.0

            elif fade_phase == "in":
                fade_timer += dt
                t = min(1.0, fade_timer / FADE_IN_DURATION)
                fade_alpha = int(255 * (1.0 - t))
                fade_surf = pygame.Surface((SCREEN_W, SCREEN_H))
                fade_surf.set_alpha(fade_alpha)
                fade_surf.fill((0, 0, 0))
                screen.blit(fade_surf, (0, 0))
                if fade_timer >= FADE_IN_DURATION:
                    fading = False
                    fade_phase = None
                    fade_timer = 0.0
                    fade_alpha = 0

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
