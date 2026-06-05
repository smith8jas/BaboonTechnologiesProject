import React from 'react';

const DEFAULT_EFFECT_RGB = '226, 236, 247';
const DEFAULT_BEAM_RGB = '6, 182, 212';
const TICKERS = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'GOOGL', 'FCF', 'ROIC', 'EPS', 'DCF'];

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

function randomTickerText() {
  const label = TICKERS[(Math.random() * TICKERS.length) | 0];
  const value = randomBetween(12, 420).toFixed(Math.random() > 0.5 ? 2 : 1);
  const signed = Math.random() > 0.5 ? '+' : '-';
  const change = `${signed}${randomBetween(0.1, 4.8).toFixed(1)}%`;
  return Math.random() > 0.48 ? `${label} ${value}` : `${label} ${change}`;
}

function makeStream(width, height) {
  return {
    x: randomBetween(24, Math.max(25, width - 90)),
    y: randomBetween(-height, height),
    speed: randomBetween(6, 18),
    text: randomTickerText(),
    nextUpdate: randomBetween(0.8, 2.8),
  };
}

function makeCandle(width, height) {
  const high = randomBetween(18, 58);
  const body = randomBetween(8, Math.max(10, high - 8));
  const y = randomBetween(96, Math.max(120, height - 130));
  return {
    age: 0,
    body,
    high,
    ttl: randomBetween(4.8, 8.5),
    up: Math.random() > 0.5,
    width: randomBetween(8, 13),
    x: randomBetween(36, Math.max(40, width - 42)),
    y,
  };
}

export default function ChatDataBackground() {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let width = 0;
    let height = 0;
    let rafId = 0;
    let lastTime = performance.now();
    let streams = [];
    let candles = [];
    let effectRgb = DEFAULT_EFFECT_RGB;
    let beamRgb = DEFAULT_BEAM_RGB;

    function readThemeColors() {
      const styles = window.getComputedStyle(document.documentElement);
      effectRgb = styles.getPropertyValue('--chat-bg-effect-rgb').trim() || DEFAULT_EFFECT_RGB;
      beamRgb = styles.getPropertyValue('--chat-bg-beam-rgb').trim() || DEFAULT_BEAM_RGB;
      if (reduceMotion) draw(0, 0);
    }

    function buildScene() {
      const streamCount = Math.max(8, Math.min(24, Math.round(width / 70)));
      streams = Array.from({ length: streamCount }, () => makeStream(width, height));
      candles = Array.from({ length: Math.max(3, Math.round(width / 340)) }, () => makeCandle(width, height));
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildScene();
      draw(0, 0);
    }

    function drawStreams(delta) {
      ctx.font = '11px "DM Mono", "SFMono-Regular", Consolas, monospace';
      ctx.textBaseline = 'top';

      for (const stream of streams) {
        stream.y += stream.speed * delta;
        stream.nextUpdate -= delta;

        if (stream.nextUpdate <= 0) {
          stream.text = randomTickerText();
          stream.nextUpdate = randomBetween(1.2, 3.4);
        }

        if (stream.y > height + 24) {
          Object.assign(stream, makeStream(width, height), { y: randomBetween(-90, -16) });
        }

        ctx.fillStyle = `rgba(${effectRgb}, 0.045)`;
        ctx.fillText(stream.text, stream.x, stream.y);
      }
    }

    function drawCandles(delta) {
      if (!reduceMotion && candles.length < 12 && Math.random() < 0.012) {
        candles.push(makeCandle(width, height));
      }

      candles = candles.filter((candle) => {
        candle.age += delta;
        return candle.age <= candle.ttl;
      });

      for (const candle of candles) {
        const fade = Math.sin((Math.PI * candle.age) / candle.ttl);
        const alpha = Math.max(0, fade) * 0.052;
        const centerX = candle.x + candle.width / 2;
        const wickTop = candle.y - candle.high / 2;
        const wickBottom = candle.y + candle.high / 2;
        const bodyTop = candle.up ? candle.y - candle.body / 2 : candle.y - candle.body / 3;
        const bodyHeight = candle.body;

        ctx.strokeStyle = `rgba(${effectRgb}, ${alpha})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(centerX, wickTop);
        ctx.lineTo(centerX, wickBottom);
        ctx.stroke();
        ctx.strokeRect(candle.x, bodyTop, candle.width, bodyHeight);
      }
    }

    function drawBeam(time) {
      const beamWidth = 140;
      const x = ((time * 42) % (width + beamWidth * 2)) - beamWidth;
      const gradient = ctx.createLinearGradient(x, 0, x + beamWidth, 0);
      gradient.addColorStop(0, `rgba(${beamRgb}, 0)`);
      gradient.addColorStop(0.5, `rgba(${beamRgb}, 0.04)`);
      gradient.addColorStop(1, `rgba(${beamRgb}, 0)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(x, 0, beamWidth, height);
    }

    function draw(delta, time) {
      ctx.clearRect(0, 0, width, height);
      drawStreams(delta);
      drawCandles(delta);
      drawBeam(time);
    }

    function step(now) {
      const delta = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;
      draw(delta, now / 1000);
      rafId = requestAnimationFrame(step);
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

    if (!reduceMotion) {
      rafId = requestAnimationFrame(step);
    }

    return () => {
      cancelAnimationFrame(rafId);
      themeObserver.disconnect();
      if (resizeObserver) resizeObserver.disconnect();
      else window.removeEventListener('resize', resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="chat-data-background" aria-hidden="true" />;
}
