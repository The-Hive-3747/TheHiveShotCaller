// Replay viewer. Field frame in inches: X toward audience, Y along beam, Z up.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const BALL_RADIUS_IN = { pollen: 1.4, nectar: 1.8 };

function label(text, color = '#ffffff') {
  const c = document.createElement('canvas');
  c.width = 128; c.height = 64;
  const g = c.getContext('2d');
  g.font = 'bold 40px sans-serif';
  g.fillStyle = color;
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, 64, 32);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
  sp.scale.set(14, 7, 1);
  return sp;
}

function lineFrom(points, material) {
  const geo = new THREE.BufferGeometry().setFromPoints(points.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
  const l = new THREE.Line(geo, material);
  if (material.isLineDashedMaterial) l.computeLineDistances();
  return l;
}

export class ReplayViewer {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    container.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0b0d10);
    this.camera = new THREE.PerspectiveCamera(45, 1, 1, 2000);
    this.camera.up.set(0, 0, 1);            // Z up (set before OrbitControls)
    this.camera.position.set(170, -150, 120);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0, 30);
    this.controls.update();
    this.scene.add(new THREE.AmbientLight(0xffffff, 1.0));

    this.staticGroup = new THREE.Group();   // floor, axes
    this.fieldGroup = new THREE.Group();    // hive wireframe + cells
    this.shotGroup = new THREE.Group();     // robot, tracks, ball
    this.scene.add(this.staticGroup, this.fieldGroup, this.shotGroup);
    this._buildStatic();

    this.shot = null;
    this.playing = false;
    this.speed = 1;
    this.progress = 0;                      // 0..1
    this.duration = 1;
    this.onProgress = null;                 // callback(progress, playing)
    this._last = performance.now();
    this._raf = null;
    this._visible = false;
    this.follow = false;
    window.addEventListener('resize', () => this.resize());
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this._loop = this._loop.bind(this);
  }

  _buildStatic(size = 144) {
    // size = inside wall to inside wall (config field_size_in, served as geometry.field_size)
    const g = this.staticGroup;
    while (g.children.length) g.remove(g.children[0]);
    this._fieldSize = size;
    const h = size / 2;
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(size, size),
      new THREE.MeshBasicMaterial({ color: 0x1a2230, side: THREE.DoubleSide }));
    floor.position.z = -0.05;
    g.add(floor);
    const pts = [];
    for (let v = -h; v <= h + 1e-6; v += 24) {
      pts.push(new THREE.Vector3(v, -h, 0), new THREE.Vector3(v, h, 0));
      pts.push(new THREE.Vector3(-h, v, 0), new THREE.Vector3(h, v, 0));
    }
    g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x3a465a })));
    const axis = (dir, color, text) => {
      const a = new THREE.ArrowHelper(dir, new THREE.Vector3(-h, -h, 0), 36, color, 6, 3);
      g.add(a);
      const s = label(text, '#' + color.toString(16).padStart(6, '0'));
      s.position.copy(dir.clone().multiplyScalar(44)).add(new THREE.Vector3(-h, -h, 0));
      g.add(s);
    };
    axis(new THREE.Vector3(1, 0, 0), 0xff5555, 'X (audience)');
    axis(new THREE.Vector3(0, 1, 0), 0x55ff55, 'Y (beam)');
    axis(new THREE.Vector3(0, 0, 1), 0x5599ff, 'Z (up)');
  }

  setField(geom) {
    const g = this.fieldGroup;
    while (g.children.length) g.remove(g.children[0]);
    if (!geom) return;
    if (geom.field_size && geom.field_size !== this._fieldSize) this._buildStatic(geom.field_size);
    const pos = [];
    for (const [a, b] of geom.wireframe || []) pos.push(new THREE.Vector3(...a), new THREE.Vector3(...b));
    g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pos),
      new THREE.LineBasicMaterial({ color: 0xaab4c4 })));
    for (const [alliance, hive] of Object.entries(geom.hives || {})) {
      const col = alliance === 'red' ? 0xf85149 : 0x4c8dff;
      for (const [, cell] of Object.entries(hive.cells || {})) {
        const poly = cell.opening;
        if (!poly || poly.length < 3) continue;
        const loop = poly.concat([poly[0]]);
        g.add(lineFrom(loop, new THREE.LineBasicMaterial({ color: col })));
        if (cell.is_up) {
          const shape = new THREE.BufferGeometry();
          const v = [];
          for (let i = 1; i < poly.length - 1; i++) v.push(...poly[0], ...poly[i], ...poly[i + 1]);
          shape.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
          g.add(new THREE.Mesh(shape, new THREE.MeshBasicMaterial({
            color: 0xf5b301, transparent: true, opacity: 0.45, side: THREE.DoubleSide })));
        }
      }
    }
  }

  setRobot(robot) { this.robotCfg = robot || { length: 18, width: 18, height: 18, launch_exit_height: 12 }; }

  clearShot() {
    while (this.shotGroup.children.length) this.shotGroup.remove(this.shotGroup.children[0]);
    this.ball = null;
  }

  showShot(shot) {
    this.clearShot();
    this.shot = shot;
    this.progress = 0;
    this.playing = false;
    const track = (shot && shot.track) || [];
    if (!track.length) { this._emit(); return; }
    const t0 = track[0].t;
    this.duration = Math.max(1e-3, track[track.length - 1].t - t0);
    const robot = this.robotCfg || { length: 18, width: 18, height: 18, launch_exit_height: 12 };
    const first = track[0];
    const lp = shot.launch_point || [first.x, first.y, first.z];
    // horizontal shot direction from the measured track
    const last = track[track.length - 1];
    let dx = last.x - first.x; let dy = last.y - first.y;
    const dn = Math.hypot(dx, dy) || 1; dx /= dn; dy /= dn;
    this.dir = [dx, dy];
    this.launch = lp;

    // robot box: bottom on floor, long side along shot direction, launcher exit at lp
    const box = new THREE.Mesh(new THREE.BoxGeometry(robot.length, robot.width, robot.height),
      new THREE.MeshBasicMaterial({ color: 0x66707f, transparent: true, opacity: 0.35 }));
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry),
      new THREE.LineBasicMaterial({ color: 0xb0bac8 }));
    const rb = new THREE.Group();
    rb.add(box, edges);
    rb.position.set(lp[0], lp[1], robot.height / 2);
    rb.rotation.z = Math.atan2(dy, dx);
    this.shotGroup.add(rb);
    const exitMark = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8),
      new THREE.MeshBasicMaterial({ color: 0xffffff }));
    exitMark.position.set(lp[0], lp[1], lp[2]);
    this.shotGroup.add(exitMark);

    // measured track: solid
    this.shotGroup.add(lineFrom(track.map((p) => [p.x, p.y, p.z]), new THREE.LineBasicMaterial({ color: 0xf5b301 })));
    for (const p of track) {
      const d = new THREE.Mesh(new THREE.SphereGeometry(0.5, 6, 4), new THREE.MeshBasicMaterial({ color: 0xf5b301 }));
      d.position.set(p.x, p.y, p.z);
      this.shotGroup.add(d);
    }
    // fitted parabola ghost: dashed. z = a s^2 + b s + c, s = horizontal distance from launch point
    const par = shot.parabola;
    if (par) {
      const smax = Math.hypot(last.x - lp[0], last.y - lp[1]) * 1.05 + 1;
      const pts = [];
      for (let i = 0; i <= 60; i++) {
        const s = (smax * i) / 60;
        pts.push([lp[0] + dx * s, lp[1] + dy * s, par.a * s * s + par.b * s + par.c]);
      }
      this.shotGroup.add(lineFrom(pts, new THREE.LineDashedMaterial({ color: 0x4cc9f0, dashSize: 3, gapSize: 2 })));
    }
    // ball
    const r = BALL_RADIUS_IN[String(shot.ball_type || '').toLowerCase()] || BALL_RADIUS_IN.pollen;
    this.ball = new THREE.Mesh(new THREE.SphereGeometry(r, 20, 14),
      new THREE.MeshBasicMaterial({ color: shot.ball_type === 'nectar' ? 0xff8c42 : 0xffe14d }));
    this.shotGroup.add(this.ball);
    this._place();
    this._emit();
  }

  _place() {
    const track = this.shot && this.shot.track;
    if (!track || !track.length || !this.ball) return;
    const t = track[0].t + this.progress * this.duration;
    let i = 0;
    while (i < track.length - 2 && track[i + 1].t < t) i++;
    const a = track[i]; const b = track[Math.min(i + 1, track.length - 1)];
    const span = b.t - a.t;
    const u = span > 0 ? Math.min(1, Math.max(0, (t - a.t) / span)) : 0;
    this.ball.position.set(a.x + (b.x - a.x) * u, a.y + (b.y - a.y) * u, a.z + (b.z - a.z) * u);
  }

  _emit() { if (this.onProgress) this.onProgress(this.progress, this.playing); }

  play() {
    if (!this.shot) return;
    if (this.progress >= 1) this.progress = 0;
    this.playing = true; this._last = performance.now(); this._emit();
  }
  pause() { this.playing = false; this._emit(); }
  toggle() { if (this.playing) this.pause(); else this.play(); }
  setProgress(p) { this.progress = Math.min(1, Math.max(0, p)); this._place(); }
  setSpeed(s) { this.speed = s; }
  setFollow(on) { this.follow = !!on; }

  resize() {
    const w = this.container.clientWidth || 600; const h = this.container.clientHeight || 400;
    if (this._w === w && this._h === h) return;
    this._w = w; this._h = h;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  // call when the tab becomes visible/hidden
  setVisible(v) {
    this._visible = v;
    if (v) { this.resize(); cancelAnimationFrame(this._raf); this._last = performance.now(); this._raf = requestAnimationFrame(this._loop); }
    else cancelAnimationFrame(this._raf);
  }

  _loop(now) {
    if (!this._visible) return;
    const dt = (now - this._last) / 1000; this._last = now;
    if (this.playing) {
      this.progress += (dt * this.speed) / this.duration;
      if (this.progress >= 1) { this.progress = 1; this.playing = false; }
      this._place(); this._emit();
    }
    if (this.follow && this.ball) {   // keep the orbit offset, move the pivot with the ball
      const d = this.ball.position.clone().sub(this.controls.target);
      this.controls.target.add(d); this.camera.position.add(d);
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this._raf = requestAnimationFrame(this._loop);
  }
}
