import * as THREE from 'three';

// A browser adaptation of the upstream H / A / FO / C film grammar. The paper
// meshes, cutter rig and camera are evaluated from seconds, never a play clock.
const PAPER_W = 2, PAPER_H = 3, STRIPS = 22, LANES = 26;
const FONT = '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif';
const DEFAULTS = { width: 1080, height: 1920, paper: '#eeece7', ink: '#181716', accent: '#ac1210' };
const renderers = new WeakMap();
const imageIds = new WeakMap();
let nextImageId = 1;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = v => { const x = clamp(v); return x * x * (3 - 2 * x); };
const mix = (a, b, u) => a + (b - a) * u;
const noise = n => { const f = Math.sin(n * 127.1 + 311.7) * 43758.5453; return f - Math.floor(f); };

/** Phase durations refer to the eight-second source film, stretched per scene. */
export function paperFilmPhase(localTime, duration = 8) {
  if (!(Number.isFinite(duration) && duration >= 8)) throw new Error('三维纸张镜头每场至少需要 8 秒。');
  const t = clamp(Number(localTime) || 0, 0, duration) / duration * 8;
  if (t < .6) return { name: 'tear', time: t, progress: t / .6, filmTime: t };
  if (t < 2.6) return { name: 'cascade', time: t - .6, progress: (t - .6) / 2, filmTime: t };
  if (t < 5.1) return { name: 'shredder', time: t - 2.6, progress: (t - 2.6) / 2.5, filmTime: t };
  return { name: 'rebuild', time: t - 5.1, progress: (t - 5.1) / 2.9, filmTime: t };
}

// Kept pure so UV continuity and exact rest geometry can be checked in Node.
export function posterStripVertex(index, u, v, phase) {
  const h = PAPER_H / STRIPS;
  let amount, dx, dy, rz, curl;
  const side = index % 2 ? -1 : 1;
  if (phase.name === 'tear') {
    amount = ease((phase.time - .10 - index * .009) / .30);
    dx = side * amount * amount * (2.8 + noise(index + 2) * .9);
    dy = Math.sin(index * .8) * amount * .14;
    rz = side * amount * .12;
    curl = amount * .18;
  } else {
    const landed = ease((phase.time - index * .050) / .78);
    amount = 1 - landed;
    dx = side * amount * amount * (2.4 + noise(index + 2) * 1.0);
    dy = Math.sin(index * .8 + phase.time) * amount * .18;
    rz = side * amount * .12;
    curl = amount * .16 + (landed < 1 ? Math.sin(landed * Math.PI) * .075 : 0);
  }
  const x = (u - .5) * PAPER_W, yy = (v - .5) * h;
  return {
    x: x * Math.cos(rz) - yy * Math.sin(rz) + dx,
    y: 1.5 - (index + .5) * h + x * Math.sin(rz) + yy * Math.cos(rz) + dy,
    // At rest the adjacent strips share one surface, so their printed edges
    // meet cleanly rather than exposing hairline background gaps.
    z: .002 * Math.sin(u * 9) + curl * Math.sin(u * Math.PI * 2 + index * .65),
    // Every horizontal strip samples the same original poster coordinates.
    texU: u,
    texV: 1 - (index + 1) / STRIPS + v / STRIPS,
  };
}

/** The bottom edge enters first; the uncut and emerging UV ranges meet at fed/3. */
export function feedPaperVertex(lane, u, v, fed, time) {
  const length = clamp(fed, 0, PAPER_H);
  const s = v * length;
  const x = -PAPER_W / 2 + (lane + u) / LANES * PAPER_W;
  const bend = Math.pow(s / PAPER_H, 1.35);
  return {
    x: x + Math.sin(s * 2.2 + lane * .63 + time * 1.5) * .065 * bend,
    y: -.17 - s * .92,
    z: .06 + (lane % 2 ? 1 : -1) * .48 * bend + Math.sin(s * 3.5 - time * 2 + lane * .8) * .10 * bend,
    texU: (lane + u) / LANES,
    texV: clamp((length - s) / PAPER_H),
  };
}

