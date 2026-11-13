"""Shred: build and render one shot in Blender (tested with 5.2). kit.py drives it; by hand:

    blender -b -P scripts/shred.py -- --shot C --out build/renders/draft --scale 50 --samples 16 --subs 3 [--frames 0,100 | 0-215 | all]

Shots (60 fps, frames local to the shot):
    H   0-29    hook: the finished poster, readable in frame 0, bursts into sliding strips (loops from C)
    A   0-111   cascade of shredder ribbons, stacked without passing through each other; a hero ribbon carries the headline
    F   0-83    the shredder: the poster comes down into the cutter discs bottom-first and is cut into 26 lanes (inset)
    O   0-71    under the cutters: the curtain of strips curls out, alternate lanes towards and away (inset)
    FO  0-122   F into O in one camera move: rush in, the bite, dive under the cutters into the curtain (inset)
    C   0-215   the poster rebuilt: scrambled strips coast in and land in a wave, top to bottom, click, hold

Every shot maps build/tex/poster.png (scripts/poster.py draws it from brief.json). In C, H and A the print slides inside a strip through a UV offset read from
the strip's "off" property (Attribute node, Object); in F and O the UVs are rewritten each (sub)frame from
the length of paper fed. All motion is a function of time, evaluated in update(f) with a float frame, so
--subs N renders N sub-frames across the shutter and averages them: true motion blur for everything.
"""
import sys, os, math, argparse, time
import numpy as np
import bpy
import bmesh
from mathutils import Vector, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import brief as BRIEF

_br = BRIEF.load()
_pl = BRIEF.lin(_br['colors']['paper'])
PAPER_LIFT = tuple(c * (0.862 - 0.045) + 0.045 for c in _pl)     # the paper's albedo, as the print shader lifts it
FPS = 60
POSTER_W, POSTER_H = 2.0, 3.0
INSET = (844, 1500)


def args():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--shot', default='C')
    p.add_argument('--out', default='build/renders/look')
    p.add_argument('--scale', type=int, default=100)
    p.add_argument('--samples', type=int, default=16)
    p.add_argument('--subs', type=int, default=1)
    p.add_argument('--shutter', type=float, default=0.5)     # in frames (0.5 = 180 degrees)
    p.add_argument('--frames', default='0')
    p.add_argument('--save', default='')
    p.add_argument('--expo', type=float, default=None)
    return p.parse_args(a)


# ---------------------------------------------------------------- easing / noise

def sease(u, p=3.0):
    u = min(1.0, max(0.0, u))
    return u ** p / (u ** p + (1 - u) ** p)


def spring_tail(s, amp, tau=0.06, period=0.16):
    """Damped return after an overshoot of size amp at s=0 (seconds); zero slope at s=0."""
    if s <= 0:
        return -amp
    w = 2 * math.pi / period
    return -amp * math.exp(-s / tau) * (math.cos(w * s) + math.sin(w * s) / (tau * w))


def smooth_field(rng, ny, nx, sy, sx):
    """Gaussian-smoothed random field via FFT, unit std."""
    f = rng.normal(0, 1, (ny, nx))
    ky = np.fft.fftfreq(ny)[:, None]
    kx = np.fft.fftfreq(nx)[None, :]
    g = np.exp(-2 * (math.pi ** 2) * ((ky * sy) ** 2 + (kx * sx) ** 2))
    r = np.real(np.fft.ifft2(np.fft.fft2(f) * g))
    return r / (r.std() + 1e-9)


def smooth_1d(rng, n, s):
    return smooth_field(rng, 1, n, 1, s)[0]


def crease_field(rng, X, Y, n, amp, across=True, sharp=0.003, spread=0.45):
    """Crumpled paper: a sum of sharp folds (|d| along random lines), net tilt removed.
    Facets stay flat between folds, so the light breaks on crisp lines like real paper."""
    z = np.zeros_like(X)
    xr, yr = (X.min(), X.max()), (Y.min(), Y.max())
    for _ in range(n):
        ang = rng.normal(0, spread) if across else rng.uniform(0, math.pi)
        c, s = math.cos(ang), math.sin(ang)
        px, py = rng.uniform(*xr), rng.uniform(*yr)
        d = (X - px) * c + (Y - py) * s
        z += rng.choice([-1, 1]) * rng.uniform(0.4, 1.0) * np.sqrt(d * d + sharp * sharp)
    A = np.stack([X.ravel(), Y.ravel(), np.ones(X.size)], 1)
    coef = np.linalg.lstsq(A, z.ravel(), rcond=None)[0]
    z = z - (A @ coef).reshape(z.shape)
    return z / (np.abs(z).max() + 1e-9) * amp


def shake(t, seed, amp):
    """Hand-held drift: a few incommensurate sines, smooth and bounded."""
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 6.28, 6)
    return amp * (np.sin(2 * math.pi * 1.3 * t + ph[0]) * 0.6 + np.sin(2 * math.pi * 2.9 * t + ph[1]) * 0.3
                  + np.sin(2 * math.pi * 5.3 * t + ph[2]) * 0.1)


# ---------------------------------------------------------------- scene basics

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    kind = None
    for k in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):     # the first GPU backend that has a device
        try:
            prefs.compute_device_type = k
        except TypeError:
            continue
        prefs.get_devices()
        if any(d.type == k for d in prefs.devices):
            kind = k
            break
    if kind:
        for d in prefs.devices:
            d.use = d.type == kind
        sc.cycles.device = 'GPU'
    else:
        sc.cycles.device = 'CPU'
    print('device', kind or 'CPU', flush=True)
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPTIX' if kind == 'OPTIX' else 'OPENIMAGEDENOISE'
    sc.render.use_persistent_data = True
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
    sc.render.fps = FPS
    sc.view_settings.view_transform = 'Khronos PBR Neutral'
    sc.view_settings.look = 'None'
    sc.render.image_settings.file_format = 'JPEG'
    sc.render.image_settings.quality = 94
    w = bpy.data.worlds.new('World')
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.8, 0.81, 0.83, 1)
    bg.inputs[1].default_value = 0.3
    return sc


def poster_image(name='poster.png'):
    return bpy.data.images.load(os.path.join(ROOT, 'build', 'tex', name), check_existing=True)


def _math(N, L, op, a, b=None, c=None, vec=False):
    n = N.new('ShaderNodeVectorMath' if vec else 'ShaderNodeMath')
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, bpy.types.NodeSocket):
            L.new(v, n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n.outputs[0]


def paper_material(name='paper', bump=0.3, rough=0.36, backprint=0.16, trans=0.08, ink_rough=0.18, spec=0.55,
                   fibre=0.3, ink=0.022, side=None, slide='X', image='poster.png'):
    """Paper: print lifted off pure black (ink = albedo of solid black), roughness from ink_rough on ink to rough
    on paper, fibre + cockle bump that travels with the print and is weaker on ink, a light back with the print
    faintly showing through, some translucency.
    side='back' always shows the back (for the shell of a solidified strip, whose back faces point outward).
    slide: which print axis the object's "off" property shifts ('X', 'Y' or None)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new('ShaderNodeOutputMaterial')
    bsdf = N.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Specular IOR Level'].default_value = spec
    bsdf.inputs['Sheen Weight'].default_value = 0.05
    bsdf.inputs['Sheen Roughness'].default_value = 0.5
    uv = N.new('ShaderNodeUVMap')
    sep = N.new('ShaderNodeSeparateXYZ')
    comb = N.new('ShaderNodeCombineXYZ')
    tex = N.new('ShaderNodeTexImage')
    tex.image = poster_image(image)
    tex.extension = 'REPEAT'
    tex.interpolation = 'Cubic'
    L.new(uv.outputs['UV'], sep.inputs[0])
    if slide:
        att = N.new('ShaderNodeAttribute')
        att.attribute_type = 'OBJECT'
        att.attribute_name = 'off'
        ax = 'X' if slide == 'X' else 'Y'
        other = 'Y' if slide == 'X' else 'X'
        L.new(_math(N, L, 'ADD', sep.outputs[ax], att.outputs['Fac']), comb.inputs[ax])
        L.new(sep.outputs[other], comb.inputs[other])
    else:
        L.new(sep.outputs['X'], comb.inputs['X'])
        L.new(sep.outputs['Y'], comb.inputs['Y'])
    L.new(comb.outputs[0], tex.inputs['Vector'])
    col = tex.outputs['Color']
    lift = _math(N, L, 'MULTIPLY_ADD', col, (0.862 - ink,) * 3, (ink, ink * 0.96, ink * 0.92), vec=True)
    lumn = N.new('ShaderNodeRGBToBW')
    L.new(col, lumn.inputs[0])
    lum = lumn.outputs[0]
    if side == 'back':
        backf = 1.0
    else:
        geo = N.new('ShaderNodeNewGeometry')
        backf = geo.outputs['Backfacing']
    paper = tuple(c * 0.95 * (1 - backprint) for c in PAPER_LIFT)
    back = _math(N, L, 'MULTIPLY_ADD', lift, (backprint,) * 3, paper, vec=True)
    diff = _math(N, L, 'SUBTRACT', back, lift, vec=True)
    base = _math(N, L, 'MULTIPLY_ADD', diff, (backf,) * 3 if side == 'back' else backf, lift, vec=True)
    L.new(base, bsdf.inputs['Base Color'])
    rf = _math(N, L, 'MULTIPLY_ADD', lum, rough - ink_rough, ink_rough)
    L.new(_math(N, L, 'MULTIPLY_ADD', backf, 0.15, rf), bsdf.inputs['Roughness'])
    # fibre (fine, stretched along the grain) + cockle (soft), on print coordinates
    v1 = _math(N, L, 'MULTIPLY', comb.outputs[0], (POSTER_W * 70, POSTER_H * 55, 1), vec=True)
    n1 = N.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 1.0
    n1.inputs['Detail'].default_value = 5
    L.new(v1, n1.inputs['Vector'])
    v2 = _math(N, L, 'MULTIPLY', comb.outputs[0], (POSTER_W * 5, POSTER_H * 5, 1), vec=True)
    n2 = N.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 1.0
    n2.inputs['Detail'].default_value = 3
    L.new(v2, n2.inputs['Vector'])
    h = _math(N, L, 'MULTIPLY_ADD', n1.outputs['Fac'], fibre, _math(N, L, 'MULTIPLY', n2.outputs['Fac'], 0.6))
    bmp = N.new('ShaderNodeBump')
    bmp.inputs['Distance'].default_value = 0.01
    L.new(_math(N, L, 'MULTIPLY', _math(N, L, 'MULTIPLY_ADD', lum, 0.65, 0.35), bump), bmp.inputs['Strength'])
    L.new(h, bmp.inputs['Height'])
    L.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
    tr = N.new('ShaderNodeBsdfTranslucent')
    L.new(base, tr.inputs['Color'])
    L.new(bmp.outputs['Normal'], tr.inputs['Normal'])
    mix = N.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = trans
    L.new(bsdf.outputs[0], mix.inputs[1])
    L.new(tr.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs['Surface'])
    return m


def edge_material(name='paper_edge'):
    """Cut edge of a sheet: bare paper core, matte, light, translucent (ink sits only on the surface)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N['Principled BSDF']
    b.inputs['Base Color'].default_value = (*PAPER_LIFT, 1)
    b.inputs['Roughness'].default_value = 0.8
    b.inputs['Specular IOR Level'].default_value = 0.3
    tr = N.new('ShaderNodeBsdfTranslucent')
    tr.inputs['Color'].default_value = (*PAPER_LIFT, 1)
    mix = N.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = 0.3
    L.new(b.outputs[0], mix.inputs[1])
    L.new(tr.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], N['Material Output'].inputs['Surface'])
    return m


