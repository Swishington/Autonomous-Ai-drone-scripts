"""3D renderer for Kart Rush (OpenGL via ModernGL).

The race itself still runs on the flat 2D simulation in kart_racer.py; this
module only *draws* it in 3D:

  * the cartoon track artwork becomes a ground texture seen in perspective,
  * trees, lollipops, gumdrops and mushrooms are toon-shaded 3D models with
    ink outlines (inverted hull), plus hills and clouds on the horizon,
  * karts are 3D models that lean into turns, with the characters riding on
    them as upright cut-outs (like classic kart racers),
  * each player gets a smooth chase camera; split-screen uses viewports,
  * the 2D HUD and menus are drawn on a transparent layer composited on top.

World mapping: 2D (x, y) -> 3D (x, height, y), units are the game's pixels.
"""

import math
import random
import struct
from array import array

import moderngl
import pygame

# ----------------------------------------------------------------------------
# Small vector / matrix helpers (row-major lists; packed column-major for GLSL)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2)
    return [[f / aspect, 0, 0, 0], [0, f, 0, 0],
            [0, 0, (far + near) / (near - far), (2 * far * near) / (near - far)], [0, 0, -1, 0]]


def look_at(eye, target, up=(0.0, 1.0, 0.0)):
    f = _norm(_sub(target, eye))
    s = _norm(_cross(f, up))
    u = _cross(s, f)
    return [[s[0], s[1], s[2], -_dot(s, eye)], [u[0], u[1], u[2], -_dot(u, eye)],
            [-f[0], -f[1], -f[2], _dot(f, eye)], [0, 0, 0, 1]]


def matmul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def pack(m):
    return struct.pack("16f", *[m[r][c] for c in range(4) for r in range(4)])


def kart_matrix(x, y, z, heading, roll=0.0, yaw_extra=0.0):
    """Local kart space (+X forward, +Z right, +Y up) to world space."""
    h = heading + yaw_extra
    ch, sh, cr, sr = math.cos(h), math.sin(h), math.cos(roll), math.sin(roll)
    # yaw (about Y) * roll (about local X)
    return [[ch, -sh * sr, -sh * cr, x],
            [0.0, cr, -sr, y],
            [sh, ch * sr, ch * cr, z],
            [0, 0, 0, 1]]


IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

# ----------------------------------------------------------------------------
# Mesh building: non-indexed triangles, each vertex = pos, normal, colour, outline-dir