function canvasElement(w, h) {
  if (typeof OffscreenCanvas === 'function') return new OffscreenCanvas(w, h);
  if (typeof globalThis.document?.createElement === 'function') {
    const c = globalThis.document.createElement('canvas'); c.width = w; c.height = h; return c;
  }
  throw new Error('三维纸张电影需要支持 OffscreenCanvas 的浏览器。');
}

function linesFor(ctx, text, maxWidth) {
  const out = [];
  for (const paragraph of String(text || '').split('\n')) {
    let line = '';
    for (const ch of Array.from(paragraph)) {
      if (line && ctx.measureText(line + ch).width > maxWidth) { out.push(line); line = ch; }
      else line += ch;
    }
    out.push(line);
  }
  return out;
}

function printBlock(ctx, text, box, { max = 70, min = 24, weight = 500, color = '#181716', line = 1.18 } = {}) {
  let fitted;
  for (let size = max; size >= min; size -= 2) {
    ctx.font = `${weight} ${size}px ${FONT}`;
    const lines = linesFor(ctx, text, box.w);
    if (lines.length * size * line <= box.h) { fitted = { size, lines }; break; }
  }
  if (!fitted) throw new Error('海报文字超出版面，请将这个分镜拆成两段或缩短标题。');
  ctx.fillStyle = color; ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  fitted.lines.forEach((t, i) => ctx.fillText(t, box.x, box.y + i * fitted.size * line));
  return fitted;
}

function imageKey(image) {
  if (!image || typeof image !== 'object') return '';
  if (!imageIds.has(image)) imageIds.set(image, nextImageId++);
  return `${imageIds.get(image)}:${image.currentSrc || image.src || ''}:${image.width}:${image.height}`;
}

function posterKey(scene, settings) {
  return JSON.stringify([scene.id, scene.title, scene.narration, scene.items, imageKey(scene.image), settings.paper, settings.ink, settings.accent]);
}