def paper_set(name, **kw):
    """Front, back and edge materials for a solidified paper strip."""
    return (paper_material(name, **kw), paper_material(name + '_back', side='back', **kw), edge_material(name + '_edge'))


def steel_material(name, col=(0.56, 0.56, 0.58), rough=0.24, aniso=0.75, rings=900, grime=0.35):
    """Machined steel: metallic, anisotropic around the object's X axis (turned/ground discs), fine concentric
    grooves as bump, roughness and a little grime varying with object-space noise."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N['Principled BSDF']
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Anisotropic'].default_value = aniso
    tg = N.new('ShaderNodeTangent')
    tg.direction_type = 'RADIAL'
    tg.axis = 'X'
    L.new(tg.outputs['Tangent'], b.inputs['Tangent'])
    tc = N.new('ShaderNodeTexCoord')
    n1 = N.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 14
    n1.inputs['Detail'].default_value = 6
    L.new(tc.outputs['Object'], n1.inputs['Vector'])
    L.new(_math(N, L, 'MULTIPLY_ADD', n1.outputs['Fac'], 0.22, rough - 0.11), b.inputs['Roughness'])
    n2 = N.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 5
    n2.inputs['Detail'].default_value = 4
    L.new(tc.outputs['Object'], n2.inputs['Vector'])
    dirt = _math(N, L, 'MULTIPLY_ADD', _math(N, L, 'SMOOTH_MIN', n2.outputs['Fac'], 0.62, 0.1), -grime * 1.6, 1 + grime * 0.6)
    tint = _math(N, L, 'SCALE', col, None, None, vec=True)
    tint.node.inputs['Scale'].default_value = 1.0
    L.new(dirt, tint.node.inputs['Scale'])
    L.new(tint, b.inputs['Base Color'])
    w = N.new('ShaderNodeTexWave')
    w.wave_type = 'RINGS'
    w.rings_direction = 'X'
    w.inputs['Scale'].default_value = rings
    w.inputs['Distortion'].default_value = 0.6
    w.inputs['Detail'].default_value = 1.5
    L.new(tc.outputs['Object'], w.inputs['Vector'])
    bmp = N.new('ShaderNodeBump')
    bmp.inputs['Strength'].default_value = 0.06
    bmp.inputs['Distance'].default_value = 0.0005
    L.new(w.outputs['Fac'], bmp.inputs['Height'])
    L.new(bmp.outputs['Normal'], b.inputs['Normal'])
    return m


def plastic_material(name, col=(0.028, 0.028, 0.03), rough=0.42):
    """Glass-filled black nylon: dark, satin, faint mottling."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1)
    b.inputs['Specular IOR Level'].default_value = 0.45
    tc = N.new('ShaderNodeTexCoord')
    n1 = N.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 40
    n1.inputs['Detail'].default_value = 6
    L.new(tc.outputs['Object'], n1.inputs['Vector'])
    L.new(_math(N, L, 'MULTIPLY_ADD', n1.outputs['Fac'], 0.16, rough - 0.08), b.inputs['Roughness'])
    bmp = N.new('ShaderNodeBump')
    bmp.inputs['Strength'].default_value = 0.08
    L.new(n1.outputs['Fac'], bmp.inputs['Height'])
    L.new(bmp.outputs['Normal'], b.inputs['Normal'])
    return m


def concrete_material(lo=0.20, hi=0.34, relief=0.35):
    """Poured concrete: soft blotches, mid mottling, small pits, fine grit."""
    m = bpy.data.materials.new('concrete')
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.88
    tc = N.new('ShaderNodeTexCoord')
    n1 = N.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 0.35
    n1.inputs['Detail'].default_value = 4
    L.new(tc.outputs['Object'], n1.inputs['Vector'])
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (lo, lo * 1.01, lo * 1.02, 1)
    ramp.color_ramp.elements[1].color = (hi, hi * 1.005, hi * 1.01, 1)
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[1].position = 0.72
    L.new(n1.outputs['Fac'], ramp.inputs[0])
    n2 = N.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 5.0
    n2.inputs['Detail'].default_value = 8
    L.new(tc.outputs['Object'], n2.inputs['Vector'])
    mott = _math(N, L, 'MULTIPLY_ADD', n2.outputs['Fac'], 0.22, 0.89)
    vor = N.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = 70
    L.new(tc.outputs['Object'], vor.inputs['Vector'])
    pits = _math(N, L, 'GREATER_THAN', vor.outputs['Distance'], 0.09)        # 0 in a pit
    shade = _math(N, L, 'MULTIPLY', mott, _math(N, L, 'MULTIPLY_ADD', pits, 0.3, 0.7))
    L.new(_math(N, L, 'SCALE', ramp.outputs['Color'], None, None, vec=True), bsdf.inputs['Base Color'])
    sc_node = bsdf.inputs['Base Color'].links[0].from_node
    L.new(shade, sc_node.inputs['Scale'])
    n3 = N.new('ShaderNodeTexNoise')
    n3.inputs['Scale'].default_value = 160
    n3.inputs['Detail'].default_value = 6
    L.new(tc.outputs['Object'], n3.inputs['Vector'])
    bmp = N.new('ShaderNodeBump')
    bmp.inputs['Strength'].default_value = relief
    bmp.inputs['Distance'].default_value = 0.004
    L.new(_math(N, L, 'MULTIPLY_ADD', pits, 0.5, n3.outputs['Fac']), bmp.inputs['Height'])
    L.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def floor_material(lo=0.34, hi=0.44):
    m = bpy.data.materials.new('floor')
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.8
    n1 = N.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 1.2
    n1.inputs['Detail'].default_value = 8
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (lo, lo, lo * 1.01, 1)
    ramp.color_ramp.elements[1].color = (hi, hi, hi * 1.005, 1)
    L.new(n1.outputs['Fac'], ramp.inputs[0])
    L.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    n2 = N.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 90
    bmp = N.new('ShaderNodeBump')
    bmp.inputs['Strength'].default_value = 0.15
    L.new(n2.outputs['Fac'], bmp.inputs['Height'])
    L.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def add_plane(name, mat, x0, y0, x1, y1, z=0.0):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    ob.data.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def grid_faces(ny, nx):
    idx = np.arange((ny + 1) * (nx + 1)).reshape(ny + 1, nx + 1)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    return np.stack([a, b, c, d], -1).reshape(-1, 4)


