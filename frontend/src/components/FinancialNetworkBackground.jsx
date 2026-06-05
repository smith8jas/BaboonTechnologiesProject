import React from 'react';

// Fallback rgb triplets. The live values come from CSS variables so light mode
// can use blue instead of inheriting the dark-mode cyan.
const DEFAULT_NODE_RGB = '34, 211, 238';
const DEFAULT_LINE_RGB = '6, 182, 212';

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// Smooth 0->1 ramp used to fade the whole field out toward the right side,
// so the report card on the right stays clean and visually dominant.
function smoothstep(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

/**
 * FinancialNetworkBackground
 * A calm, institutional "data network" rendered on a single canvas:
 * drifting accent-color nodes, sparse connecting lines, occasional pulses traveling
 * along a line, and a very subtle pointer parallax. Weighted to the left so
 * it sits behind the headline and fades out before the right-hand content.
 *
 * Sits absolutely behind hero content, never intercepts pointer events, and
 * fully respects prefers-reduced-motion.
 */
export default function FinancialNetworkBackground() {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let width = 0;
    let height = 0;
    let nodes = [];
    let pulses = [];
    let rafId = 0;
    let running = true;
    let nodeRgb = DEFAULT_NODE_RGB;
    let lineRgb = DEFAULT_LINE_RGB;

    // Eased pointer offset (px) -> eased toward target for smooth parallax.
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

    function readThemeColors() {
      const styles = window.getComputedStyle(document.documentElement);
      nodeRgb = styles.getPropertyValue('--network-node-rgb').trim() || DEFAULT_NODE_RGB;
      lineRgb = styles.getPropertyValue('--network-line-rgb').trim() || DEFAULT_LINE_RGB;
      if (reduceMotion) draw();
    }

    function connectDist() {
      return clamp(width * 0.16, 110, 170);
    }

    // 1 on the far left, fading to 0 by ~62% of the width.
    function leftWeight(x) {
      return 1 - smoothstep(0.2, 0.62, x / width);
    }

    function nodeCount() {
      const byArea = Math.round((width * height) / 22000);
      const cap = width < 700 ? 24 : 58;
      return clamp(byArea, 12, cap);
    }

    function spawnNode() {
      // Bias x toward the left (squared random) so density concentrates there.
      const r = Math.random();
      return {
        x: r * r * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.12,
        vy: (Math.random() - 0.5) * 0.12,
        r: 0.8 + Math.random() * 1.3,
      };
    }

    function buildNodes() {
      nodes = Array.from({ length: nodeCount() }, spawnNode);
      pulses = [];
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildNodes();
      if (reduceMotion) draw(); // single static frame
    }

    function spawnPulse() {
      const maxD = connectDist();
      for (let attempt = 0; attempt < 8; attempt += 1) {
        const a = nodes[(Math.random() * nodes.length) | 0];
        const b = nodes[(Math.random() * nodes.length) | 0];
        if (a === b) continue;
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < maxD && leftWeight((a.x + b.x) / 2) > 0.18) {
          pulses.push({ a, b, t: 0, speed: 0.004 + Math.random() * 0.0045 });
          return;
        }
      }
    }

    function draw() {
      ctx.clearRect(0, 0, width, height);
      const ox = pointer.x;
      const oy = pointer.y;
      const maxD = connectDist();

      // Connecting lines (closer = more opaque, faded toward the right).
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i += 1) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j += 1) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;
          if (d2 > maxD * maxD) continue;
          const w = leftWeight((a.x + b.x) / 2);
          if (w <= 0.02) continue;
          const alpha = (1 - Math.sqrt(d2) / maxD) * 0.16 * w;
          ctx.strokeStyle = `rgba(${lineRgb}, ${alpha})`;
          ctx.beginPath();
          ctx.moveTo(a.x + ox, a.y + oy);
          ctx.lineTo(b.x + ox, b.y + oy);
          ctx.stroke();
        }
      }

      // Pulses traveling along a line (brightest mid-line, fade at the ends).
      for (const p of pulses) {
        const x = p.a.x + (p.b.x - p.a.x) * p.t + ox;
        const y = p.a.y + (p.b.y - p.a.y) * p.t + oy;
        const alpha = (1 - Math.abs(0.5 - p.t) * 2) * 0.5 * leftWeight(x);
        if (alpha <= 0) continue;
        ctx.fillStyle = `rgba(${nodeRgb}, ${alpha})`;
        ctx.beginPath();
        ctx.arc(x, y, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }

      // Nodes: soft glow + small core.
      for (const n of nodes) {
        const w = leftWeight(n.x);
        if (w <= 0.02) continue;
        const x = n.x + ox;
        const y = n.y + oy;
        const a = 0.32 * w;
        const glow = ctx.createRadialGradient(x, y, 0, x, y, n.r * 4.5);
        glow.addColorStop(0, `rgba(${nodeRgb}, ${a})`);
        glow.addColorStop(1, `rgba(${nodeRgb}, 0)`);
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(x, y, n.r * 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = `rgba(${nodeRgb}, ${a + 0.18})`;
        ctx.beginPath();
        ctx.arc(x, y, n.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function step() {
      pointer.x += (pointer.tx - pointer.x) * 0.05;
      pointer.y += (pointer.ty - pointer.y) * 0.05;

      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < -24) n.x = width + 24;
        else if (n.x > width + 24) n.x = -24;
        if (n.y < -24) n.y = height + 24;
        else if (n.y > height + 24) n.y = -24;
      }

      draw();

      if (pulses.length < 4 && Math.random() < 0.018) spawnPulse();
      pulses = pulses.filter((p) => {
        p.t += p.speed;
        return p.t <= 1;
      });

      if (running) rafId = requestAnimationFrame(step);
    }

    function onPointerMove(e) {
      const rect = canvas.getBoundingClientRect();
      const nx = clamp((e.clientX - rect.left) / rect.width - 0.5, -0.5, 0.5);
      const ny = clamp((e.clientY - rect.top) / rect.height - 0.5, -0.5, 0.5);
      pointer.tx = nx * 14; // max ~7px parallax
      pointer.ty = ny * 10;
    }

    function resetPointer() {
      pointer.tx = 0;
      pointer.ty = 0;
    }

    function onVisibility() {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(rafId);
      } else if (!running) {
        running = true;
        rafId = requestAnimationFrame(step);
      }
    }

    readThemeColors();
    resize();

    const themeObserver = new MutationObserver(readThemeColors);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    let resizeObserver;
    if ('ResizeObserver' in window) {
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(canvas);
    } else {
      window.addEventListener('resize', resize);
    }

    if (reduceMotion) {
      return () => {
        themeObserver.disconnect();
        if (resizeObserver) resizeObserver.disconnect();
        else window.removeEventListener('resize', resize);
      };
    }

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerleave', resetPointer);
    document.addEventListener('visibilitychange', onVisibility);
    rafId = requestAnimationFrame(step);

    return () => {
      running = false;
      cancelAnimationFrame(rafId);
      themeObserver.disconnect();
      if (resizeObserver) resizeObserver.disconnect();
      else window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerleave', resetPointer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return <canvas ref={canvasRef} className="financial-network" aria-hidden="true" />;
}