function posterTexture(scene, config, index, plain = false) {
  const canvas = canvasElement(1200, 1800), ctx = canvas.getContext('2d');
  ctx.fillStyle = config.paper; ctx.fillRect(0, 0, 1200, 1800);
  ctx.fillStyle = config.ink; ctx.fillRect(64, 116, 1072, 3);
  printBlock(ctx, 'PAPER / FILM', { x: 64, y: 65, w: 720, h: 48 }, { max: 34, min: 30, color: config.ink });
  printBlock(ctx, String(index + 1).padStart(2, '0'), { x: 1020, y: 62, w: 116, h: 55 }, { max: 40, min: 34, color: config.accent });
  ctx.fillStyle = plain ? config.paper : config.accent; ctx.fillRect(0, 166, 1200, 440);
  printBlock(ctx, scene.title || '纸张电影', { x: 62, y: 198, w: 1076, h: 370 }, {
    max: 160, min: 54, weight: 750, line: 1.08, color: plain ? config.ink : contrastInk(config.accent),
  });
  const image = scene.image;
  if (image) {
    const iw = image.naturalWidth || image.width, ih = image.naturalHeight || image.height;
    if (!(iw > 0 && ih > 0)) throw new Error('海报图片还未加载完成，请稍后重试。');
    const box = { x: 65, y: 681, w: 1070, h: 555 };
    const scale = Math.min(box.w / iw, box.h / ih);
    ctx.drawImage(image, box.x + (box.w - iw * scale) / 2, box.y + (box.h - ih * scale) / 2, iw * scale, ih * scale);
    ctx.strokeStyle = config.ink; ctx.lineWidth = 2; ctx.strokeRect(box.x, box.y, box.w, box.h);
  } else {
    // An editorial print study, rather than an invented illustration of the topic.
    ctx.save(); ctx.beginPath(); ctx.rect(64, 675, 1072, 520); ctx.clip();
    ctx.fillStyle = config.ink; ctx.font = `850 465px ${FONT}`; ctx.textBaseline = 'top';
    ctx.fillText(String(scene.title || '纸张').slice(0, 2), 38, 660);
    ctx.globalAlpha = .11;
    for (let y = 688; y < 1185; y += 16) for (let x = 70; x < 1125; x += 16) {
      ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  const body = scene.narration || (scene.items || []).join(' · ');
  printBlock(ctx, body, { x: 65, y: 1280, w: 1070, h: 335 }, { max: 42, min: 18, line: 1.30, color: config.ink });
  ctx.fillStyle = config.ink; ctx.fillRect(64, 1655, 1072, 3);
  printBlock(ctx, 'PRINT / CUT / REBUILD', { x: 65, y: 1687, w: 1070, h: 62 }, { max: 44, min: 28, weight: 650, color: config.ink });
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

function contrastInk(hex) {
  const rgb = String(hex).replace('#', '').match(/../g)?.map(v => parseInt(v, 16) / 255) || [0, 0, 0];
  const luminance = rgb.reduce((a, c, i) => a + [ .2126, .7152, .0722 ][i] * (c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4), 0);
  return luminance > .37 ? '#181716' : '#fffdf8';
}

function gridGeometry(nx, ny) {
  const count = (nx + 1) * (ny + 1), positions = new Float32Array(count * 3), uv = new Float32Array(count * 2), indices = [];
  for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
    const a = y * (nx + 1) + x, b = a + 1, c = a + nx + 1, d = c + 1;
    indices.push(a, b, c, b, d, c);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2).setUsage(THREE.DynamicDrawUsage));
  geometry.setIndex(indices);
  geometry.userData.grid = { nx, ny };
  return geometry;
}

function updateGrid(geometry, vertex) {
  const { nx, ny } = geometry.userData.grid, p = geometry.attributes.position, uv = geometry.attributes.uv;
  let k = 0;
  for (let y = 0; y <= ny; y++) for (let x = 0; x <= nx; x++, k++) {
    const v = vertex(x / nx, y / ny);
    p.setXYZ(k, v.x, v.y, v.z); uv.setXY(k, v.texU, v.texV);
  }
  p.needsUpdate = true; uv.needsUpdate = true;
  geometry.computeVertexNormals();
  // Geometry bounds move with the strip; avoiding stale frustum bounds also
  // makes arbitrary seeking reproduce the same frame as sequential encoding.
  geometry.boundingSphere = null;
}

function paperMesh(geometry, material) {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true; mesh.receiveShadow = true; mesh.frustumCulled = false;
  return mesh;
}

function makeRig(config) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(config.paper);
  const camera = new THREE.PerspectiveCamera(42, config.width / config.height, .05, 80);
  const canvas = canvasElement(config.width, config.height);
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' }); }
  catch { throw new Error('三维纸张电影需要 WebGL 2。请开启浏览器图形加速，或切换到文字动画模式。'); }
  renderer.setPixelRatio(1); renderer.setSize(config.width, config.height, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  scene.add(new THREE.HemisphereLight('#ffffff', '#c4b8a8', 2.25));
  const key = new THREE.DirectionalLight('#fff7eb', 3.2);
  key.position.set(-3.5, 6, 7); key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024); key.shadow.bias = -.0006; key.shadow.normalBias = .025;
  Object.assign(key.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: .1, far: 24 });
  key.target.position.set(0, -.5, 0); scene.add(key, key.target);
  const rim = new THREE.DirectionalLight('#dae6ff', 1.6); rim.position.set(3, 2, -4); scene.add(rim);
  const paper = new THREE.MeshStandardMaterial({ color: '#ffffff', side: THREE.DoubleSide, roughness: .75, metalness: 0 });
  const plainPaper = paper.clone();
  const poster = new THREE.Group(), cascade = new THREE.Group(), machine = new THREE.Group();
  scene.add(poster, cascade, machine);
  const strips = Array.from({ length: STRIPS }, () => { const m = paperMesh(gridGeometry(40, 2), paper); poster.add(m); return m; });
  const ribbons = Array.from({ length: 29 }, (_, i) => { const m = paperMesh(gridGeometry(66, 3), i === 0 ? paper : plainPaper); cascade.add(m); return m; });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshStandardMaterial({ color: config.paper, roughness: 1 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -1.69; floor.receiveShadow = true; scene.add(floor);
  const stand = new THREE.Mesh(new THREE.PlaneGeometry(15, 15), new THREE.ShadowMaterial({ opacity: .14 }));
  stand.position.z = -.18; stand.receiveShadow = true; poster.add(stand);
  const housing = new THREE.MeshStandardMaterial({ color: '#25292c', metalness: .42, roughness: .31 });
  const silver = new THREE.MeshStandardMaterial({ color: '#bec6cb', metalness: .65, roughness: .28 });
  const darkMetal = new THREE.MeshStandardMaterial({ color: '#52595d', metalness: .7, roughness: .34 });
  const accent = new THREE.MeshStandardMaterial({ color: config.accent, metalness: .24, roughness: .43 });
  const box = (w, h, d, x, y, z, material = housing) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material); mesh.position.set(x, y, z);
    mesh.castShadow = true; mesh.receiveShadow = true; machine.add(mesh); return mesh;
  };
  box(3.2, 1.3, .32, 0, -.77, -.62);
  box(.30, 1.4, 1.45, -1.45, -.75, 0); box(.30, 1.4, 1.45, 1.45, -.75, 0);
  box(2.6, .23, .30, 0, -.12, -.58, silver); box(2.6, .23, .25, 0, -.12, .58, silver);
  box(2.6, .19, .18, 0, -1.26, .65, housing);
  box(.76, .06, .018, -.65, -1.19, .76, accent);
  const gearShape = new THREE.Shape();
  for (let i = 0; i < 64; i++) {
    const a = i / 64 * Math.PI * 2, r = (i % 4 < 2 ? .243 : .209), x = Math.cos(a) * r, y = Math.sin(a) * r;
    if (!i) gearShape.moveTo(x, y); else gearShape.lineTo(x, y);
  }
  gearShape.closePath();
  const gearGeometry = new THREE.ExtrudeGeometry(gearShape, { depth: .052, steps: 1, bevelEnabled: false });
  gearGeometry.translate(0, 0, -.026); gearGeometry.rotateY(Math.PI / 2);
  const shafts = [];
  for (let row = 0; row < 2; row++) {
    const shaft = new THREE.Group(); shaft.position.set(0, -.26, row ? -.19 : .19); machine.add(shaft); shafts.push(shaft);
    const axle = new THREE.Mesh(new THREE.CylinderGeometry(.068, .068, 2.8, 20), darkMetal); axle.rotation.z = Math.PI / 2; shaft.add(axle);
    for (let lane = 0; lane < LANES; lane++) {
      const gear = new THREE.Mesh(gearGeometry, silver);
      gear.position.x = -1.05 + (lane + (row ? .5 : 0)) * (2.1 / LANES);
      gear.rotation.x = lane % 2 ? .098 : 0; gear.castShadow = true; gear.receiveShadow = true; shaft.add(gear);
    }
  }
  // A real motor and six visible fasteners give the cutaway depth and scale.
  const motor = new THREE.Mesh(new THREE.CylinderGeometry(.27, .27, .48, 32), darkMetal);
  motor.rotation.z = Math.PI / 2; motor.position.set(1.79, -.68, -.23); motor.castShadow = true; machine.add(motor);
  for (const x of [-1.45, 1.45]) for (const y of [-.23, -.76, -1.23]) {
    const screw = new THREE.Mesh(new THREE.CylinderGeometry(.043, .043, .018, 12), silver);
    screw.rotation.x = Math.PI / 2; screw.position.set(x, y, .737); machine.add(screw);
  }
  const feed = paperMesh(gridGeometry(10, 50), paper); machine.add(feed);
  const output = Array.from({ length: LANES }, () => { const m = paperMesh(gridGeometry(2, 56), paper); machine.add(m); return m; });
  const rig = { scene, camera, canvas, renderer, key, poster, cascade, machine, floor, strips, ribbons, shafts, feed, output, paper, plainPaper, housing, accent, textures: [], textureKey: null, width: config.width, height: config.height, colors: null };
  return rig;
}

