// The hills, drawn in the browser. Reads the JSON that `make hills` writes from the Database of
// British and Irish Hills and draws each hill as a marker and a name on a canvas over the map.
//
// Compared with tiles this gives crisp markers and text at any pixel density, names in the page's
// own fonts, hills you can hover and click, lists you can switch on and off, and no rendering:
// the 13,000 hills in Scotland and the north of England are 275 kB compressed.
//
// Hills are placed most important first and a marker or name that would land on one already
// placed is dropped, so the map stays readable at every zoom. Which hills show at a zoom is set in
// hill-markers.js.
//
// Needs Leaflet.
//
//   import { HillsLayer } from './hills.js';
//   const hills = new HillsLayer('https://tiles.example.org/hills/v1.0/hills.json').addTo(map);
//   hills.setFamilies(['munro', 'corbett']);   // optional: only these lists

import { FAMILIES, LIST_NAMES, drawMarker, familyOf, pixelSize } from './hill-markers.js';

const FEET_PER_METRE = 3.28084;

// Hills with a name like "Ben Nevis [Beinn Nibheis]" are drawn as "Ben Nevis"
const shortName = (name) => name.replace(/\s*\[.*\]\s*$/, '');
const gaelicName = (name) => (name.match(/\[(.*)\]/) || [])[1];

