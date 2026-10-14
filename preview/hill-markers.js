// The hill markers: which list a hill is shown as, and how each kind is drawn.
//
// The markers for the lists that the tile layer already drew are the same ones, taken from
// styling/Database of British and Irish Hills.qml: a triangle for a Munro, a circle for a
// Corbett, a hexagon for a Graham, a diamond for a Donald, a pentagon for a Wainwright, with a
// hollow version for each kind of top. The lists it never had a marker for are new, and use the
// shapes that are still free: squares for the lists about prominence (Marilyns, HuMPs), a cross
// for Simms, a hollow pentagon for Hewitts and Nuttalls, and a small dot for the rest.
//
// A hill is shown as the most important list it is on (the order of FAMILIES). Used by hills.js
// and by hill-markers.html, which shows the whole set.

const INK = '#232323';   // the QGIS symbols' 35,35,35
const GREY = '#5d6670';
const PX_PER_MM = 2.8;   // the symbols are sized in mm in the QGIS style; this is about the size the tiles drew them

// In order of importance. `size` is the marker's width in millimetres of the QGIS style (as in the
// style), `hollow` markers have a white centre and a dark outline, `minZoom` is the first zoom the
// markers are drawn at (the style's scale limits: 1:541,678 is zoom 9, 1:270,839 zoom 10, 1:135,419
// zoom 11) and `labelZoom` the first zoom they get a name. Donalds come before Corbetts and Grahams
// because every Donald is also one of those and the style draws the diamond on top.
export const FAMILIES = [
  { id: 'munro', label: 'Munro', lists: ['M'], shape: 'triangle', size: 5, minZoom: 9, labelZoom: 9 },
  { id: 'furth', label: 'Munro Furth', lists: ['F'], shape: 'triangle', size: 5, minZoom: 9, labelZoom: 10 },
  { id: 'munro-top', label: 'Munro top', lists: ['MT'], shape: 'triangle', hollow: true, size: 4, minZoom: 10, labelZoom: 11 },
  { id: 'donald', label: 'Donald', lists: ['D'], shape: 'diamond', size: 4.2, minZoom: 9, labelZoom: 10 },
  { id: 'donald-top', label: 'Donald top', lists: ['DT'], shape: 'diamond', hollow: true, size: 2.9, minZoom: 10, labelZoom: 12 },
  { id: 'corbett', label: 'Corbett', lists: ['C'], shape: 'circle', size: 4, minZoom: 9, labelZoom: 10 },
  { id: 'corbett-top', label: 'Corbett top', lists: ['CT'], shape: 'circle', hollow: true, size: 3, minZoom: 11, labelZoom: 12 },
  { id: 'graham', label: 'Graham', lists: ['G'], shape: 'hexagon', size: 4.4, minZoom: 9, labelZoom: 10 },
  { id: 'graham-top', label: 'Graham top', lists: ['GT'], shape: 'hexagon', hollow: true, size: 3, minZoom: 11, labelZoom: 12 },
  { id: 'wainwright', label: 'Wainwright', lists: ['W'], shape: 'pentagon', size: 4, minZoom: 10, labelZoom: 11 },
  { id: 'dillon', label: 'Dillon', lists: ['Dil'], shape: 'circle', size: 4, minZoom: 9, labelZoom: 10 },
  { id: 'munro-top-former', label: 'Former Munro top', lists: ['xMT'], shape: 'asterisk', hollow: true, size: 3, minZoom: 11, labelZoom: 12 },
  // New markers from here on
  { id: 'hewitt-nuttall', label: 'Hewitt, Nuttall', lists: ['Hew', 'N'], shape: 'pentagon', hollow: true, size: 3.4, minZoom: 10, labelZoom: 11, isNew: true },
  { id: 'marilyn', label: 'Marilyn', lists: ['Ma'], shape: 'square', color: GREY, size: 3, minZoom: 11, labelZoom: 12, isNew: true },
  { id: 'hump', label: 'HuMP', lists: ['Hu'], shape: 'square', hollow: true, color: GREY, size: 2.6, minZoom: 12, labelZoom: 13, isNew: true },
  { id: 'simm', label: 'Simm', lists: ['Sim'], shape: 'plus', color: GREY, size: 2.8, minZoom: 12, labelZoom: 13, isNew: true },
  { id: 'other', label: 'Other hill', lists: [], shape: 'dot', color: GREY, size: 1.5, minZoom: 13, labelZoom: 99, isNew: true },
];