function setPoster(rig, scene, config, index) {
  const key = posterKey(scene, config);
  if (rig.textureKey === key) return;
  const textures = [posterTexture(scene, config, index), posterTexture(scene, config, index, true)];
  for (const texture of rig.textures) texture.dispose();
  rig.textures = textures; rig.textureKey = key;
  rig.paper.map = textures[0]; rig.plainPaper.map = textures[1];
  rig.paper.needsUpdate = true; rig.plainPaper.needsUpdate = true;
}

function cameraAt(rig, position, target, roll = 0) {
  rig.camera.position.set(...position); rig.camera.up.set(0, 1, 0); rig.camera.lookAt(...target); rig.camera.rotateZ(roll);
}

function updatePoster(rig, phase, aspect) {
  for (let i = 0; i < STRIPS; i++) updateGrid(rig.strips[i].geometry, (u, v) => posterStripVertex(i, u, v, phase));
  const wide = aspect > 1;
  const z = wide ? 5.35 : 5.72;
  const push = phase.name === 'tear' ? ease(phase.progress) * .55 : mix(.24, 0, ease(phase.progress));
  cameraAt(rig, [0, .03, z - push], [0, phase.name === 'tear' ? ease(phase.progress) * .26 : .03, 0], -.015);
}

function updateCascade(rig, phase) {
  const t = phase.time;
  rig.ribbons.forEach((mesh, i) => {
    const hero = i === 0, layer = hero ? 3 : Math.floor((i - 1) / 10), row = (i - 1) % 10;
    const land = hero ? .20 : .08 + noise(i * 5) * 1.2;
    const drop = 1 - ease((t - land + .65) / .85);
    const width = hero ? .74 : .15 + noise(i * 2) * .07;
    updateGrid(mesh.geometry, (u, v) => {
      const s = u * 6.5, wave = Math.sin(s * (hero ? .9 : 1.5) + i * .8);
      return {
        x: s - 3.25 + (hero ? 0 : (noise(i) - .5) * .7) + drop * Math.sin(i) * .25,
        y: -1.63 + layer * .065 + (hero ? .12 : .06) + (wave * wave) * (hero ? .10 : .15) + drop * (2.8 + .5 * Math.sin(s * .7 + t * 2 + i)),
        z: (hero ? .63 : (row - 4.5) * .23) + (v - .5) * width + .04 * Math.sin(s * 1.7 + i + t * 1.3),
        texU: u, texV: hero ? mix(.68, .91, v) : mix(.02 + noise(i + 5) * .6, .12 + noise(i + 5) * .6, v),
      };
    });
  });
  const x = mix(-.9, .9, ease(phase.progress));
  cameraAt(rig, [x, 1.35, 4.0], [x, -.98, .2], -.20 - phase.progress * .08);
}