def make_mesh(name, verts, faces, U, V, mat=None, link=True, solid=0.0, crisp=False):
    """mat is a material, or a (front, back, edge) set from paper_set: then the solidify shell gets the back
    and the rim the bare-paper edge. crisp splits normals at the rim so the edge reads as a cut, not a bead."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces.tolist())
    uvl = me.uv_layers.new(name='UVMap')
    loop_uv = np.stack([U.reshape(-1), V.reshape(-1)], -1)[faces.reshape(-1)]
    uvl.data.foreach_set('uv', loop_uv.reshape(-1))
    me.polygons.foreach_set('use_smooth', [True] * len(faces))
    mats = mat if isinstance(mat, tuple) else ((mat,) if mat else ())
    for mm in mats:
        me.materials.append(mm)
    ob = bpy.data.objects.new(name, me)
    if link:
        bpy.context.scene.collection.objects.link(ob)
    if solid > 0:
        md = ob.modifiers.new('thick', 'SOLIDIFY')
        md.thickness = solid
        md.offset = -1
        if len(mats) == 3:
            md.material_offset = 1
            md.material_offset_rim = 2
        if crisp:
            es = ob.modifiers.new('crisp', 'EDGE_SPLIT')
            es.split_angle = math.radians(40)
            es.use_edge_sharp = False
    ob['off'] = 0.0
    return ob


def set_uv(ob, U, V, faces):
    ob.data.uv_layers[0].data.foreach_set('uv', np.stack([U.reshape(-1), V.reshape(-1)], -1)[faces.reshape(-1)].reshape(-1))


def strip_geom(rng, w, h, nx, ny, edge=0.0035):
    """XY grid for a strip w x h centred at 0, edge rows jittered (cutter wobble + fibre)."""
    xs = np.linspace(-w / 2, w / 2, nx + 1)
    ys = np.linspace(-h / 2, h / 2, ny + 1)
    X, Y = np.meshgrid(xs, ys)
    if edge:
        for row, sgn in ((0, -1), (ny, 1)):
            j = smooth_1d(rng, nx + 1, 10) * edge + rng.normal(0, edge * 0.3, nx + 1)
            Y[row] += sgn * np.abs(j) * 0.5 + j * 0.5
    return X, Y


def area_light(name, loc, target, size, power, color=(1, 1, 1), spread=None, size_y=None):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.size = size
    if size_y:
        ld.shape = 'RECTANGLE'
        ld.size_y = size_y
    ld.energy = power
    ld.color = color
    if spread:
        ld.spread = spread
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob


def persp_camera(sc, lens, fstop=None, focus=None):
    cd = bpy.data.cameras.new('cam')
    cd.lens = lens
    cd.sensor_fit = 'VERTICAL'
    cd.sensor_height = 24
    cam = bpy.data.objects.new('cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_distance = focus
    return cam


def look_at(ob, loc, target, roll=0.0):
    ob.location = loc
    q = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y')
    ob.rotation_euler = (q.to_matrix().to_4x4() @ Matrix.Rotation(roll, 4, 'Z')).to_euler()


def set_off(ob, v):
    ob['off'] = float(v)
    ob.update_tag()


# ---------------------------------------------------------------- the poster (shots C and H)

POSTER_Z = 0.035
C_END_SCALE = 4.7           # poster ~76 % of the frame width at the end of C / start of H
C_START_SCALE = 5.0
CAM_Y0 = -0.30              # poster sits ~115 px above centre: clear of the Reels caption and buttons
PUSH = 0.05                 # ortho units/s: a slow push that runs through C's hold into H, so the loop never parks
KEY_END = ((-3.4, 3.6, 5.2), (0.2, -0.3, 0.0))
KEY_START = ((-5.2, 0.4, 4.2), (-0.5, -1.1, 0.0))


def build_poster(sc, seed=11):
    """26 horizontal strips of the poster on concrete. Same seed -> identical poster in C and H, so C's last
    frame is H's first and the reel loops without a seam."""
    rng = np.random.default_rng(seed)
    add_plane('concrete', concrete_material(0.17, 0.36, relief=0.5), -8, -10, 8, 10)
    mat = paper_set('paper_C', bump=0.16, rough=0.6, ink_rough=0.44, spec=0.32, fibre=0.0, ink=0.045, trans=0.24)
    NS = 26
    bands = np.linspace(0, 1, NS + 1)
    bands[1:-1] += rng.normal(0, 0.22, NS - 1) / NS          # unequal widths, about +-20 %
    strips = []
    for i in range(NS):
        v0, v1 = bands[i], bands[i + 1]
        h = (v1 - v0) * POSTER_H
        nx, ny = 360, 14
        X, Y = strip_geom(rng, POSTER_W * rng.uniform(0.995, 1.005), h * 1.004, nx, ny)
        crumple = 1.0 if i >= 2 else 2.4
        z = crease_field(rng, X, Y, int(10 * crumple), 0.005 * crumple, across=True)
        z += smooth_field(rng, ny + 1, nx + 1, 30, 70) * 0.007                       # slow bow
        z += smooth_field(rng, ny + 1, nx + 1, 1.2, 2.0) * 0.00045 * crumple           # small crinkle
        z += (np.linspace(-1, 1, ny + 1)[:, None] ** 2) * 0.008 * rng.uniform(0.3, 1.0)   # edges lift
        z -= z.min()
        U = (X + POSTER_W / 2) / POSTER_W
        V = v0 + (Y + h / 2) / h * (v1 - v0)
        ob = make_mesh(f'strip{i:02d}', np.stack([X, Y, z], -1).reshape(-1, 3), grid_faces(ny, nx), U, V, mat,
                       solid=0.0025, crisp=True)
        y = -POSTER_H / 2 + (v0 + v1) / 2 * POSTER_H
        base = (rng.normal(0, 0.006), y + rng.normal(0, 0.002), POSTER_Z + 0.004 * rng.random())
        ob.location = base
        ob.rotation_euler = (rng.normal(0, 0.015), 0, rng.normal(0, 0.002))
        ob['base'] = base
        ob['rot'] = tuple(ob.rotation_euler)
        strips.append(ob)
    # one big soft key from the upper left with a narrowed spread: a pool of light, darker corners
    area_light('key', KEY_END[0], KEY_END[1], 3.2, 1500, (1.0, 0.975, 0.94), spread=math.radians(68))
    area_light('fill', (4, -3, 7), (0, 0, 0), 8, 45, (0.9, 0.93, 1.0))
    cd = bpy.data.cameras.new('cam')
    cd.type = 'ORTHO'
    cd.ortho_scale = C_END_SCALE
    cam = bpy.data.objects.new('cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, CAM_Y0, 10)
    sc.view_settings.exposure = -3.2              # matte stock reads light under the neutral view transform
    return strips, rng, cam


def c_scale(f, n=216):
    """C's ortho scale: eases in from C_START_SCALE, then keeps pushing at PUSH through the hold, so frame n is
    exactly H's frame 0 (C_END_SCALE) with the same speed."""
    base = C_END_SCALE + PUSH * (n - f) / FPS
    k = 1 - sease(min(1.0, f / (n - 20)), 1.6)
    return base + (C_START_SCALE - C_END_SCALE - PUSH * n / FPS) * k


def shot_C(sc):
    n = 216
    strips, rng, cam = build_poster(sc)
    NS = len(strips)
    hold_t = (n - 20) / FPS
    plan = []
    for i, ob in enumerate(strips):
        k = NS - 1 - i                                 # top strip lands first
        x = k / (NS - 1)
        # neighbours start on opposite sides more often than not, so the strips shear past each other
        side = (1 if k % 2 else -1) * (1 if rng.uniform() < 0.8 else -1)
        o0 = side * rng.uniform(0.35, 1.0)
        o1 = o0 * rng.uniform(0.12, 0.4)
        t2 = 0.5 + 2.1 * (1 - (1 - x) ** 1.6) + rng.normal(0, 0.025)    # the wave bunches up: accelerating
        d2 = 0.62 - 0.30 * x
        t1 = rng.uniform(-0.5, -0.15)                  # every strip is already sliding at the cut
        tc = 0.35 + 0.45 * (t2 - 0.5)                  # and keeps coasting until its own landing: no freeze
        plan.append(dict(o0=o0, o1=o1, t1=t1, tc=tc, t2=t2, d2=d2, lift=0.0))
    for i in rng.choice(NS, 3, replace=False):
        plan[i]['lift'] = rng.uniform(0.04, 0.07)
    import json
    key = bpy.data.objects['key']
    t_last = max(p['t2'] + p['d2'] for p in plan)
    gl = area_light('glint', (0.0, 2.6, 2.4), (0.0, 1.6, 0.0), 1.4, 0.0, (1.0, 0.98, 0.95))
    lands = sorted(round((p['t2'] + p['d2']) * FPS, 1) for p in plan)
    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    with open(os.path.join(ROOT, 'build', 'c_lands.json'), 'w') as fh:
        json.dump({'land_frames': lands, 'hold_from': n - 20}, fh)

    def strip_off(p, t):
        a = p['o1'] + (p['o0'] - p['o1']) * math.exp(-max(0.0, t - p['t1']) / p['tc'])
        tau = (t - p['t2']) / p['d2']
        ov = 0.03
        if tau < 1:
            r = 1 - (1 + ov) * sease(tau, 3.0)
        else:
            r = spring_tail(t - p['t2'] - p['d2'], ov)
        return a * r

    def update(f):
        t = f / FPS
        for i, (ob, p) in enumerate(zip(strips, plan)):
            if t >= hold_t:
                v = 0.0
            else:
                v = strip_off(p, t)
                for j in (i - 1, i + 1):                           # neighbours shiver when a strip lands
                    if 0 <= j < NS:
                        q = plan[j]
                        s = t - q['t2'] - q['d2']
                        if s > 0:
                            v += 0.005 * math.copysign(1, q['o1']) * math.exp(-s / 0.07) * math.sin(2 * math.pi * s / 0.11)
            set_off(ob, v)
            b, r = ob['base'], ob['rot']
            tau = (t - p['t2']) / p['d2']
            lift = p['lift'] * math.sin(math.pi * min(1, max(0, tau))) if t < hold_t else 0.0
            ob.location = (b[0], b[1], b[2] + lift)
            ob.rotation_euler = (r[0] + lift * 2.2, r[1], r[2])
        cam.data.ortho_scale = c_scale(f, n)
        # the pool of key light drifts up the poster while it assembles and settles with the last strip
        u = sease(min(1.0, t / t_last), 1.8)
        kl = [a + (b - a) * u for a, b in zip(KEY_START[0], KEY_END[0])]
        kt = [a + (b - a) * u for a, b in zip(KEY_START[1], KEY_END[1])]
        key.location = kl
        key.rotation_euler = (Vector(kt) - Vector(kl)).to_track_quat('-Z', 'Y').to_euler()
        # after the final click a soft light passes down the poster once
        g = (t - t_last - 0.03) / 0.42
        y = 2.6 - 5.4 * min(1.0, max(0.0, g))
        gl.location = (0.0, y, 2.4)
        gl.rotation_euler = (Vector((0.0, y - 1.0, 0.0)) - Vector((0.0, y, 2.4))).to_track_quat('-Z', 'Y').to_euler()
        gl.data.energy = 260.0 * math.sin(math.pi * g) ** 2 if 0 < g < 1 else 0.0
    sc.frame_start, sc.frame_end = 0, n - 1
    return update


def shot_H(sc):
    """Frame 0 continues C's last frame (same slow push). 4 frames of the clean poster, then the strips rip
    sideways in a fast wave from the top while the camera lunges at the headline."""
    n = 30
    strips, rng, cam = build_poster(sc)
    NS = len(strips)
    hold = 4 / FPS
    plan = []
    for i in range(NS):
        k = NS - 1 - i
        plan.append((rng.choice([-1, 1]) * rng.uniform(0.35, 1.1), hold + 0.010 * k + rng.uniform(0, 0.03)))

    def update(f):
        t = f / FPS
        for ob, (amp, ts) in zip(strips, plan):
            u = max(0.0, t - ts) / 0.3
            set_off(ob, amp * u ** 2.2)
        u = max(0.0, t - hold) / (n / FPS - hold)
        cam.data.ortho_scale = C_END_SCALE - PUSH * t - 1.35 * u ** 2.2
        cam.location = (0.0, CAM_Y0 + 1.03 * u ** 2.2, 10)
    sc.frame_start, sc.frame_end = 0, n - 1
    return update


# ---------------------------------------------------------------- ribbons (shot A)

class Ribbon:
    """A long strip draped along +X: arches, meander and a limited twist (it never turns edge-on).
    Geometry is a function of time: arches sag as the ribbon settles, a slow wave sways it, raised parts flutter.
    `land` = (t_land, s_contact, direction, drift, phase) makes it fall onto the pile: it comes down at a steady
    terminal speed, slows on the air cushion, and touches down progressively, the contact rolling along the
    strip from s_contact, so it lays down like paper instead of dropping like a plank. While airborne it billows,
    flutters, twists more and drifts sideways."""

    def __init__(self, name, mat, length, width, rng, base_xy, z0, uvmode, uvargs, nx=700, ny=10,
                 amp=0.16, freq=(1.1, 1.7), meander=1.0, twist=0.4, land=None, solid=0.0025, crisp=False,
                 crimp=0.0):
        self.L, self.w, self.base, self.z0 = length, width, base_xy, z0
        self.solid = solid
        s = np.linspace(0, length, nx + 1)
        t = np.linspace(-0.5, 0.5, ny + 1)
        self.S, self.T = np.meshgrid(s, t)
        self.s = s
        self.ph = rng.uniform(0, 6.28, 6)
        self.meander, self.amp, self.twist = meander, amp * rng.uniform(0.7, 1.15), twist
        self.fq = rng.uniform(*freq)
        self.hnoise = smooth_1d(rng, nx + 1, 25) * amp * 0.12
        self.znoise = smooth_field(rng, ny + 1, nx + 1, 3, 4) * 0.003
        self.crease = crease_field(rng, self.S, self.T * width, max(4, int(length * 3)), 0.006, across=True)
        if crimp:
            # transverse zig-zag kinks left by the shredder's rollers, irregular pitch about 0.2: the light
            # breaks on crisp lines across the strip, which rubber or leather never does
            ph = np.cumsum(rng.uniform(0.5, 1.5, nx + 1)) * (s[1] - s[0]) / 0.2
            fr = ph - np.floor(ph) - 0.5
            zc = 2 * crimp * rng.uniform(0.6, 1.3) * np.sqrt(fr ** 2 + 0.03 ** 2)
            self.crease = self.crease + (zc - zc.mean())[None, :]
        self.land = land
        self.sway = rng.uniform(0.012, 0.025)
        U, V = uvmode(self.S, self.T, *uvargs)
        self.faces = grid_faces(ny, nx)
        self.ob = make_mesh(name, self.coords(0.0), self.faces, U, V, mat, solid=solid, crisp=crisp)

    def coords(self, t):
        s, S, T, ph = self.s, self.S, self.T, self.ph
        settle = 1 + 0.35 * (1 - sease(t / 1.8, 1.4))
        lat = self.meander * (0.10 * np.sin(s * 0.9 + ph[0]) + 0.05 * np.sin(s * 2.3 + ph[1]))
        lat = lat + self.sway * np.sin(s * 1.1 - 2.4 * t + ph[3])
        fold = np.abs(np.sin(s * self.fq + ph[2])) ** 3.0
        h = self.amp * fold * settle + self.hnoise
        h = h - h.min()
        tw = self.twist * (0.7 * np.sin(s * 0.7 + ph[1]) * fold + 0.3 * np.sin(s * 1.9 + ph[0]))
        tw = tw + 0.10 * fold * np.sin(3.1 * t + s * 1.3 + ph[4])
        dz = 0.0
        air = 0.0
        if self.land:
            tl, s_c, dn, drift, ph5 = self.land
            tau = tl - t + np.clip(dn * (s - s_c) / 5.0, -0.35, 0.35)       # contact rolls along at 5 u/s
            dz = 1.0 * (np.sqrt(np.maximum(tau, 0.0) ** 2 + 0.12 ** 2) - 0.12)  # slow terminal fall, cushioned touchdown
            ls = np.maximum(-tau, 0.0)                                         # time since touchdown
            dz = dz + 0.012 * np.sin(2 * np.pi * ls / 0.16) * np.exp(-ls / 0.07)   # one small rebound
            air = np.clip(dz / 0.35, 0.0, 1.0)
            h = h * (1 + 0.9 * air) + 0.05 * air * (1 + np.sin(2.4 * s - 6.0 * t + ph5))
            lat = lat + drift * dz
            tw = tw + 0.3 * air * np.sin(1.6 * s - 4.5 * t + ph5)
        tw = np.clip(tw, -0.5 - 0.1 * air, 0.5 + 0.1 * air)
        dx = np.gradient(lat, s)
        nrm = np.arctan(dx)
        X = self.base[0] + S - T * self.w * np.sin(nrm)[None, :]
        Y = self.base[1] + lat[None, :] + T * self.w * np.cos(tw)[None, :]
        Z = self.z0 + dz + h[None, :] + T * self.w * np.sin(tw)[None, :] + self.znoise + self.crease
        return np.stack([X, Y, Z], -1).reshape(-1, 3)

    def update(self, t, stack=None):
        co = self.coords(t)
        if stack is not None:
            co = stack.place(co.reshape(self.S.shape + (3,)), self.w, self.solid + 0.002,
                             self.L / (self.S.shape[1] - 1)).reshape(-1, 3)
        self.ob.data.vertices.foreach_set('co', co.reshape(-1))
        self.ob.data.update()


def _gauss_rows(a, sigma):
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    return np.stack([np.convolve(row, k, mode='valid') for row in p])


class Stack:
    """Ribbons never pass through each other: they are laid one by one in a fixed order, and each one is lifted
    to rest on a height map of everything laid before it. The lift drapes: it falls off with a limited slope
    along the strip and across it (paper is stiff over its narrow width), and the peaks are slightly rounded."""

    def __init__(self, x0, x1, y0, y1, res=0.02, floor=-0.01, slope_s=0.2, slope_t=0.3):
        self.x0, self.y0, self.res = x0, y0, res
        self.nx, self.ny = int((x1 - x0) / res) + 1, int((y1 - y0) / res) + 1
        self.floor, self.slope_s, self.slope_t = floor, slope_s, slope_t
        self.reset()

    def reset(self):
        self.H = np.full((self.ny, self.nx), self.floor, np.float64)

    def _idx(self, X, Y):
        ix = np.clip(np.rint((X - self.x0) / self.res).astype(int), 0, self.nx - 1)
        iy = np.clip(np.rint((Y - self.y0) / self.res).astype(int), 0, self.ny - 1)
        return ix, iy

    def place(self, co, w, gap, ds):
        """co: (nt, ns, 3) top surface of a strip, rows across the width, columns along it."""
        ix, iy = self._idx(co[..., 0], co[..., 1])
        h = self.H[iy, ix]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                h = np.maximum(h, self.H[np.clip(iy + dy, 0, self.ny - 1), np.clip(ix + dx, 0, self.nx - 1)])
        need = np.maximum(0.0, h + gap - co[..., 2])
        if need.max() > 0:
            nt = need.shape[0]
            tg = np.linspace(-0.5, 0.5, nt) * w
            p = np.max(need[None, :, :] - self.slope_t * np.abs(tg[:, None, None] - tg[None, :, None]), axis=1)
            ramp = np.arange(p.shape[1]) * ds * self.slope_s
            f = np.maximum.accumulate(p + ramp, axis=1) - ramp
            b = np.maximum.accumulate((p - ramp)[:, ::-1], axis=1)[:, ::-1] + ramp
            q = np.maximum(f, b)
            q = np.maximum(_gauss_rows(q, 3.0), need)
            co = co.copy()
            co[..., 2] += q
        np.maximum.at(self.H, (iy, ix), co[..., 2])
        return co


def uv_vertical(S, T, u0, v0, width, scale):
    """Shredder strip: print runs down the poster along the length."""
    return u0 + (T + 0.5) * width / (POSTER_W * scale), v0 - S / (POSTER_H * scale)


def uv_horizontal(S, T, u0, v0, v1, length_scale):
    """Hero: a horizontal band of the poster (v0..v1) laid along the ribbon, so a whole word runs along it."""
    return u0 + S / (POSTER_W * length_scale), v0 + (T + 0.5) * (v1 - v0)


def shot_A(sc):
    """Cascade of wide shredder ribbons on a light floor, three depth layers; a hero band of the headline runs along
    the camera path in focus. From the first frame ribbons are falling and laying down onto the pile (the hero
    lands at 0.3 s), one after another through the shot, so the paper's softness reads at once. The camera
    tracks with a speed ramp."""
    n = 112
    rng = np.random.default_rng(31)
    tt = np.arange(n + 2) / FPS
    v = 1.0 + 1.4 * np.exp(-tt / 0.1) + 1.6 * np.array([sease((x - 1.35) / 0.5, 2.2) for x in tt])
    v = v * 0.8
    pos = np.concatenate([[0], np.cumsum(v[:-1] / FPS)])
    fr = np.arange(n + 2)

    def cam_x(t):
        return -2.4 + float(np.interp(t * FPS, fr, pos))

    lrng = np.random.default_rng(77)

    def landing(tl, base_x):
        return (tl, cam_x(tl) + lrng.uniform(-0.4, 0.6) - base_x, lrng.choice([-1, 1]),
                lrng.uniform(0.12, 0.3) * lrng.choice([-1, 1]), lrng.uniform(0, 6.28))
    # uncoated stock: matte paper, satin (not glossy) ink, no stretched fibre, real translucency
    pk = dict(bump=0.14, rough=0.6, ink_rough=0.44, spec=0.32, fibre=0.0, ink=0.045, trans=0.24)
    mat = paper_set('paper_A', image='poster_plain.png', **pk)      # the red stays on the hero only
    mat_hero = paper_set('paper_A_hero', image='poster.png', **pk)
    S = 1.5
    width = 0.27
    L = 14.0
    ribs = []
    k = 0
    for layer, count, amp, z0 in ((0, 16, 0.03, 0.0), (1, 18, 0.15, 0.03), (2, 8, 0.24, 0.07)):
        for j in range(count):
            y = -3.0 + (j + rng.uniform(-0.3, 0.3)) * (5.6 / count)
            wid = width * rng.uniform(0.85, 1.15)
            bx = -L / 2 - 1.5 + rng.uniform(-1, 1)
            ribs.append(Ribbon(f'rib{k:02d}', mat, L, wid, rng, (bx, y), z0,
                               uv_vertical, (rng.uniform(0, 1), rng.uniform(0, 1), wid, S),
                               amp=amp, twist=0.45, solid=0.002, crisp=True, crimp=0.005))
            ribs[-1].layer, ribs[-1].y, ribs[-1].bx, ribs[-1].j = layer, y, bx, j
            k += 1
    # droppers: the whole top layer and every third ribbon of the middle one; those nearest the view land first,
    # so ribbons are in the air in frame 0 and keep landing through the shot
    drop = [r for r in ribs if r.layer == 2 or (r.layer == 1 and r.j % 3 == 1)]
    drop.sort(key=lambda r: abs(r.y - 0.25))
    times = [0.1, 0.18, 0.46, 0.58, 0.72, 0.86, 1.0, 1.12, 1.26, 1.4, 1.55, 1.2, 0.95, 1.6, 0.8, 1.35]
    for r, tl in zip(drop, times):
        r.land = landing(tl, r.bx)
    # stacking order: the resting ribbons layer by layer, shuffled inside a layer so the overlaps don't shingle
    # one way; then the droppers in order of landing, so whatever lands later rests on top
    order_rng = np.random.default_rng(5)
    rest = []
    for layer in (0, 1, 2):
        idx = [r for r in ribs if r.layer == layer and r.land is None]
        order_rng.shuffle(idx)
        rest += idx
    # hero: the headline running along the path, wide, gentle, in focus; it lays down onto the pile at 0.3 s
    hero_scale = 0.78
    hero = Ribbon('hero', mat_hero, 6.0, 0.18 * POSTER_H * hero_scale, rng, (-4.6, 0.05), 0.12,
                  uv_horizontal, (0.0, 0.755, 0.935, hero_scale), nx=900, ny=16, amp=0.07,
                  freq=(0.5, 0.7), meander=0.35, twist=0.12, solid=0.002, crisp=True, crimp=0.004)
    hero.land = (0.3, cam_x(0.3) + 0.2 + 4.6, 1, 0.1, 1.3)
    ribs = rest + sorted(drop + [hero], key=lambda r: r.land[0])
    stack = Stack(-10.5, 8.0, -3.8, 3.4, res=0.02, floor=-0.01)
    add_plane('floor', floor_material(0.30, 0.38), -20, -20, 20, 20, -0.01)

    cam = persp_camera(sc, 38, fstop=2.2, focus=3.6)
    sc.cycles.diffuse_bounces = 8                     # light bounces around inside the pile: no black pits
    sc.cycles.transmission_bounces = 8
    sc.world.node_tree.nodes['Background'].inputs[1].default_value = 0.5
    area_light('key', (-2.5, 3.0, 5.0), (0, 0, 0), 2.8, 880, (1.0, 0.975, 0.94))   # smaller: falling ribbons cast a readable shadow
    area_light('top', (0.0, 0.0, 7.0), (0, 0, 0), 14, 210, (0.97, 0.98, 1.0))                    # broad sky
    area_light('back', (1.5, 5.0, 1.2), (0, 0, 0.2), 6, 350, (1.0, 0.98, 0.95), size_y=1.5)    # glows through arches
    sc.view_settings.exposure = -0.9

    def update(f):
        t = f / FPS
        stack.reset()
        for r in ribs:
            r.update(t, stack)
        x = cam_x(t)
        z = 3.3 + 0.9 * sease(f / (n - 1), 1.3)
        sx, sy, sz = shake(t, 1, 0.006), shake(t, 2, 0.006), shake(t, 3, 0.004)
        roll = math.radians(-40 - 6 * sease(f / (n - 1), 1.5))                     # a slow drift in the roll
        look_at(cam, (x + sx, -1.5 + sy, z + sz), (x, 0.2, 0.0), roll=roll + shake(t, 4, 0.003))
        cam.data.dof.focus_distance = float(np.linalg.norm([1.65, z - 0.15]))
    sc.frame_start, sc.frame_end = 0, n - 1
    return update


# ---------------------------------------------------------------- the shredder (shots F and O)
#
# A strip-cut shredder in close-up. Two shafts sit either side of the paper plane (y = 0); on each, cutter
# discs alternate with spacers, and the discs of one shaft run in the lanes where the other has spacers, so
# their edges overlap by a few mm and shear the sheet into 26 lanes. Combs below strip the paper off.
# The poster comes down bottom-first, so its text reads upright; each strip leaves the nip in its own lane,
# pushed back or forward alternately, and curls and sways there. Lanes never cross, so nothing can collide.
# The print flows: every (sub)frame rebuilds the sheet and the strips from the length fed so far, and the
# cockle of the paper is sampled at paper coordinates, so it travels with the print into the cutters.

LANES = 26
LANE_W = POSTER_W / LANES
R_DISC, R_SPACER = 0.21, 0.138
SHAFT_D = 0.19                                    # shaft axis to the paper plane
Z_CUT = math.sqrt(R_DISC ** 2 - SHAFT_D ** 2)     # where the two discs' edges cross: the scissor point
PAPER_T = 0.0012                                  # lane 0.077 : 0.0012, like a 5.8 mm strip of 90 gsm paper
F_FRAMES, O_FRAMES = 84, 72
FEED_V = 0.75                                     # u/s under load: 10 cm/s on a 42 cm poster, a fast office shredder
SPIN = FEED_V / R_DISC                            # rad/s: rim speed = paper speed under load
FEED_START = 0.14                                 # the poster's bottom edge is this far above the cut line at F 0


def feed_curve():
    """Length of paper past the cut line vs time from the start of F. It slides in at 0.42 u/s; when the
    cutters bite they snatch it (a quick surge) and then pull a steady FEED_V under load."""
    dt = 1 / 1200
    tt = np.arange(-0.2, 3.5, dt)
    t_b = FEED_START / 0.42
    v = 0.42 + (FEED_V - 0.42) * np.array([sease((x - t_b) / 0.07, 2) for x in tt])
    v = v + 0.22 * np.where(tt > t_b, np.exp(-(tt - t_b) / 0.05) * (1 - np.exp(-(tt - t_b) / 0.012)), 0.0)
    p = np.cumsum(v) * dt
    p = p - FEED_START - np.interp(0.0, tt, p)
    return tt, p, t_b


def lathe_mesh(name, profile, nth, rad=None):
    """Revolve a closed (x, r[, rim]) profile around X; rad(theta) adds radius to the points flagged rim."""
    prof = np.array([(p[0], p[1]) for p in profile], float)
    rim = np.array([p[2] if len(p) > 2 else 0 for p in profile], float)
    th = np.linspace(0, 2 * math.pi, nth, endpoint=False)
    extra = rad(th) if rad is not None else np.zeros(nth)
    r = prof[None, :, 1] + rim[None, :] * extra[:, None]
    X = np.broadcast_to(prof[None, :, 0], r.shape)
    V = np.stack([X, r * np.cos(th)[:, None], r * np.sin(th)[:, None]], -1).reshape(-1, 3)
    P = len(prof)
    i = np.arange(nth)[:, None]
    j = np.arange(P)[None, :]
    F = np.stack([i * P + j, i * P + (j + 1) % P, ((i + 1) % nth) * P + (j + 1) % P, ((i + 1) % nth) * P + j], -1)
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], F.reshape(-1, 4).tolist())
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    return me