class MeshBuilder:
    def __init__(self):
        self.data = array("f")

    def tri(self, a, b, c, normals, color, onormals, facing=None):
        """Add a triangle; winding is fixed so it faces `facing` (or the average normal)."""
        want = facing or _norm(tuple(sum(n[i] for n in normals) for i in range(3)))
        if _dot(_cross(_sub(b, a), _sub(c, a)), want) < 0:
            b, c = c, b
            normals = (normals[0], normals[2], normals[1])
            onormals = (onormals[0], onormals[2], onormals[1])
        col = (color[0] / 255, color[1] / 255, color[2] / 255)
        for p, n, o in zip((a, b, c), normals, onormals):
            self.data.extend(p)
            self.data.extend(n)
            self.data.extend(col)
            self.data.extend(o)

    def box(self, x0, x1, y0, y1, z0, z1, color):
        c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        hx, hy, hz = (x1 - x0) / 2 or 1, (y1 - y0) / 2 or 1, (z1 - z0) / 2 or 1
        faces = [((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
                 ((-1, 0, 0), [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]),
                 ((0, 1, 0), [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)]),
                 ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
                 ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
                 ((0, 0, -1), [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)])]
        for n, q in faces:
            on = [_norm(((p[0] - c[0]) / hx, (p[1] - c[1]) / hy, (p[2] - c[2]) / hz)) for p in q]
            self.tri(q[0], q[1], q[2], (n, n, n), color, (on[0], on[1], on[2]), n)
            self.tri(q[0], q[2], q[3], (n, n, n), color, (on[0], on[2], on[3]), n)

    def sphere(self, center, radius, color, slices=10, stacks=7, squash=1.0, color_fn=None):
        cx, cy, cz = center

        def pt(i, j):
            th = 2 * math.pi * i / slices
            ph = math.pi * j / stacks
            n = (math.sin(ph) * math.cos(th), math.cos(ph), math.sin(ph) * math.sin(th))
            return (cx + n[0] * radius, cy + n[1] * radius * squash, cz + n[2] * radius), _norm((n[0], n[1] / squash, n[2]))

        for j in range(stacks):
            for i in range(slices):
                (a, na), (b, nb), (c, nc), (d, nd) = pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)
                col = color_fn(i, j) if color_fn else color
                if j > 0:
                    self.tri(a, b, c, (na, nb, nc), col, (na, nb, nc))
                if j < stacks - 1:
                    self.tri(a, c, d, (na, nc, nd), col, (na, nc, nd))

    def cylinder(self, base, axis, radius, length, color, segments=10, cap_color=None):
        """Cylinder from `base` along unit `axis`."""
        ax = _norm(axis)
        tmp = (1, 0, 0) if abs(ax[0]) < 0.9 else (0, 0, 1)
        u = _norm(_cross(ax, tmp))
        v = _cross(ax, u)
        top = (base[0] + ax[0] * length, base[1] + ax[1] * length, base[2] + ax[2] * length)

        def ring(center, i):
            a = 2 * math.pi * i / segments
            d = (u[0] * math.cos(a) + v[0] * math.sin(a), u[1] * math.cos(a) + v[1] * math.sin(a),
                 u[2] * math.cos(a) + v[2] * math.sin(a))
            return (center[0] + d[0] * radius, center[1] + d[1] * radius, center[2] + d[2] * radius), d

        neg = (-ax[0], -ax[1], -ax[2])
        for i in range(segments):
            (p0, d0), (p1, d1) = ring(base, i), ring(base, i + 1)
            (q0, _), (q1, _) = ring(top, i), ring(top, i + 1)
            o0b, o1b = _norm(tuple(d0[k] + neg[k] * 0.6 for k in range(3))), _norm(tuple(d1[k] + neg[k] * 0.6 for k in range(3)))
            o0t, o1t = _norm(tuple(d0[k] + ax[k] * 0.6 for k in range(3))), _norm(tuple(d1[k] + ax[k] * 0.6 for k in range(3)))
            self.tri(p0, p1, q1, (d0, d1, d1), color, (o0b, o1b, o1t))
            self.tri(p0, q1, q0, (d0, d1, d0), color, (o0b, o1t, o0t))
            cc = cap_color or color
            self.tri(top, q0, q1, (ax, ax, ax), cc, (ax, o0t, o1t), ax)
            self.tri(base, p1, p0, (neg, neg, neg), cc, (neg, o1b, o0b), neg)

    def bytes(self):
        return self.data.tobytes()


def lighten(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)

# ----------------------------------------------------------------------------
# Shaders


MESH_VS = """
#version 330
uniform mat4 u_vp;
uniform mat4 u_model;
uniform float u_outline;
in vec3 in_pos; in vec3 in_norm; in vec3 in_col; in vec3 in_onorm;
out vec3 v_norm; out vec3 v_col; out vec3 v_world;
void main() {
    vec4 w = u_model * vec4(in_pos + in_onorm * u_outline, 1.0);
    v_world = w.xyz;
    v_norm = mat3(u_model) * in_norm;
    v_col = in_col;
    gl_Position = u_vp * w;
}
"""

MESH_FS = """
#version 330
uniform vec3 u_light; uniform vec3 u_cam; uniform vec3 u_fog_col; uniform vec2 u_fog;
uniform int u_ink; uniform vec3 u_ink_col;
in vec3 v_norm; in vec3 v_col; in vec3 v_world;
out vec4 f_color;
void main() {
    vec3 c;
    if (u_ink == 1) {
        c = u_ink_col;
    } else {
        vec3 n = normalize(v_norm);
        float d = dot(n, u_light);
        float t = d > 0.55 ? 1.0 : (d > 0.1 ? 0.84 : 0.68);            // 3-step toon shading
        float rim = pow(1.0 - max(dot(n, normalize(u_cam - v_world)), 0.0), 3.0) * 0.18;
        c = v_col * (0.38 + 0.72 * t) + rim;
    }
    float fog = clamp((distance(v_world, u_cam) - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    f_color = vec4(mix(c, u_fog_col, fog), 1.0);
}
"""

