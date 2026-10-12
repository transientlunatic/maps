// Names of lochs and other bodies of water, drawn along each water body's
// main axis. Reads the GeoJSON written by `make waternames` (one line per
// water body, with `name` and `length_m`) and draws each name as SVG text on
// its line, so the text uses the page's own fonts.
//
// Needs Leaflet and Leaflet.TextPath (npm: leaflet-textpath) to be loaded first.
//
//   import { WaterNames } from './water-names.js';
//   new WaterNames('https://tiles.example.org/waternames/v1.0/water-names.geojson').addTo(map);

// Smallest water body labelled at each zoom (length of its axis, in metres),
// and the text style for each size of water body.
const MIN_LENGTH_BY_ZOOM = [[12, 0], [11, 1000], [10, 3000], [8, 8000]];
const STYLES = [
  { minLength: 8000, size: 15, spacing: 2 },
  { minLength: 3000, size: 13, spacing: 1.3 },
  { minLength: 1000, size: 12, spacing: 0.7 },
  { minLength: 0, size: 11, spacing: 0 },
];

function minLengthAt(zoom) {
  for (const [z, length] of MIN_LENGTH_BY_ZOOM) {
    if (zoom >= z) return length;
  }
  return Infinity;
}

export const WaterNames = L.Layer.extend({
  options: {
    color: '#28649a',
    fontFamily: 'Lato, sans-serif',
    attribution: '',
  },

  initialize(url, options) {
    this._url = url;
    L.setOptions(this, options);
    this._features = [];
  },

  onAdd(map) {
    this._group = L.layerGroup().addTo(map);
    map.on('moveend', this._update, this);
    if (this._loaded) {
      this._update();
    } else {
      this._loaded = fetch(this._url)
        .then((r) => r.json())
        .then((geojson) => {
          this._features = geojson.features.map((f) => {
            const latlngs = f.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
            return {
              name: f.properties.name,
              length: f.properties.length_m,
              latlngs,
              bounds: L.latLngBounds(latlngs),
            };
          });
          if (this._map) this._update();
        });
    }
  },

  onRemove(map) {
    map.off('moveend', this._update, this);
    this._group.remove();
  },

  // Redraw the labels that are on screen and big enough for this zoom. The
  // set is small, so rebuilding it after each move is cheap.
  _update() {
    const map = this._map;
    const minLength = minLengthAt(map.getZoom());
    const view = map.getBounds().pad(0.3);
    this._group.clearLayers();

    for (const f of this._features) {
      if (f.length < minLength || !view.intersects(f.bounds)) continue;
      const style = STYLES.find((s) => f.length >= s.minLength);
      const line = L.polyline(f.latlngs, { stroke: false, interactive: false });
      this._group.addLayer(line);
      line.setText(f.name, {
        center: true,
        offset: style.size * 0.35, // centre the text on the line
        attributes: {
          'font-family': this.options.fontFamily,
          'font-style': 'italic',
          'font-size': style.size,
          'letter-spacing': style.spacing,
          fill: this.options.color,
          stroke: '#fff',
          'stroke-width': 3,
          'stroke-opacity': 0.7,
          'stroke-linejoin': 'round',
          'paint-order': 'stroke',
          'pointer-events': 'none',
        },
      });
      // Drop names that do not fit along their line.
      if (line._textNode.getComputedTextLength() > line._path.getTotalLength() * 0.95) {
        this._group.removeLayer(line);
      }
    }
  },
});