def extrude_yz(name, poly, x0, x1, mat, bevel=0.0):
    """A prism: polygon in (y, z) extruded along X from x0 to x1."""
    n = len(poly)
    V = [(x0, y, z) for y, z in poly] + [(x1, y, z) for y, z in poly]
    F = [tuple(range(n)), tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], F)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if bevel:
        md = ob.modifiers.new('round', 'BEVEL')
        md.width = bevel
        md.segments = 3
        md.limit_method = 'ANGLE'
        md.harden_normals = False
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    es = ob.modifiers.new('crisp', 'EDGE_SPLIT')
    es.split_angle = math.radians(35)
    es.use_edge_sharp = False
    return ob


def _sm(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _cumtrapz(y, x):
    return np.concatenate([[0.0], np.cumsum((y[1:] + y[:-1]) / 2 * np.diff(x))])


class Shredder:
    def __init__(self, sc, seed=61):
        rng = np.random.default_rng(seed)
        self.tt, self.pp, self.t_b = feed_curve()
        steel = steel_material('steel', aniso=0.55)
        steel_sp = steel_material('steel_spacer', col=(0.40, 0.40, 0.41), rough=0.36, aniso=0.45, rings=600, grime=0.5)
        nylon = plastic_material('nylon')
        nylon_bar = plastic_material('nylon_bar', col=(0.05, 0.05, 0.055), rough=0.34)   # catches a sheen: not a black hole
        # cutter disc: chamfered rim, three hooked teeth, a fine serration; spacer: plain chamfered ring
        hwd, hws, c = 0.48 * LANE_W, 0.497 * LANE_W, 0.0045

        def teeth(th):
            u = np.mod(th, 2 * math.pi / 3) / 0.5
            return np.where(u < 1, 0.017 * u ** 1.7, 0.0) + 0.0022 * np.mod(th * 44 / (2 * math.pi), 1.0)
        disc_me = lathe_mesh('disc', [(-hwd, 0.05, 0), (-hwd, R_DISC - c, 1), (-hwd + c, R_DISC, 1),
                                      (hwd - c, R_DISC, 1), (hwd, R_DISC - c, 1), (hwd, 0.05, 0)], 792, teeth)
        disc_me.materials.append(steel)
        cs = 0.004
        sp_me = lathe_mesh('spacer', [(-hws, 0.05), (-hws, R_SPACER - cs), (-hws + cs, R_SPACER),
                                      (hws - cs, R_SPACER), (hws, R_SPACER - cs), (hws, 0.05)], 240)
        sp_me.materials.append(steel_sp)
        self.rot = []
        for side, yc in ((0, -SHAFT_D), (1, SHAFT_D)):
            for i in range(-2, LANES + 2):
                xc = -POSTER_W / 2 + (i + 0.5) * LANE_W
                disc = (i % 2 == 0) == (side == 0)
                ob = bpy.data.objects.new(f'{"fb"[side]}{"ds"[0 if disc else 1]}{i + 2:02d}', disc_me if disc else sp_me)
                sc.collection.objects.link(ob)
                es = ob.modifiers.new('crisp', 'EDGE_SPLIT')
                es.split_angle = math.radians(30)
                es.use_edge_sharp = False
                ob.location = (xc, yc, 0.0)
                self.rot.append((ob, -1.0 if side == 0 else 1.0, rng.uniform(0, 2 * math.pi)))
        # combs: a bar below-outside each shaft, fingers reaching in around the spacers
        deg = math.radians
        for side, yc in ((0, -SHAFT_D), (1, SHAFT_D)):
            sg = 1.0 if side == 0 else -1.0

            def P(th, r):
                return (yc + sg * r * math.sin(th), -r * math.cos(th))
            r_in, r_out = R_SPACER + 0.006, R_SPACER + 0.04
            fp = [P(th, r_in) for th in np.linspace(deg(50), deg(-72), 34)]
            fp += [P(th, 0.305) for th in np.linspace(deg(-72), deg(-33), 12)]
            fp += [P(th, r_out) for th in np.linspace(deg(-33), deg(50), 24)]
            tc, rr = (r_in + r_out) / 2, (r_out - r_in) / 2
            fp += [P(deg(50) + rr / tc * math.sin(a), tc + rr * math.cos(a)) for a in np.linspace(0, math.pi, 8)[1:-1]]
            for i in range(-2, LANES + 2):
                if (i % 2 == 1) != (side == 0):
                    continue                       # fingers only in this shaft's spacer lanes
                xc = -POSTER_W / 2 + (i + 0.5) * LANE_W
                extrude_yz(f'finger{side}{i + 2:02d}', fp, xc - 0.4 * LANE_W, xc + 0.4 * LANE_W, nylon, bevel=0.003)
            bp = [P(th, 0.235) for th in np.linspace(deg(-75), deg(-30), 16)]
            bp += [P(th, 0.31) for th in np.linspace(deg(-30), deg(-75), 16)]
            extrude_yz(f'bar{side}', bp, -1.25, 1.25, nylon_bar, bevel=0.004)
        # paper
        pk = dict(bump=0.12, rough=0.6, ink_rough=0.44, spec=0.32, fibre=0.0, ink=0.045, trans=0.24, slide=None)
        mats = paper_set('paper_F', **pk)
        p0, dp = -0.25, 0.01
        Xg, Pg = np.meshgrid(np.linspace(-1, 1, 201), np.arange(p0, POSTER_H + 0.3, dp))
        self.cock = crease_field(rng, Xg, Pg, 34, 0.0045, across=False, sharp=0.002) \
            + smooth_field(rng, *Xg.shape, 5, 5) * 0.0012
        self.cock_p0, self.cock_dp = p0, dp
        self.snx, self.sny, self.span = 200, 220, 2.3
        self.sheet_faces = grid_faces(self.sny, self.snx)
        z = np.zeros(((self.sny + 1) * (self.snx + 1), 3))
        uz = np.zeros((self.sny + 1, self.snx + 1))
        self.sheet = make_mesh('sheet', z, self.sheet_faces, uz, uz, mats, solid=PAPER_T, crisp=True)
        self.nseg, self.ncol = 170, 4
        self.strip_faces = grid_faces(self.nseg, self.ncol)[:, ::-1].copy()     # printed side faces -y
        self.strips = []
        for i in range(LANES):
            sgn = 1.0 if i % 2 == 0 else -1.0       # even lanes pushed back by the front discs, odd forward
            strong = rng.random() < 0.25
            prm = dict(sg=sgn, xc=-POSTER_W / 2 + (i + 0.5) * LANE_W,
                       a=rng.uniform(1.2, 1.58) if strong else rng.uniform(0.3, 1.05),
                       lam=rng.uniform(0.1, 0.26), ell=rng.uniform(0.35, 1.6), sc=rng.uniform(0.38, 0.46),
                       fq=rng.uniform(0.7, 1.4), ph=rng.uniform(0, 6.28), ph2=rng.uniform(0, 6.28),
                       tw=rng.uniform(0.15, 0.45), twl=rng.uniform(0.45, 0.9), wob=rng.uniform(0, 6.28),
                       fq2=rng.uniform(2.5, 4.0), ph3=rng.uniform(0, 6.28))
            zz = np.zeros(((self.nseg + 1) * (self.ncol + 1), 3))
            uz = np.zeros((self.nseg + 1, self.ncol + 1))
            ob = make_mesh(f'lane{i:02d}', zz, self.strip_faces, uz, uz, mats, solid=PAPER_T, crisp=True)
            self.strips.append((ob, prm))
        # paper dust shaken loose by the cut: tumbling flecks, born after the bite
        nf = 280
        self.fl = dict(t0=rng.uniform(self.t_b + 0.05, 2.8, nf), o=np.stack([rng.uniform(-0.95, 0.95, nf),
                       rng.uniform(-0.09, 0.09, nf), rng.uniform(-0.32, -0.26, nf)], 1),
                       v=np.stack([rng.normal(0, 0.03, nf), rng.normal(0, 0.07, nf), -rng.uniform(0.1, 0.32, nf)], 1),
                       ax=rng.normal(0, 1, (nf, 3)), w=rng.uniform(4, 14, nf), phi=rng.uniform(0, 6.28, nf),
                       size=np.stack([rng.uniform(0.003, 0.009, nf), rng.uniform(0.0015, 0.004, nf)], 1),
                       dph=rng.uniform(0, 6.28, nf))
        self.fl['ax'] /= np.linalg.norm(self.fl['ax'], axis=1, keepdims=True)
        fv = np.zeros((nf * 4, 3))
        ff = np.arange(nf * 4).reshape(nf, 4)
        self.flecks = make_mesh('flecks', fv, ff, np.zeros(nf * 4), np.zeros(nf * 4), edge_material('fleck'))
        self.flecks.data.polygons.foreach_set('use_smooth', [False] * nf)
        # light: warm key, a long strip for the disc rims, a side rake for the ground faces, a cool backlight
        # under the strips so they glow, a faint front fill; the machine's inside stays dark
        wall = add_plane('wall', plastic_material('wall', col=(0.05, 0.05, 0.055), rough=0.7), -4, -3.5, 4, 1.0)
        wall.rotation_euler = (math.pi / 2, 0, 0)
        wall.location = (0, 1.3, 0)
        bg = sc.world.node_tree.nodes['Background']
        bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1)
        bg.inputs[1].default_value = 0.03
        sc.cycles.diffuse_bounces = 6
        sc.cycles.glossy_bounces = 6
        sc.cycles.sample_clamp_indirect = 6.0          # no sparkle from indirect glints on the machined steel
        area_light('key', (-1.4, -2.6, 2.2), (0, 0, 0.1), 2.5, 190, (1.0, 0.965, 0.92))
        area_light('rims', (0.2, -1.0, 1.15), (0, -0.25, 0.1), 3.0, 70, (1.0, 0.99, 0.97), size_y=0.22)
        area_light('rake', (-2.6, -0.6, 0.4), (0, -0.2, 0.0), 0.8, 110, (1.0, 0.98, 0.95))
        # backlight behind the curtain (in front of the wall), so the
        # strips glow through and the curls catch a rim
        bl = area_light('back', (0.3, 1.0, -1.5), (0.0, -0.2, -0.75), 1.6, 170, (0.92, 0.96, 1.0),
                        spread=math.radians(70))
        bl.visible_camera = False
        area_light('fill', (1.5, -3.5, -0.5), (0, 0, -0.2), 6.0, 22, (0.92, 0.95, 1.0))
        sc.view_settings.exposure = 0.0

    def feed(self, t):
        return float(np.interp(t, self.tt, self.pp))

    def _cockle(self, p, x):
        fi = np.clip((p - self.cock_p0) / self.cock_dp, 0, self.cock.shape[0] - 1.001)
        fj = np.clip((x + 1) / 0.01, 0, self.cock.shape[1] - 1.001)
        i0, j0 = fi.astype(int), fj.astype(int)
        a, b = fi - i0, fj - j0
        C = self.cock
        return (C[i0, j0] * (1 - a) * (1 - b) + C[i0 + 1, j0] * a * (1 - b) + C[i0, j0 + 1] * (1 - a) * b
                + C[i0 + 1, j0 + 1] * a * b)

    def update(self, t):
        f = self.feed(t)
        ang = SPIN * t
        for ob, sg, ph in self.rot:
            ob.rotation_euler = (sg * ang + ph, 0.0, 0.0)
        load = _sm((t - self.t_b) / 0.05) * (1 + 1.5 * math.exp(-max(0.0, t - self.t_b) / 0.08))
        # the sheet above the cut line
        plo = max(0.0, f)
        x = np.linspace(-1, 1, self.snx + 1)
        p = plo + np.linspace(0, self.span, self.sny + 1)
        X, Pm = np.meshgrid(x, p)
        Z = Z_CUT + Pm - f
        fade = _sm((Z - Z_CUT) / 0.18)
        bow = -0.035 * _sm((Z - 0.25) / 0.9)
        vib = 0.0012 * load * np.sin(2 * math.pi * 41 * t + 7 * X + 3 * Z)
        Y = (-self._cockle(Pm, X) + vib) * fade + bow
        co = np.stack([X, Y, Z], -1).reshape(-1, 3)
        self.sheet.data.vertices.foreach_set('co', co.reshape(-1))
        set_uv(self.sheet, (X + 1) / POSTER_W, Pm / POSTER_H, self.sheet_faces)
        self.sheet.data.update()
        # the strips below it
        L = max(f, 1e-4)
        s = np.linspace(0, L, self.nseg + 1)
        T = np.linspace(-0.5, 0.5, self.ncol + 1)
        ws = LANE_W * 0.985
        for ob, q in self.strips:
            sg = q['sg']
            u = s - q['sc']
            phi = sg * 0.9 * np.sin(math.pi * np.clip(s / 0.08, 0, 1))                  # S-bend through the nip
            phi = phi + sg * q['a'] * _sm(u / q['lam']) * np.exp(-np.maximum(0.0, u - q['lam']) / q['ell'])
            env = np.clip(u / 0.5, 0, None) ** 1.5
            phi = phi + env * (0.12 * np.sin(2 * math.pi * q['fq'] * t - 2 * math.pi * s / 0.8 + q['ph'])
                               + 0.035 * np.sin(2 * math.pi * q['fq2'] * t - 2 * math.pi * s / 0.35 + q['ph3']))
            phi = np.clip(phi, -1.6, 1.6)
            y = _cumtrapz(np.sin(phi), s)
            z = Z_CUT - _cumtrapz(np.cos(phi), s)
            tw = q['tw'] * np.sin(2 * math.pi * s / q['twl'] + q['ph2'] - 2 * math.pi * 0.6 * t) * _sm(u / 0.3)
            cphi, sphi, ct, st = np.cos(phi), np.sin(phi), np.cos(tw), np.sin(tw)
            wv = np.stack([ct, st * cphi, st * sphi], -1)                  # across the strip
            nv = np.stack([-st, ct * cphi, ct * sphi], -1)                 # strip normal (towards +y at the nip)
            pc = f - s                                                     # paper coordinate along the strip
            xs = q['xc'] + T * ws
            Pm2, Xm2 = np.meshgrid(pc, xs, indexing='ij')
            ck = self._cockle(Pm2, Xm2) * _sm((s[:, None] - 0.3) / 0.2)
            lat = 0.004 * np.sin(2 * math.pi * 0.5 * t + q['wob'] + s * 3)[:, None] * _sm(u / 0.4)[:, None]
            P = np.stack([np.full_like(s, q['xc']), y, z], -1)
            V = P[:, None, :] + (T * ws)[None, :, None] * wv[:, None, :] - ck[..., None] * nv[:, None, :]
            V[..., 0] += lat
            ob.data.vertices.foreach_set('co', V.reshape(-1))
            set_uv(ob, (Xm2 + 1) / POSTER_W, Pm2 / POSTER_H, self.strip_faces)
            ob.data.update()
        # dust
        F_ = self.fl
        age = t - F_['t0']
        alive = age > 0
        a = np.maximum(age, 0)[:, None]
        pos = F_['o'] + F_['v'] * a + np.stack([0.02 * np.sin(3 * a[:, 0] + F_['dph']), 0.03 * np.sin(2.3 * a[:, 0] + F_['dph']),
                                                 np.zeros_like(a[:, 0])], 1)
        ang_ = F_['phi'] + F_['w'] * a[:, 0]
        k = F_['ax']
        corners = np.array([[-0.5, -0.5, 0], [0.5, -0.5, 0], [0.5, 0.5, 0], [-0.5, 0.5, 0]])
        loc = corners[None, :, :] * np.concatenate([F_['size'], np.ones((len(a), 1))], 1)[:, None, :]
        c_, s_ = np.cos(ang_)[:, None, None], np.sin(ang_)[:, None, None]
        kk = k[:, None, :]
        rot = loc * c_ + np.cross(kk, loc) * s_ + kk * np.sum(kk * loc, -1, keepdims=True) * (1 - c_)
        Vf = pos[:, None, :] + rot
        Vf[~alive] = np.array([0.0, 5.0, -20.0])
        self.flecks.data.vertices.foreach_set('co', Vf.reshape(-1))
        self.flecks.data.update()
        return f


