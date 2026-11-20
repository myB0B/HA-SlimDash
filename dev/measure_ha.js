/* Measures the ORIGINAL cards in Home Assistant, to compare them with SlimDash.
   Open the view in a browser 600 px wide, paste this script into the console.
   One JSON line per card: type, box [x, y, width, height], texts
   [text, x, y, width, size, weight, colour], icons [kind, x, y, width, height, colour],
   background and radius of the card. Positions are relative to the card. */
(function () {
  function kids(n) {
    var a = [];
    if (n.shadowRoot) { a = a.concat([].slice.call(n.shadowRoot.childNodes)); }
    if (n.tagName === 'SLOT') { var as = n.assignedNodes(); if (as.length) { return a.concat(as); } }
    return a.concat([].slice.call(n.childNodes).filter(function (c) { return !(n.shadowRoot && c.assignedSlot); }));
  }
  function walk(n, f) { if (f(n) === false) { return; } kids(n).forEach(function (c) { walk(c, f); }); }
  var cards = [], R = Math.round;
  walk(document.body, function (n) {
    if (n.tagName === 'HUI-CARD' || n.tagName === 'HUI-BADGE') { cards.push(n); return false; }
  });
  var out = cards.map(function (c) {
    var r = c.getBoundingClientRect(), hc = null;
    var o = { t: (c.config && c.config.type) || c.tagName, b: [R(r.left), R(r.top + scrollY), R(r.width), R(r.height)], tx: [], ic: [] };
    walk(c, function (n) {
      if (n.nodeType === 3) {
        var s = n.textContent.trim();
        var p = n.parentElement || (n.parentNode && n.parentNode.host);
        if (!s || !p) { return; }
        var cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden') { return; }
        var rg = document.createRange(); rg.selectNodeContents(n);
        var q = rg.getBoundingClientRect();
        if (q.width) { o.tx.push([s.slice(0, 22), R(q.left - r.left), R(q.top - r.top), R(q.width), parseFloat(cs.fontSize), cs.fontWeight, cs.color.replace(/ /g, '')]); }
        return;
      }
      if (n.nodeType !== 1 || n.tagName === 'STYLE' || n.tagName === 'SCRIPT') { return n.nodeType === 1 ? false : undefined; }
      if (n.tagName === 'HA-CARD' && !hc) {
        hc = getComputedStyle(n);
        o.card = [hc.backgroundColor.replace(/ /g, ''), hc.borderRadius];
      }
      var tg = n.tagName;
      if (tg === 'HA-STATE-ICON' || tg === 'HA-ICON' || tg === 'HA-SVG-ICON' || tg === 'CANVAS' || tg === 'IMG' || tg === 'svg' || tg === 'HA-TILE-ICON') {
        var q2 = n.getBoundingClientRect();
        if (q2.width) { o.ic.push([tg.toLowerCase().replace('ha-', ''), R(q2.left - r.left), R(q2.top - r.top), R(q2.width), R(q2.height), getComputedStyle(n).color.replace(/ /g, '')]); }
        return tg === 'HA-TILE-ICON' ? undefined : false;
      }
    });
    return JSON.stringify(o);
  }).join('\n');
  console.log(out);
  return out;
})();