export const HillsLayer = L.Layer.extend({
  options: {
    fontFamily: 'Lato, sans-serif',
    color: '#1f2328',
    maxLabelWidth: 150,
    attribution: 'Hills: <a href="https://www.hills-database.co.uk">Database of British and Irish Hills</a>',
  },

  initialize(url, options) {
    this._url = url;
    L.setOptions(this, options);
    this._hills = [];
    this._placed = [];
    this._enabled = null; // null means every list
  },

  /** Show only these lists (ids from FAMILIES in hill-markers.js), or every list for null. */
  setFamilies(ids) {
    this._enabled = ids ? new Set(ids) : null;
    if (this._map) this._redraw();
    return this;
  },

  onAdd(map) {
    this._canvas = L.DomUtil.create('canvas', 'leaflet-hills-layer');
    this._canvas.style.position = 'absolute';
    this._canvas.style.pointerEvents = 'none';
    map.getPanes().overlayPane.appendChild(this._canvas);
    map.on('moveend zoomend resize', this._redraw, this);
    map.on('zoomstart', this._clear, this);
    map.on('mousemove', this._hover, this);
    map.on('click', this._click, this);
    if (this._loaded) {
      this._redraw();
    } else {
      this._loaded = fetch(this._url)
        .then((r) => r.json())
        .then((data) => {
          this._hills = data.hills.map(([lon, lat, name, metres, drop, lists, id, country]) => ({
            latlng: L.latLng(lat, lon), name, metres, drop, lists, id, country, family: familyOf(lists),
          }));
          if (this._map) this._redraw();
        });
    }
  },

  onRemove(map) {
    map.off('moveend zoomend resize', this._redraw, this);
    map.off('zoomstart', this._clear, this);
    map.off('mousemove', this._hover, this);
    map.off('click', this._click, this);
    this._tooltip && this._tooltip.remove();
    L.DomUtil.remove(this._canvas);
    this._placed = [];
  },

  _clear() {
    this._canvas.getContext('2d').clearRect(0, 0, this._canvas.width, this._canvas.height);
    this._placed = [];
  },

  _redraw() {
    const map = this._map;
    const size = map.getSize();
    const dpr = window.devicePixelRatio || 1;
    const canvas = this._canvas;
    canvas.width = size.x * dpr;
    canvas.height = size.y * dpr;
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;
    // The canvas covers the visible map, so put it where the top left of the map now is
    L.DomUtil.setPosition(canvas, map._getMapPanePos().multiplyBy(-1));

    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    this._placed = [];

    const zoom = map.getZoom();
    const pad = 30;
    const view = map.getBounds();
    const north = view.getNorth() + 0.05, south = view.getSouth() - 0.05;
    const east = view.getEast() + 0.1, west = view.getWest() - 0.1;
    const scale = zoom >= 12 ? 1.1 : 1;

    const occupied = []; // rectangles [x0, y0, x1, y1] already taken, markers and names alike
    const hit = (r) => occupied.some((o) => r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1]);

    // Most important families first, and the highest hills first within each
    const candidates = this._hills.filter((h) => {
      const f = h.family;
      if (zoom < f.minZoom) return false;
      if (this._enabled && !this._enabled.has(f.id)) return false;
      const { lat, lng } = h.latlng;
      return lat < north && lat > south && lng < east && lng > west;
    });
    candidates.sort((a, b) => FAMILIES.indexOf(a.family) - FAMILIES.indexOf(b.family) || b.metres - a.metres);

    const markers = [];
    const labels = [];
    for (const h of candidates) {
      const p = map.latLngToContainerPoint(h.latlng);
      if (p.x < -pad || p.y < -pad || p.x > size.x + pad || p.y > size.y + pad) continue;
      const r = pixelSize(h.family, scale) / 2 + 2;
      const box = [p.x - r, p.y - r, p.x + r, p.y + r];
      if (hit(box)) continue;
      occupied.push(box);
      markers.push({ h, x: p.x, y: p.y });
      this._placed.push({ h, x: p.x, y: p.y, r: Math.max(r, 8) });
    }

    // Names, in the same order, to the right of the marker or else to the left
    ctx.textBaseline = 'middle';
    for (const m of markers) {
      const f = m.h.family;
      if (zoom < f.labelZoom) continue;
      const big = f.size >= 4;
      const px = big ? 13 : 11.5;
      ctx.font = `${big ? '700 ' : '400 '}${px}px ${this.options.fontFamily}`;
      const text = shortName(m.h.name);
      const width = Math.min(ctx.measureText(text).width, this.options.maxLabelWidth);
      const half = pixelSize(f, scale) / 2 + 3;
      const showHeight = zoom >= 11 && big;
      const lineH = px + 1;
      let placed = null;
      for (const side of [1, -1]) {
        const x0 = side === 1 ? m.x + half : m.x - half - width;
        const rect = [x0 - 1, m.y - lineH / 2 - 1, x0 + width + 1, m.y + lineH / 2 + (showHeight ? lineH - 2 : 0) + 1];
        if (!hit(rect)) { placed = { x0, rect, side }; break; }
      }
      if (!placed) continue;
      occupied.push(placed.rect);
      labels.push({ text, x0: placed.x0, y: m.y, px, big, width, height: showHeight ? `${m.h.metres} m` : null, lineH });
    }

    for (const m of markers) drawMarker(ctx, m.h.family, m.x, m.y, scale);
    ctx.textAlign = 'left';
    for (const l of labels) {
      ctx.font = `${l.big ? '700 ' : '400 '}${l.px}px ${this.options.fontFamily}`;
      ctx.lineJoin = 'round';
      ctx.strokeStyle = 'rgba(255,255,255,0.85)';
      ctx.lineWidth = 3;
      ctx.fillStyle = this.options.color;
      ctx.strokeText(l.text, l.x0, l.y, this.options.maxLabelWidth);
      ctx.fillText(l.text, l.x0, l.y, this.options.maxLabelWidth);
      if (l.height) {
        ctx.font = `400 ${l.px - 2}px ${this.options.fontFamily}`;
        ctx.strokeText(l.height, l.x0, l.y + l.lineH - 1);
        ctx.fillText(l.height, l.x0, l.y + l.lineH - 1);
      }
    }
  },

  /** The marker under a point of the map container, or null. */
  _hillAt(containerPoint) {
    let best = null;
    let bestD = Infinity;
    for (const p of this._placed) {
      const d = Math.hypot(p.x - containerPoint.x, p.y - containerPoint.y);
      if (d <= p.r && d < bestD) { best = p; bestD = d; }
    }
    return best && best.h;
  },

  _hover(e) {
    const h = this._hillAt(e.containerPoint);
    this._map.getContainer().style.cursor = h ? 'pointer' : '';
    if (!h) {
      this._tooltip && this._tooltip.remove();
      this._tooltip = null;
      return;
    }
    if (this._tooltipHill === h && this._tooltip) return;
    this._tooltipHill = h;
    this._tooltip && this._tooltip.remove();
    this._tooltip = L.tooltip({ direction: 'top', offset: [0, -8], className: 'hill-tooltip' })
      .setLatLng(h.latlng)
      .setContent(`<strong>${shortName(h.name)}</strong> ${h.metres} m`)
      .addTo(this._map);
  },

  _click(e) {
    const h = this._hillAt(e.containerPoint);
    if (!h) return;
    const gaelic = gaelicName(h.name);
    const lists = h.lists ? h.lists.split(' ').map((c) => LIST_NAMES[c] || c).join(', ') : 'not on a main list';
    const link = `https://www.hill-bagging.co.uk/mountaindetails.php?qu=${h.country || 'S'}&rf=${h.id}`;
    L.popup({ offset: [0, -6] })
      .setLatLng(h.latlng)
      .setContent(
        `<strong>${shortName(h.name)}</strong>${gaelic ? ` <em>${gaelic}</em>` : ''}<br>` +
        `${h.metres} m (${Math.round(h.metres * FEET_PER_METRE).toLocaleString('en-GB')} ft), drop ${h.drop} m<br>` +
        `${lists}<br><a href="${link}" target="_blank" rel="noopener">Hill-bagging page</a>`
      )
      .openOn(this._map);
  },
});