def shot_F(sc):
    """FEED: the poster comes down into the cutters bottom-first; the camera dollies in on the bite line and
    tilts down as the first strips come out under the comb."""
    n = F_FRAMES
    sc.render.resolution_x, sc.render.resolution_y = INSET
    rig = Shredder(sc)
    cam = persp_camera(sc, 40, fstop=0.35, focus=3.5)
    import json
    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    t_emerge = float(np.interp(0.45, rig.pp, rig.tt))
    with open(os.path.join(ROOT, 'build', 'f_cues.json'), 'w') as fh:
        json.dump({'bite': rig.t_b, 'emerge': t_emerge}, fh)

    def update(f):
        t = f / FPS
        rig.update(t)
        u = sease(t / (n / FPS), 1.8)
        d = 5.4 - 2.5 * u
        el = 0.22 - 0.12 * u
        tx, tz = -0.04 + 0.12 * (t / (n / FPS)), 1.0 - 1.3 * u
        sx, sz = shake(t, 11, 0.004), shake(t, 12, 0.003)
        loc = (tx + sx, -d * math.cos(el), tz + d * math.sin(el) + sz)
        look_at(cam, loc, (tx, 0.0, tz), roll=shake(t, 13, 0.002))
        cam.data.dof.focus_distance = float(np.linalg.norm(np.array(loc) - np.array((tx, -0.12, 0.12))))
    sc.frame_start, sc.frame_end = 0, n - 1
    return update