function updateMachine(rig, phase, aspect) {
  const u = ease(phase.progress), fed = Math.min(PAPER_H, .07 + u * 3.05), remain = PAPER_H - fed;
  rig.feed.visible = remain > .003;
  if (rig.feed.visible) updateGrid(rig.feed.geometry, (x, y) => ({
    x: (x - .5) * PAPER_W,
    y: -.15 + y * remain,
    z: Math.sin(y * Math.PI) * .055 + Math.sin(x * 5 + phase.time) * .008 * y,
    texU: x, texV: fed / PAPER_H + y * (1 - fed / PAPER_H),
  }));
  rig.output.forEach((mesh, lane) => {
    mesh.visible = fed > .08;
    if (mesh.visible) updateGrid(mesh.geometry, (x, y) => feedPaperVertex(lane, x, y, fed, phase.time));
  });
  rig.shafts[0].rotation.x = -phase.time * 5.5; rig.shafts[1].rotation.x = phase.time * 5.5;
  const dive = ease((phase.progress - .30) / .62), wide = aspect > 1;
  cameraAt(rig, [mix(1.6, .85, dive), mix(1.55, -.65, dive), wide ? 7.3 : mix(7.3, 6.65, dive)],
    [mix(.06, .1, dive), mix(.13, -1.18, dive), 0], mix(.01, -.055, dive));
}