GROUND_VS = """
#version 330
uniform mat4 u_vp; uniform vec2 u_world;
in vec3 in_pos;
out vec2 v_uv; out vec3 v_world;
void main() {
    v_uv = in_pos.xz / u_world;
    v_world = in_pos;
    gl_Position = u_vp * vec4(in_pos, 1.0);
}
"""

GROUND_FS = """
#version 330
uniform sampler2D u_tex; uniform vec3 u_cam; uniform vec3 u_fog_col; uniform vec2 u_fog; uniform vec3 u_grass;
in vec2 v_uv; in vec3 v_world;
out vec4 f_color;
void main() {
    vec3 c = (v_uv.x < 0.0 || v_uv.y < 0.0 || v_uv.x > 1.0 || v_uv.y > 1.0) ? u_grass : texture(u_tex, v_uv).rgb;
    float fog = clamp((distance(v_world, u_cam) - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    f_color = vec4(mix(c, u_fog_col, fog), 1.0);
}
"""

SPRITE_VS = """
#version 330
uniform mat4 u_vp;
in vec3 in_pos; in vec2 in_uv; in vec4 in_col;
out vec2 v_uv; out vec4 v_col; out vec3 v_world;
void main() { v_uv = in_uv; v_col = in_col; v_world = in_pos; gl_Position = u_vp * vec4(in_pos, 1.0); }
"""

SPRITE_FS = """
#version 330
uniform sampler2D u_tex; uniform vec3 u_cam; uniform vec3 u_fog_col; uniform vec2 u_fog; uniform float u_cutout;
in vec2 v_uv; in vec4 v_col; in vec3 v_world;
out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv) * v_col;
    if (c.a < u_cutout) discard;
    float fog = clamp((distance(v_world, u_cam) - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    f_color = vec4(mix(c.rgb, u_fog_col, fog), c.a);
}
"""