def shot_O(sc):
    """OUT: below the cutters, looking up into the curtain of strips: alternate lanes curl towards and away
    from the camera, sway, and carry the sliced headline down; the camera trucks, then whips out."""
    n = O_FRAMES
    sc.render.resolution_x, sc.render.resolution_y = INSET
    rig = Shredder(sc)
    cam = persp_camera(sc, 32, fstop=0.35, focus=1.7)
    t_off = F_FRAMES / FPS
    tt = np.arange(n + 2) / FPS
    v = 0.18 + 0.9 * np.array([sease((x - 0.85) / 0.3, 2.2) for x in tt])
    pos = np.concatenate([[0], np.cumsum(v[:-1] / FPS)])
    fr = np.arange(n + 2)

    def update(f):
        t = f / FPS
        rig.update(t + t_off)
        x = 0.1 + float(np.interp(f, fr, pos))
        sx, sz = shake(t, 14, 0.004), shake(t, 15, 0.003)
        loc = (x + sx, -1.25, -1.25 + sz)
        tgt = (x - 0.05, -0.05, -0.45)
        look_at(cam, loc, tgt, roll=shake(t, 16, 0.003))
        cam.data.dof.focus_distance = float(np.linalg.norm(np.array(loc) - np.array((x, -0.12, -0.5))))
    sc.frame_start, sc.frame_end = 0, n - 1
    return update