export const LIST_NAMES = {
  M: 'Munro', MT: 'Munro top', xMT: 'Former Munro top', F: 'Munro Furth', C: 'Corbett', CT: 'Corbett top',
  G: 'Graham', GT: 'Graham top', D: 'Donald', DT: 'Donald top', Dil: 'Dillon', W: 'Wainwright',
  Hew: 'Hewitt', N: 'Nuttall', Ma: 'Marilyn', Hu: 'HuMP', Sim: 'Simm',
};

/** The marker's width in CSS pixels. */
export const pixelSize = (family, scale = 1) => family.size * PX_PER_MM * scale;

/** The family a hill is drawn as, from its string of list codes ("M Ma Sim"). */
export function familyOf(lists) {
  const codes = lists ? lists.split(' ') : [];
  return FAMILIES.find((f) => f.lists.length === 0 || f.lists.some((c) => codes.includes(c)));
}

function polygon(ctx, x, y, r, sides, rotation) {
  ctx.beginPath();
  for (let i = 0; i < sides; i++) {
    const a = rotation + (i * 2 * Math.PI) / sides;
    const px = x + r * Math.cos(a);
    const py = y + r * Math.sin(a);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

/** Draw one marker centred on (x, y), as the QGIS style does: a fill with a thin outline. */
export function drawMarker(ctx, family, x, y, scale = 1) {
  const w = pixelSize(family, scale);
  const r = w / 2;
  const ink = family.color || INK;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  if (family.shape === 'plus' || family.shape === 'asterisk') {
    // Strokes only: a white one under a dark one keeps them readable on dark ground
    const arms = family.shape === 'plus' ? [0, Math.PI / 2] : [0, Math.PI / 3, (2 * Math.PI) / 3];
    const draw = (style, width) => {
      ctx.strokeStyle = style;
      ctx.lineWidth = width;
      for (const a of arms) {
        ctx.beginPath();
        ctx.moveTo(x - r * Math.cos(a), y - r * Math.sin(a));
        ctx.lineTo(x + r * Math.cos(a), y + r * Math.sin(a));
        ctx.stroke();
      }
    };
    draw('rgba(255,255,255,0.95)', 3.4);
    draw(ink, 1.7);
    return;
  }

  const path = () => {
    switch (family.shape) {
      case 'triangle': {
        // QGIS's equilateral triangle: as wide as the size, point up, centred in its box
        const h = w * 0.866;
        ctx.beginPath();
        ctx.moveTo(x, y - h / 2);
        ctx.lineTo(x + r, y + h / 2);
        ctx.lineTo(x - r, y + h / 2);
        ctx.closePath();
        break;
      }
      case 'diamond': polygon(ctx, x, y, r * 1.12, 4, -Math.PI / 2); break;
      case 'hexagon': polygon(ctx, x, y, r * 1.02, 6, -Math.PI / 2); break;   // a point at the top, as in QGIS
      case 'pentagon': polygon(ctx, x, y, r * 1.05, 5, -Math.PI / 2); break;
      case 'square': ctx.beginPath(); ctx.rect(x - r * 0.88, y - r * 0.88, r * 1.76, r * 1.76); break;
      default: ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);   // circle, dot
    }
  };

  const edge = 0.4 * PX_PER_MM;   // the 0.4 mm outline of the style
  path();
  if (family.hollow) {
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = edge * 1.5;
    ctx.stroke();
  } else {
    ctx.fillStyle = ink;
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = edge;
    ctx.stroke();
  }
}