/** Draw into an existing 2D canvas without replacing its context. */
export function drawPaperFilm(targetCanvas, { scenes = [], settings = {} }, time = 0) {
  const config = { ...DEFAULTS, ...settings };
  config.width = Number(config.width); config.height = Number(config.height);
  if (!(Number.isInteger(config.width) && Number.isInteger(config.height) && config.width >= 240 && config.height >= 240)) throw new Error('三维纸张画面尺寸无效。');
  const duration = scenes.length ? Math.max(...scenes.map(s => Number(s.end) || 0)) : 0;
  const now = clamp(Number(time) || 0, 0, Math.max(0, duration - .00001));
  const scene = scenes.find(s => now >= s.start && now < s.end) || scenes.at(-1);
  if (!scene) return { sceneIndex: -1, localTime: 0, duration: 0 };
  const local = now - scene.start, phase = paperFilmPhase(local, scene.duration);
  let rig = renderers.get(targetCanvas);
  if (!rig) { rig = makeRig(config); renderers.set(targetCanvas, rig); }
  if (rig.width !== config.width || rig.height !== config.height) {
    rig.renderer.setSize(config.width, config.height, false); rig.camera.aspect = config.width / config.height; rig.camera.updateProjectionMatrix();
    rig.width = config.width; rig.height = config.height;
  }
  const colors = JSON.stringify([config.paper, config.ink, config.accent]);
  if (colors !== rig.colors) {
    rig.scene.background.set(config.paper); rig.floor.material.color.set(config.paper); rig.accent.color.set(config.accent); rig.colors = colors;
  }
  const index = scene.index ?? scenes.indexOf(scene); setPoster(rig, scene, config, index);
  rig.poster.visible = phase.name === 'tear' || phase.name === 'rebuild';
  rig.cascade.visible = phase.name === 'cascade'; rig.machine.visible = phase.name === 'shredder';
  rig.floor.visible = phase.name === 'cascade' || phase.name === 'shredder';
  rig.floor.position.y = phase.name === 'shredder' ? -3.48 : -1.69;
  const aspect = config.width / config.height;
  if (rig.poster.visible) updatePoster(rig, phase, aspect);
  else if (rig.cascade.visible) updateCascade(rig, phase);
  else updateMachine(rig, phase, aspect);
  rig.renderer.render(rig.scene, rig.camera);
  if (targetCanvas.width !== config.width) targetCanvas.width = config.width;
  if (targetCanvas.height !== config.height) targetCanvas.height = config.height;
  const ctx = targetCanvas.getContext('2d');
  if (!ctx) throw new Error('无法把三维纸张画面绘制到视频画布。');
  ctx.save();
  try { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.drawImage(rig.canvas, 0, 0); }
  finally { ctx.restore(); }
  return { sceneIndex: index, localTime: local, duration };
}

/** Release the private GL context as well as all textures/materials/geometries. */
export function disposePaperFilm(targetCanvas) {
  const rig = renderers.get(targetCanvas); if (!rig) return;
  const geometries = new Set(), materials = new Set();
  rig.scene.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach(m => materials.add(m));
    object.shadow?.dispose?.();
  });
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  for (const texture of rig.textures) texture.dispose();
  rig.renderer.dispose(); rig.renderer.forceContextLoss(); renderers.delete(targetCanvas);
}