def hermite(keys, t):
    """C1 path through (time, vector) keys: cubic Hermite with Catmull-Rom tangents over non-uniform times."""
    ts = np.array([k[0] for k in keys], float)
    P = np.array([k[1] for k in keys], float)
    n = len(ts)
    M = np.zeros_like(P)
    for i in range(n):
        a, b = max(0, i - 1), min(n - 1, i + 1)
        M[i] = (P[b] - P[a]) / (ts[b] - ts[a])
    t = min(max(t, ts[0]), ts[-1])
    i = min(int(np.searchsorted(ts, t, side='right')) - 1, n - 2)
    h = ts[i + 1] - ts[i]
    u = (t - ts[i]) / h
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return h00 * P[i] + h10 * h * M[i] + h01 * P[i + 1] + h11 * h * M[i + 1]


FO_FRAMES = 123
FO_T0 = 0.10          # the feed clock is 0.1 s ahead at the cut: the poster is already sliding in

# one continuous camera move: a fast dolly at the poster going in, a close-up on the bite line while the headline is
# eaten, a dive past the cutters with a slight orbit and roll, under the comb looking up into the curtain as the
# sliced word comes out, a short truck, then the whip out. (time, camera, target, focus point, lens, roll)
FO_KEYS = [
    (0.00, (-0.30, -4.90, 2.05), (0.00, 0.0, 0.80), (0.00, -0.05, 0.60), 40.0, 0.06),
    (0.50, (-0.08, -2.70, 0.62), (0.03, 0.0, 0.15), (0.03, -0.12, 0.14), 40.0, 0.02),
    (0.95, (0.12, -1.85, -0.25), (0.10, 0.0, -0.12), (0.10, -0.12, -0.12), 36.0, -0.05),
    (1.30, (0.20, -1.30, -1.15), (0.15, -0.05, -0.42), (0.15, -0.12, -0.50), 32.0, 0.0),
    (1.70, (0.42, -1.25, -1.25), (0.37, -0.05, -0.45), (0.37, -0.12, -0.50), 32.0, 0.0),
    (2.05, (0.85, -1.25, -1.22), (0.80, -0.05, -0.45), (0.80, -0.12, -0.50), 32.0, 0.0),
]