SCREEN_VS = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() { v_uv = vec2(in_pos.x * 0.5 + 0.5, 0.5 - in_pos.y * 0.5); gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

OVERLAY_FS = """
#version 330
uniform sampler2D u_tex;
in vec2 v_uv;
out vec4 f_color;
void main() { f_color = texture(u_tex, v_uv); }
"""

SKY_FS = """
#version 330
uniform vec3 u_top; uniform vec3 u_horizon;
in vec2 v_uv;
out vec4 f_color;
void main() { f_color = vec4(mix(u_top, u_horizon, smoothstep(0.0, 0.62, v_uv.y)), 1.0); }
"""

SKY_TOP = (0.40, 0.66, 1.0)
SKY_HORIZON = (0.80, 0.91, 1.0)
FOG = (700.0, 2900.0)
LIGHT = _norm((-0.45, 0.8, -0.35))
INK = (38 / 255, 24 / 255, 48 / 255)


def _sprite_texture(ctx, surface):
    tex = ctx.texture(surface.get_size(), 4, pygame.image.tobytes(surface, "RGBA"))
    tex.build_mipmaps()
    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    return tex


def _circle_sprite(size=64, rim=True):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    if rim:
        pygame.draw.circle(s, (38, 24, 48, 255), (size // 2, size // 2), size // 2 - 1)
        pygame.draw.circle(s, (255, 255, 255, 255), (size // 2, size // 2), size // 2 - 6)
    else:
        for r in range(size // 2, 0, -1):  # soft blob for shadows
            a = int(150 * (1 - r / (size / 2)) ** 0.6)
            pygame.draw.circle(s, (20, 10, 40, a), (size // 2, size // 2), r)
    return s


def _star_sprite(size=64):
    s = pygame.Surface((size, size), pygame.SRCALPHA)

    def star(r, col):
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((size / 2 + math.cos(a) * rr, size / 2 + math.sin(a) * rr))
        pygame.draw.polygon(s, col, pts)

    star(size / 2 - 1, (38, 24, 48, 255))
    star(size / 2 - 7, (255, 255, 255, 255))
    return s


class Renderer3D:
    def __init__(self, headless_size=None):
        """Use the current pygame OpenGL window, or an offscreen buffer when headless_size is given."""
        if headless_size:
            self.ctx = moderngl.create_standalone_context(backend="egl")
            self.fbo = self.ctx.simple_framebuffer(headless_size, components=4)
            self.size = headless_size
        else:
            self.ctx = moderngl.create_context()
            self.fbo = self.ctx.screen
            self.size = pygame.display.get_window_size()
        ctx = self.ctx
        self.mesh_prog = ctx.program(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self.ground_prog = ctx.program(vertex_shader=GROUND_VS, fragment_shader=GROUND_FS)
        self.sprite_prog = ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SPRITE_FS)
        self.overlay_prog = ctx.program(vertex_shader=SCREEN_VS, fragment_shader=OVERLAY_FS)
        self.sky_prog = ctx.program(vertex_shader=SCREEN_VS, fragment_shader=SKY_FS)
        self.sky_prog["u_top"].value = SKY_TOP
        self.sky_prog["u_horizon"].value = SKY_HORIZON
        for p in (self.mesh_prog, self.ground_prog, self.sprite_prog):
            p["u_fog_col"].value = SKY_HORIZON
            p["u_fog"].value = FOG
        self.mesh_prog["u_light"].value = LIGHT
        self.mesh_prog["u_ink_col"].value = INK

        quad = ctx.buffer(struct.pack("8f", -1, -1, 1, -1, -1, 1, 1, 1))
        self.overlay_vao = ctx.vertex_array(self.overlay_prog, [(quad, "2f", "in_pos")])
        self.sky_vao = ctx.vertex_array(self.sky_prog, [(quad, "2f", "in_pos")])
        self.overlay_tex = None
        self.cams = {}
        self.last_time = None

    def load_world(self, track, roster):
        """Build the textures and models (takes a moment; show the loading screen first)."""
        ctx = self.ctx
        self.track = track

        # Ground: the track artwork plus a big grassy apron out to the horizon.
        ground = track.ground_surface
        self.ground_tex = ctx.texture(ground.get_size(), 3, pygame.image.tobytes(ground, "RGB"))
        self.ground_tex.build_mipmaps()
        self.ground_tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        try:
            self.ground_tex.anisotropy = 8.0
        except Exception:  # noqa: BLE001 - not every driver supports it
            pass
        W, H = ground.get_size()
        self.world = (W, H)
        e = 9000
        gq = [(-e, 0, -e), (W + e, 0, -e), (W + e, 0, H + e), (-e, 0, -e), (W + e, 0, H + e), (-e, 0, H + e)]
        self.ground_vao = ctx.vertex_array(self.ground_prog, [(ctx.buffer(array("f", [c for p in gq for c in p]).tobytes()), "3f", "in_pos")])
        self.ground_prog["u_world"].value = (W, H)
        self.ground_prog["u_grass"].value = (118 / 255, 196 / 255, 84 / 255)

        self.scenery_vao = self._vao(self._build_scenery(track))
        self.kart_vaos = {id(ch): self._vao(self._build_kart(ch)) for ch in roster}
        self.rider_tex = {id(ch): _sprite_texture(ctx, ch.avatar_full) for ch in roster}
        self.circle_tex = _sprite_texture(ctx, _circle_sprite())
        self.shadow_tex = _sprite_texture(ctx, _circle_sprite(rim=False))
        self.star_tex = _sprite_texture(ctx, _star_sprite())
        self.tag_tex = {}
        self.sprite_buf = ctx.buffer(reserve=4 * 9 * 6 * 2000, dynamic=True)
        self.sprite_vao = ctx.vertex_array(self.sprite_prog, [(self.sprite_buf, "3f 2f 4f", "in_pos", "in_uv", "in_col")])
        shadows = array("f")  # props never move, so their shadows are built once
        for x, y, r, kind in track.obstacles:
            self._flat_quad(shadows, x + 6, 0.5, y + 8, r * 1.5, (1, 1, 1, 0.9))
        self.prop_shadow_vao = ctx.vertex_array(self.sprite_prog, [(ctx.buffer(shadows.tobytes()), "3f 2f 4f", "in_pos", "in_uv", "in_col")])

    def _vao(self, builder):
        buf = self.ctx.buffer(builder.bytes())
        return self.ctx.vertex_array(self.mesh_prog, [(buf, "3f 3f 3f 3f", "in_pos", "in_norm", "in_col", "in_onorm")])

    # --- models ---------------------------------------------------------------
    @staticmethod
    def _build_scenery(track):
        m = MeshBuilder()
        for x, y, r, kind in track.obstacles:
            rng = random.Random(int(x) * 7 + int(y))
            if kind == "tree":
                m.cylinder((x, 0, y), (0, 1, 0), r * 0.28, r * 1.1, (150, 100, 60), 8)
                green = rng.choice([(70, 170, 80), (60, 155, 75), (90, 185, 85)])
                m.sphere((x, r * 1.75, y), r * 1.0, green)
                m.sphere((x + r * 0.45, r * 1.45, y - r * 0.3), r * 0.62, lighten(green, 18))
                m.sphere((x - r * 0.4, r * 2.35, y + r * 0.2), r * 0.55, lighten(green, 30))
            elif kind == "lollipop":
                m.cylinder((x, 0, y), (0, 1, 0), r * 0.09, r * 2.0, (250, 248, 252), 6)
                pink, blue = (255, 90, 150), (110, 200, 255)
                m.sphere((x, r * 2.3, y), r * 0.85, pink, slices=12, stacks=8,
                         color_fn=lambda i, j: (255, 255, 255) if i % 2 else (pink if i % 4 == 0 else blue))
            elif kind == "gumdrop":
                col = random.Random(int(x) * 31 + int(y)).choice([(255, 90, 130), (120, 220, 120), (255, 200, 70), (170, 130, 255)])
                m.sphere((x, r * 0.15, y), r * 1.0, col, squash=0.85)
            else:  # mushroom
                m.cylinder((x, 0, y), (0, 1, 0), r * 0.38, r * 0.9, (250, 240, 220), 8)
                m.sphere((x, r * 0.95, y), r * 1.05, (232, 52, 62), squash=0.62)
                for k in range(5):
                    a = k * 2 * math.pi / 5 + rng.uniform(0, 1)
                    m.sphere((x + math.cos(a) * r * 0.62, r * 1.32, y + math.sin(a) * r * 0.62), r * 0.2, (255, 250, 245), 6, 4)
        # Rolling hills and puffy clouds out past the edges of the map.
        W, H = 3200, 2300
        rng = random.Random(11)
        for i in range(46):
            a = 2 * math.pi * i / 46 + rng.uniform(-0.04, 0.04)
            d = rng.uniform(2300, 3300)
            hx, hz = W / 2 + math.cos(a) * d * 1.25, H / 2 + math.sin(a) * d
            m.sphere((hx, -60, hz), rng.uniform(380, 720), rng.choice([(96, 178, 80), (110, 190, 90), (84, 166, 74)]),
                     slices=12, stacks=8, squash=0.55)
        for i in range(16):
            cx, cz, cy = rng.uniform(-1500, W + 1500), rng.uniform(-1500, H + 1500), rng.uniform(900, 1300)
            for k in range(4):
                m.sphere((cx + k * 90 - 135, cy + rng.uniform(-20, 30), cz + rng.uniform(-40, 40)), rng.uniform(70, 120),
                         (255, 255, 255), 8, 6, squash=0.7)
        return m

    @staticmethod
    def _build_kart(ch):
        m = MeshBuilder()
        body, accent = ch.body, ch.accent
        dark = lighten(body, -70)
        tyre, hub = (45, 40, 55), (190, 185, 200)
        if ch.style == "hotrod":
            m.box(-30, 26, 5, 17, -13, 13, body)
            m.box(8, 34, 5, 13, -11, 11, body)                         # long bonnet
            m.box(-16, 6, 17, 27, -11, 11, (170, 230, 255))             # glass cabin
            m.box(-17, 7, 26, 29, -12, 12, body)                        # roof
            for zz in (-7, 0, 7):                                      # flame stripes on the bonnet
                m.box(10, 30, 13, 14, zz - 2, zz + 2, accent)
            for zz in (-6, 6):
                m.cylinder((-32, 10, zz), (-1, 0, 0), 2.2, 8, (215, 215, 225), 6)
            for ex in (-5, 5):                                         # cartoon eyes on the windscreen
                m.sphere((7, 22, ex), 4.2, (255, 255, 255), 8, 6)
                m.sphere((10, 22, ex), 2.0, (30, 25, 45), 6, 4)
            wheels = [(-18, 9, 9), (22, 7, 7)]
        else:
            m.box(-24, 24, 4, 15, -13, 13, body)
            m.box(24, 31, 4, 11, -9, 9, accent)                         # nose
            m.box(-24, 24, 15, 16.5, -3.5, 3.5, accent)                 # racing stripe
            m.box(-31, -25, 15, 21, -16, 16, dark)                      # rear spoiler
            m.box(-29, -27, 11, 15, -10, 10, dark)
            m.box(-12, 4, 15, 23, -9, 9, dark)                          # seat
            m.cylinder((10, 18, 0), (1, 0.4, 0), 1.6, 10, (60, 55, 70), 6)   # steering column
            wheels = [(-17, 8, 8), (17, 8, 8)]
        for wx, wr, ww in wheels:
            for side in (-1, 1):
                z = side * (14 + ww / 2)
                m.cylinder((wx, wr, z - ww / 2), (0, 0, 1), wr, ww, tyre, 12, cap_color=hub)
        return m

    # --- per-frame -----------------------------------------------------------------
    def resize(self, size):
        self.size = size

    def _camera_for(self, kart, t):
        cam = self.cams.get(id(kart))
        if cam is None:
            cam = self.cams[id(kart)] = {"h": kart.heading, "x": kart.x, "y": kart.y}
        dt = 0.0 if self.last_time is None else max(0.0, min(0.1, t - self.last_time))
        diff = (kart.heading - cam["h"] + math.pi) % (2 * math.pi) - math.pi
        cam["h"] += diff * min(1.0, dt * 5.0)
        cam["x"] += (kart.x - cam["x"]) * min(1.0, dt * 14.0)
        cam["y"] += (kart.y - cam["y"]) * min(1.0, dt * 14.0)
        fx, fz = math.cos(cam["h"]), math.sin(cam["h"])
        eye = (cam["x"] - fx * 150, 74.0, cam["y"] - fz * 150)
        target = (cam["x"] + fx * 70, 16.0, cam["y"] + fz * 70)
        return eye, target

    def _orbit_camera(self, t):
        W, H = self.world
        a = t * 0.08
        eye = (W / 2 + math.cos(a) * 1700, 820.0, H / 2 + math.sin(a) * 1350)
        return eye, (W / 2, 0.0, H / 2)

    def _viewport(self, rect):
        """Layout rect (1280x720 HUD space) -> GL viewport in window pixels."""
        sx, sy = self.size[0] / 1280, self.size[1] / 720
        x, y, w, h = rect
        return (round(x * sx), round(self.size[1] - (y + h) * sy), round(w * sx), round(h * sy))

    def _draw_scene(self, game, eye, target, viewport, focus=None, fog=FOG):
        ctx = self.ctx
        vx, vy, vw, vh = viewport
        self.fbo.viewport = viewport
        self.fbo.scissor = viewport
        ctx.clear(*SKY_HORIZON, 1.0, depth=1.0)
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.sky_vao.render(moderngl.TRIANGLE_STRIP)
        aspect = vw / max(1, vh)
        proj = perspective(64 if aspect > 1.2 else 74, aspect, 8.0, 12000.0)
        vp = matmul(proj, look_at(eye, target))
        vpb = pack(vp)
        for prog in (self.mesh_prog, self.ground_prog, self.sprite_prog):
            prog["u_fog"].value = fog

        ctx.enable(moderngl.DEPTH_TEST)
        self.ground_prog["u_vp"].write(vpb)
        self.ground_prog["u_cam"].value = eye
        self.ground_tex.use(0)
        self.ground_vao.render()

        mp = self.mesh_prog
        mp["u_vp"].write(vpb)
        mp["u_cam"].value = eye

        def draw_mesh(vao, model, outline):
            mp["u_model"].write(pack(model))
            ctx.enable(moderngl.CULL_FACE)
            ctx.cull_face = "front"          # ink outline: inflated back faces
            mp["u_ink"].value = 1
            mp["u_outline"].value = outline
            vao.render()
            ctx.cull_face = "back"
            mp["u_ink"].value = 0
            mp["u_outline"].value = 0.0
            vao.render()

        draw_mesh(self.scenery_vao, IDENTITY, 1.8)
        t = game.time
        # Karts right in front of the lens would block your view of your own kart: hide them.
        karts = [k for k in game.karts
                 if k is focus or (k.x - eye[0]) ** 2 + (k.y - eye[2]) ** 2 > 105 ** 2]
        for k in karts:
            speed = min(1.0, abs(k.forward_speed) / 400)
            steer = getattr(k, "steer_input", 0.0)
            bob = math.sin(t * 22 + k.x * 0.05) * 0.6 * speed
            roll = steer * 0.14 * speed       # lean into the turn
            yaw = steer * 0.38 if k.drifting else 0.0
            draw_mesh(self.kart_vaos[id(k.character)], kart_matrix(k.x, bob, k.y, k.heading, roll, yaw), 1.0)
        ctx.disable(moderngl.CULL_FACE)

        # Sprites: blob shadows (flat), riders and tags (upright cut-outs), particles.
        right = _norm(_cross(_norm(_sub(target, eye)), (0, 1, 0)))
        sp = self.sprite_prog
        sp["u_vp"].write(vpb)
        sp["u_cam"].value = eye
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        verts = array("f")
        for k in karts:
            self._flat_quad(verts, k.x + 4, 0.6, k.y + 4, 36, (1, 1, 1, 1))
        self.fbo.depth_mask = False
        sp["u_cutout"].value = 0.01
        self._draw_sprites(verts, self.shadow_tex)
        self.prop_shadow_vao.render()
        self.fbo.depth_mask = True

        sp["u_cutout"].value = 0.5
        for k in karts:
            if k.character.style != "rider":
                continue
            verts = array("f")
            bob = math.sin(t * 9 + k.x * 0.01) * 1.5 * min(1.0, abs(k.forward_speed) / 200)
            self._upright_quad(verts, (k.x - math.cos(k.heading) * 4, 40 + bob, k.y - math.sin(k.heading) * 4), right, 46, 46,
                               (1, 1, 1, 1))
            self._draw_sprites(verts, self.rider_tex[id(k.character)])

        # Particles (stars, puffs, sparkles), batched by texture.
        stars, blobs = array("f"), array("f")
        for p in game.particles:
            if (p.x - eye[0]) ** 2 + (p.y - eye[2]) ** 2 > 2200 ** 2:
                continue
            life = p.life / p.max_life
            if p.puff:
                size = p.size * (1.0 + 1.4 * (1 - life)) * 2.2
                height = 18 + (1 - life) * 22
            else:
                size = p.size * (0.4 + 0.6 * life) * (3.2 if p.star else 1.1)
                height = 10 + (1 - life) * 14
            col = (p.color[0] / 255, p.color[1] / 255, p.color[2] / 255, 1.0)
            self._upright_quad(stars if p.star else blobs, (p.x, height, p.y), right, size, size, col)
        sp["u_cutout"].value = 0.3
        self._draw_sprites(blobs, self.circle_tex)
        self._draw_sprites(stars, self.star_tex)

        # Other players' tags: crisp, fixed-size labels so you can always spot your friends.
        if len(game.humans) > 1:
            ctx.disable(moderngl.DEPTH_TEST)
            sp["u_vp"].write(pack(IDENTITY))
            sp["u_cam"].value = (0.0, 0.0, -100000.0)
            sp["u_fog"].value = (1e9, 2e9)
            scale = self.size[1] / 720
            for k in game.humans:
                if k is focus or k.tag is None:
                    continue
                top = 70 if k.character.style == "rider" else 44
                cx, cy, cz, cw = (sum(vp[r][c] * v for c, v in enumerate((k.x, top, k.y, 1.0))) for r in range(4))
                if cw <= 1.0:
                    continue  # behind the camera
                nx, ny = cx / cw, cy / cw
                if abs(nx) > 1.2 or abs(ny) > 1.2:
                    continue
                tex = self.tag_tex.get(id(k))
                if tex is None:
                    tex = self.tag_tex[id(k)] = _sprite_texture(ctx, k.tag)
                w, h = k.tag.get_size()
                hw, hh = w * scale / vw, h * scale / vh   # NDC half-size for the tag's real pixel size
                verts = array("f")
                for px, py, u, v in ((nx - hw, ny, 0, 1), (nx + hw, ny, 1, 1), (nx + hw, ny + 2 * hh, 1, 0),
                                     (nx - hw, ny, 0, 1), (nx + hw, ny + 2 * hh, 1, 0), (nx - hw, ny + 2 * hh, 0, 0)):
                    verts.extend((px, py, 0.0, u, v, 1.0, 1.0, 1.0, 1.0))
                self._draw_sprites(verts, tex)
            ctx.enable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.BLEND)

    @staticmethod
    def _flat_quad(verts, x, y, z, size, col):
        h = size / 2
        pts = [(x - h, z - h, 0, 0), (x + h, z - h, 1, 0), (x + h, z + h, 1, 1),
               (x - h, z - h, 0, 0), (x + h, z + h, 1, 1), (x - h, z + h, 0, 1)]
        for px, pz, u, v in pts:
            verts.extend((px, y, pz, u, v))
            verts.extend(col)

    @staticmethod
    def _upright_quad(verts, center, right, w, h, col):
        cx, cy, cz = center
        rx, rz = right[0] * w / 2, right[2] * w / 2
        bl = (cx - rx, cy - h / 2, cz - rz, 0, 1)
        br = (cx + rx, cy - h / 2, cz + rz, 1, 1)
        tr = (cx + rx, cy + h / 2, cz + rz, 1, 0)
        tl = (cx - rx, cy + h / 2, cz - rz, 0, 0)
        for v in (bl, br, tr, bl, tr, tl):
            verts.extend(v)
            verts.extend(col)

    def _draw_sprites(self, verts, tex):
        if not verts:
            return
        n = len(verts) // 9
        data = verts.tobytes()
        if len(data) > self.sprite_buf.size:
            self.sprite_buf.orphan(len(data))
        self.sprite_buf.write(data)
        tex.use(0)
        self.sprite_vao.render(moderngl.TRIANGLES, vertices=n)

    def render(self, game, overlay_surface, views):
        """Draw the 3D views, then the HUD/menu layer on top.

        `views` is a list of (layout_rect, kart) in 1280x720 HUD space, or [] for the menu flyover."""
        ctx = self.ctx
        self.fbo.use()
        self.fbo.scissor = None
        self.fbo.viewport = (0, 0, *self.size)
        ctx.clear(0.04, 0.03, 0.08, 1.0)
        if views:
            for rect, kart in views:
                eye, target = self._camera_for(kart, game.time)
                self._draw_scene(game, eye, target, self._viewport(rect), kart)
        else:
            eye, target = self._orbit_camera(game.time)
            self._draw_scene(game, eye, target, (0, 0, *self.size), fog=(2600.0, 7000.0))
        self.last_time = game.time
        self.fbo.scissor = None
        self.fbo.viewport = (0, 0, *self.size)
        self._draw_overlay(overlay_surface)

    def show_overlay(self, overlay_surface):
        """Just the 2D layer (used for the loading screen)."""
        self.fbo.use()
        self.fbo.scissor = None
        self.fbo.viewport = (0, 0, *self.size)
        self.ctx.clear(0.16, 0.08, 0.24, 1.0)
        self._draw_overlay(overlay_surface)

    def _draw_overlay(self, overlay_surface):
        ctx = self.ctx
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        surf = overlay_surface
        fast = (surf.get_masks() == (0xFF0000, 0xFF00, 0xFF, 0xFF000000)
                and surf.get_pitch() == surf.get_width() * 4)
        if self.overlay_tex is None or self.overlay_tex.size != surf.get_size():
            self.overlay_tex = self.ctx.texture(surf.get_size(), 4)
            self.overlay_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            if fast:
                self.overlay_tex.swizzle = "BGRA"  # upload pygame's pixels as-is; the GPU swaps channels
        self.overlay_tex.write(surf.get_view("2") if fast else pygame.image.tobytes(surf, "RGBA"))
        self.overlay_tex.use(0)
        self.overlay_vao.render(moderngl.TRIANGLE_STRIP)
        ctx.disable(moderngl.BLEND)

    def snapshot(self):
        """The last rendered frame as a pygame Surface (for tests / screenshots)."""
        data = self.fbo.read(components=3)
        return pygame.transform.flip(pygame.image.frombytes(data, self.size, "RGB"), False, True)