def shot_FO(sc):
    """FEED into OUT without a cut: the camera rushes the poster going into the cutters, holds a beat on the
    bite line, then dives under the shredder and comes up into the curtain of strips, trucks and whips out."""
    n = FO_FRAMES
    sc.render.resolution_x, sc.render.resolution_y = INSET
    rig = Shredder(sc)
    cam = persp_camera(sc, 40, fstop=0.35, focus=3.5)
    import json
    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    t_emerge = float(np.interp(0.45, rig.pp, rig.tt))
    with open(os.path.join(ROOT, 'build', 'fo_cues.json'), 'w') as fh:
        json.dump({'bite': rig.t_b - FO_T0, 'emerge': t_emerge - FO_T0, 'under': 1.30}, fh)
    K = {name: [(k[0], k[i]) for k in FO_KEYS] for i, name in ((1, 'loc'), (2, 'tgt'), (3, 'foc'))}
    K['lens'] = [(k[0], (k[4],)) for k in FO_KEYS]
    K['roll'] = [(k[0], (k[5],)) for k in FO_KEYS]

    def update(f):
        t = f / FPS
        rig.update(t + FO_T0)
        loc = hermite(K['loc'], t) + np.array([shake(t, 11, 0.004), 0.0, shake(t, 12, 0.003)])
        tgt = hermite(K['tgt'], t)
        cam.data.lens = float(hermite(K['lens'], t)[0])
        look_at(cam, tuple(loc), tuple(tgt), roll=float(hermite(K['roll'], t)[0]) + shake(t, 13, 0.002))
        cam.data.dof.focus_distance = float(np.linalg.norm(loc - hermite(K['foc'], t)))
    sc.frame_start, sc.frame_end = 0, n - 1
    return update


SHOTS = {'H': shot_H, 'A': shot_A, 'F': shot_F, 'O': shot_O, 'FO': shot_FO, 'C': shot_C}


def frames_arg(s, sc):
    if s == 'all':
        return list(range(sc.frame_start, sc.frame_end + 1))
    out = []
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-')
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def set_time(sc, update, ff):
    fi = math.floor(ff)
    sc.frame_set(fi, subframe=ff - fi)
    update(ff)


def main():
    a = args()
    sc = reset()
    t_build = time.time()
    update = SHOTS[a.shot](sc)
    print('built', f'{time.time() - t_build:.1f}s', flush=True)
    sc.render.resolution_percentage = a.scale
    sc.cycles.samples = a.samples
    if a.expo is not None:
        sc.view_settings.exposure = a.expo
    if a.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, a.save))
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(out, exist_ok=True)
    W = sc.render.resolution_x * a.scale // 100
    H = sc.render.resolution_y * a.scale // 100
    tmp = os.path.join(out, f'_sub_{a.shot}.png')
    for f in frames_arg(a.frames, sc):
        t0 = time.time()
        dst = os.path.join(out, f'{a.shot}_{f:04d}.jpg')
        if a.subs <= 1:
            set_time(sc, update, f)
            sc.render.filepath = dst
            bpy.ops.render.render(write_still=True)
        else:
            sc.render.image_settings.file_format = 'PNG'
            sc.render.image_settings.color_depth = '8'
            sc.render.image_settings.compression = 0
            acc = None
            for o in ((np.arange(a.subs) + 0.5) / a.subs - 0.5) * a.shutter:
                set_time(sc, update, f + float(o))
                sc.render.filepath = tmp
                bpy.ops.render.render(write_still=True)
                im = bpy.data.images.load(tmp, check_existing=False)
                px = np.empty(W * H * 4, np.float32)
                im.pixels.foreach_get(px)
                bpy.data.images.remove(im)
                acc = px if acc is None else acc + px
            acc /= a.subs
            im = bpy.data.images.new('acc', W, H, alpha=False)
            im.pixels.foreach_set(acc)
            im.filepath_raw = dst
            im.file_format = 'JPEG'
            im.save(quality=94)
            bpy.data.images.remove(im)
        print('frame', f, f'{time.time() - t0:.1f}s', flush=True)
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == '__main__':
    main()
