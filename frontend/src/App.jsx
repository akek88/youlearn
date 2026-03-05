import { useState, useEffect, useRef, useCallback } from 'react'

/* ─────────────────────────────────────────────
   Google Fonts injection
───────────────────────────────────────────── */
const fontLink = document.createElement('link')
fontLink.rel = 'stylesheet'
fontLink.href =
  'https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Space+Mono:wght@400;700&display=swap'
document.head.appendChild(fontLink)

/* ─────────────────────────────────────────────
   Global styles (injected once)
───────────────────────────────────────────── */
const globalCSS = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root {
    height: 100%;
    background: #0a0a0f;
    color: #e2e2f0;
    font-family: 'Noto Sans SC', sans-serif;
    font-size: 15px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #13131f; }
  ::-webkit-scrollbar-thumb { background: #3a2f6e; border-radius: 3px; }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }

  /* ── Metro timeline vertical track ── */
  .timeline-track { position: relative; }
  .timeline-track::before {
    content: '';
    position: absolute;
    left: 23px;
    top: 0; bottom: 0;
    width: 2px;
    background: linear-gradient(
      to bottom,
      transparent 0px,
      #1e1e30 28px,
      #1e1e30 calc(100% - 28px),
      transparent 100%
    );
    pointer-events: none;
  }

  /* ── Gradient scrollbar (timeline) ── */
  .timeline-scroll::-webkit-scrollbar { width: 5px; }
  .timeline-scroll::-webkit-scrollbar-track { background: #06060e; }
  .timeline-scroll::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #14b8a6 0%, #7c3aed 50%, #d97706 100%);
    border-radius: 3px;
    min-height: 48px;
  }
  .timeline-scroll::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, #2dd4bf 0%, #a78bfa 50%, #fbbf24 100%);
  }

  /* ── Active dot ripple ── */
  @keyframes ripple {
    0%   { box-shadow: 0 0 8px rgba(124,58,237,.7), 0 0 0 0   rgba(124,58,237,.5); }
    70%  { box-shadow: 0 0 8px rgba(124,58,237,.7), 0 0 0 7px rgba(124,58,237,0);  }
    100% { box-shadow: 0 0 8px rgba(124,58,237,.7), 0 0 0 0   rgba(124,58,237,0);  }
  }
  .dot-active { animation: ripple 1.8s ease-out infinite; }

  /* ── Alien welcome — motion animations ── */
  @keyframes alienFloat {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    30%       { transform: translateY(-14px) rotate(.4deg); }
    70%       { transform: translateY(-8px)  rotate(-.3deg); }
  }
  @keyframes alienGlow {
    0%, 100% { filter: drop-shadow(0 0 14px rgba(124,58,237,.45))
                       drop-shadow(0 0 32px rgba(79,70,229,.2)); }
    50%       { filter: drop-shadow(0 0 28px rgba(124,58,237,.9))
                       drop-shadow(0 0 60px rgba(124,58,237,.4)); }
  }
  @keyframes circuitBreath {
    0%, 100% { opacity: .38; }
    50%       { opacity: .85; }
  }
  @keyframes eyeShimmer {
    0%, 78%, 100% { opacity: 1; }
    84%            { opacity: .5; }
    88%            { opacity: 1; }
    92%            { opacity: .6; }
  }
  @keyframes scanLine {
    0%   { transform: translateY(-130px); opacity: 0; }
    8%   { opacity: .35; }
    92%  { opacity: .35; }
    100% { transform: translateY(145px); opacity: 0; }
  }
  .alien-svg  { animation: alienFloat 5.5s ease-in-out infinite,
                            alienGlow  3.5s ease-in-out infinite; }
  .alien-circ { animation: circuitBreath 2.8s ease-in-out infinite; }
  .alien-eyes { animation: eyeShimmer 6s ease-in-out infinite; }
  .alien-scan { animation: scanLine 5s linear 1.5s infinite; }
`
const styleTag = document.createElement('style')
styleTag.textContent = globalCSS
document.head.appendChild(styleTag)

/* ─────────────────────────────────────────────
   Inline style helpers
───────────────────────────────────────────── */
const S = {
  app: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },

  /* Header */
  header: {
    padding: '16px 40px',
    borderBottom: '1px solid #1e1e32',
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    background: 'linear-gradient(90deg,#0d0d1a 0%,#12102a 100%)',
    flexShrink: 0,
  },
  logoIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    background: 'linear-gradient(135deg,#7c3aed,#4f46e5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 18,
    flexShrink: 0,
  },
  logoText: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 22,
    fontWeight: 700,
    background: 'linear-gradient(90deg,#a78bfa,#818cf8)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    letterSpacing: '-0.5px',
  },
  headerSub: {
    fontSize: 13,
    color: '#6b6b8d',
    marginLeft: 2,
  },

  /* Input area */
  inputSection: {
    padding: '20px 40px 16px',
    borderBottom: '1px solid #1e1e32',
    background: '#0d0d1a',
    flexShrink: 0,
  },
  inputRow: {
    display: 'flex',
    gap: 12,
    alignItems: 'center',
    maxWidth: 860,
  },
  input: {
    flex: 1,
    height: 44,
    background: '#13131f',
    border: '1px solid #2a2a42',
    borderRadius: 10,
    padding: '0 16px',
    color: '#e2e2f0',
    fontSize: 14,
    fontFamily: "'Noto Sans SC', sans-serif",
    outline: 'none',
    transition: 'border-color .2s',
  },
  btn: {
    height: 44,
    padding: '0 28px',
    borderRadius: 10,
    border: 'none',
    cursor: 'pointer',
    fontFamily: "'Space Mono', monospace",
    fontWeight: 700,
    fontSize: 13,
    background: 'linear-gradient(135deg,#7c3aed,#4f46e5)',
    color: '#fff',
    whiteSpace: 'nowrap',
    transition: 'opacity .2s, transform .1s',
    flexShrink: 0,
  },
  btnDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
    transform: 'none',
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
    fontSize: 13,
    minHeight: 20,
  },
  spinner: {
    width: 14,
    height: 14,
    border: '2px solid #3730a3',
    borderTopColor: '#818cf8',
    borderRadius: '50%',
    animation: 'spin .7s linear infinite',
    flexShrink: 0,
  },
  checkCircle: {
    width: 16,
    height: 16,
    borderRadius: '50%',
    background: '#16a34a',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },

  /* Empty state */
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    padding: 40,
    color: '#3f3f5a',
    overflow: 'hidden',
    position: 'relative', // allows canvas + elements to layer correctly
  },
  emptyIcon: {
    fontSize: 56,
    marginBottom: 4,
  },
  emptyTitle: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 18,
    color: '#5a5a7a',
  },
  emptyHints: {
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap',
    justifyContent: 'center',
    marginTop: 8,
  },
  emptyHint: {
    background: '#13131f',
    border: '1px solid #1e1e32',
    borderRadius: 8,
    padding: '6px 14px',
    fontSize: 12,
    color: '#4a4a6a',
  },

  /* Main content — fills remaining viewport height exactly */
  main: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
    animation: 'fadeIn .4s ease',
    minHeight: 0,
  },

  /* Left column — scrollable so cards stay reachable after fullscreen */
  leftCol: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    borderRight: '1px solid #1e1e32',
    minWidth: 0,
    overflowY: 'auto',
  },

  /* Atmospheric backdrop that sits behind the player */
  playerGlowWrap: {
    flexShrink: 0,
    padding: '14px 14px 0',
    background: 'radial-gradient(ellipse 110% 170% at 50% -10%, rgba(109,40,217,0.22) 0%, rgba(79,70,229,0.09) 38%, #0a0a0f 65%)',
  },

  /* Sticky player area — sits inside playerGlowWrap */
  playerWrapper: {
    position: 'relative',
    width: '100%',
    aspectRatio: '16/9',
    background: '#000',
    borderRadius: 10,
    overflow: 'hidden',
    border: '1px solid rgba(124,58,237,0.24)',
    boxShadow: '0 0 48px rgba(124,58,237,0.22), 0 8px 36px rgba(0,0,0,0.75)',
  },
  playerIframe: {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    border: 'none',
  },

  /* Subtitle overlay inside player */
  subtitleOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: '10px 16px 14px',
    background: 'linear-gradient(transparent, rgba(0,0,0,.82))',
    textAlign: 'center',
    pointerEvents: 'none',
    zIndex: 2,
  },
  subEn: {
    color: '#ffffff',
    fontSize: 21,
    textShadow: '0 1px 4px rgba(0,0,0,.9)',
    lineHeight: 1.5,
  },
  subZh: {
    color: '#fde047',
    fontSize: 23,
    fontWeight: 500,
    textShadow: '0 1px 4px rgba(0,0,0,.9)',
    marginTop: 2,
    lineHeight: 1.5,
  },

  /* Cinema Mode button row — sits BELOW playerWrapper, outside iframe */
  cinemaBtnRow: {
    display: 'flex',
    justifyContent: 'flex-end',
    padding: '6px 12px',
    background: '#0d0d1a',
    borderBottom: '1px solid #1e1e32',
    flexShrink: 0,
  },
  cinemaBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 14px',
    background: '#1e1e32',
    border: '1px solid #3a3a5a',
    borderRadius: 6,
    color: '#a78bfa',
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    transition: 'background .15s, color .15s',
    letterSpacing: 0.3,
  },

  /* Knowledge cards area — parent (leftCol) handles scrolling */
  cardsArea: {
    padding: '20px 28px 28px',
    display: 'flex',
    flexDirection: 'column',
    gap: 18,
  },

  /* Right column — fixed width, full height, independent scroll */
  rightCol: {
    width: 320,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: '#0a0a0f',
  },
  timelineHeader: {
    padding: '12px 16px 8px',
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    color: '#4a4a6a',
    letterSpacing: 1,
    textTransform: 'uppercase',
    flexShrink: 0,
    borderBottom: '1px solid #1a1a2e',
  },
  /* The scroll container — fills all remaining height in rightCol */
  timelineScroll: {
    flex: 1,
    overflowY: 'scroll',
    minHeight: 0,
  },
  timelineItem: (active) => ({
    display: 'flex',
    gap: 8,
    padding: '5px 16px',
    cursor: 'pointer',
    background: active ? 'rgba(124,58,237,.07)' : 'transparent',
    transition: 'background .15s',
    position: 'relative',
    zIndex: 1,
    alignItems: 'flex-start',
  }),

  /* Fixed-width column that keeps dots centred on the track line */
  dotWrap: {
    width: 16,
    flexShrink: 0,
    display: 'flex',
    justifyContent: 'center',
    paddingTop: 4,
    position: 'relative',
    zIndex: 2,
  },

  /* Dot colour/size changes with position relative to active subtitle */
  timelineDot: (state) => ({
    width:  state === 'active' ? 12 : state === 'past' ? 8 : 7,
    height: state === 'active' ? 12 : state === 'past' ? 8 : 7,
    borderRadius: '50%',
    flexShrink: 0,
    transition: 'all .3s ease',
    background:
      state === 'active' ? 'radial-gradient(circle, #c4b5fd 10%, #7c3aed 80%)'
      : state === 'past'  ? '#14b8a6'
      :                     '#252538',
    border: state === 'active' ? '1.5px solid rgba(196,181,253,.7)' : 'none',
  }),

  timelineTime: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    color: '#4a4a6a',
    paddingTop: 2,
    flexShrink: 0,
    width: 38,
  },
  timelineTexts: {
    flex: 1,
    minWidth: 0,
  },
  timelineEn: (active) => ({
    fontSize: 12,
    color: active ? '#a5b4fc' : '#5a5a7a',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  }),
  timelineZh: (active) => ({
    fontSize: 13,
    color: active ? '#e2e2f0' : '#7a7a9a',
    marginTop: 1,
  }),

  /* Knowledge cards */
  card: {
    background: '#13131f',
    border: '1px solid #1e1e32',
    borderRadius: 14,
    padding: '18px 20px',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 14,
  },
  cardIcon: { fontSize: 18 },
  cardTitle: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 13,
    fontWeight: 700,
    color: '#a78bfa',
    letterSpacing: 0.3,
  },
  themeText: {
    fontSize: 16,
    fontWeight: 700,
    color: '#e2e2f0',
    lineHeight: 1.5,
  },
  listItem: {
    display: 'flex',
    gap: 10,
    padding: '6px 0',
    borderBottom: '1px solid #1a1a2e',
    fontSize: 14,
    color: '#c4c4da',
    lineHeight: 1.6,
    alignItems: 'flex-start',
  },
  bullet: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#7c3aed',
    flexShrink: 0,
    marginTop: 8,
  },

  /* Export button */
  exportBtn: {
    width: '100%',
    height: 44,
    background: 'linear-gradient(135deg,#7c3aed,#4f46e5)',
    border: 'none',
    borderRadius: 10,
    color: '#fff',
    fontFamily: "'Space Mono', monospace",
    fontWeight: 700,
    fontSize: 13,
    cursor: 'pointer',
    transition: 'opacity .2s',
    marginTop: 4,
    flexShrink: 0,
  },

  /* Error */
  errorBox: {
    margin: '0 40px',
    padding: '12px 16px',
    background: 'rgba(220,38,38,.12)',
    border: '1px solid rgba(220,38,38,.3)',
    borderRadius: 8,
    color: '#fca5a5',
    fontSize: 13,
    flexShrink: 0,
  },
}

/* ─────────────────────────────────────────────
   Helpers
───────────────────────────────────────────── */
function formatTime(secs) {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function exportNotes(analysis, videoId, videoUrl) {
  const now = new Date()
  const dateStr = now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\//g, '-')
  const dateTimeStr = now.toLocaleString('zh-CN')
  const youtubeLink = videoUrl || `https://www.youtube.com/watch?v=${videoId}`

  const lines = [
    `# 📹 视频笔记`,
    ``,
    `**视频链接：** [${youtubeLink}](${youtubeLink})`,
    `**生成时间：** ${dateTimeStr}`,
    ``,
    `---`,
    ``,
    `## 🎯 核心主题`,
    ``,
    analysis.theme || '',
    ``,
    `## 🔑 关键知识点`,
    ``,
    ...(analysis.keyPoints || []).map((k) => `- ${k}`),
    ``,
    `## 💡 可行动的洞察`,
    ``,
    ...(analysis.insights || []).map((i) => `- ${i}`),
    ``,
    `## 📚 延伸阅读建议`,
    ``,
    ...(analysis.further || []).map((f) => `- ${f}`),
    ``,
    `---`,
    ``,
    `*由 YouLearn 自动生成*`,
  ]

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = `youlearn_笔记_${videoId}_${dateStr}.md`
  a.click()
  URL.revokeObjectURL(blobUrl)
}

/* ─────────────────────────────────────────────
   Welcome screen — particle canvas
───────────────────────────────────────────── */
function WelcomeCanvas() {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    let animId
    const ctx = canvas.getContext('2d')
    const pts = []

    const init = () => {
      canvas.width  = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
      pts.length = 0
      for (let i = 0; i < 60; i++) {
        pts.push({
          x: Math.random() * canvas.width,
          y: Math.random() * canvas.height,
          r: Math.random() * 1.4 + 0.3,
          vx: (Math.random() - .5) * .32,
          vy: (Math.random() - .5) * .32,
          hue: Math.random() > .55 ? 174 : 262,
          a: Math.random() * .38 + .12,
        })
      }
    }

    const tick = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      pts.forEach(p => {
        p.x = (p.x + p.vx + canvas.width)  % canvas.width
        p.y = (p.y + p.vy + canvas.height) % canvas.height
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `hsla(${p.hue},65%,72%,${p.a})`
        ctx.fill()
      })
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y
          const d = Math.sqrt(dx * dx + dy * dy)
          if (d < 90) {
            ctx.beginPath()
            ctx.moveTo(pts[i].x, pts[i].y)
            ctx.lineTo(pts[j].x, pts[j].y)
            ctx.strokeStyle = `rgba(124,58,237,${(1 - d / 90) * .2})`
            ctx.lineWidth = .5
            ctx.stroke()
          }
        }
      }
      animId = requestAnimationFrame(tick)
    }

    const ro = new ResizeObserver(init)
    ro.observe(canvas)
    init()
    tick()
    return () => { cancelAnimationFrame(animId); ro.disconnect() }
  }, [])

  return (
    <canvas
      ref={ref}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  )
}

/* ─────────────────────────────────────────────
   Welcome screen — alien SVG figure
───────────────────────────────────────────── */
function AlienFigure() {
  return (
    <svg
      viewBox="0 0 200 295"
      className="alien-svg"
      style={{ width: 190, height: 278, flexShrink: 0, zIndex: 1 }}
    >
      <defs>
        <radialGradient id="alien-hg" cx="50%" cy="32%" r="55%">
          <stop offset="0%"   stopColor="rgba(196,181,253,0.2)" />
          <stop offset="100%" stopColor="rgba(79,70,229,0.03)" />
        </radialGradient>
        <radialGradient id="alien-eg" cx="38%" cy="32%" r="52%">
          <stop offset="0%"   stopColor="#e9d5ff" />
          <stop offset="55%"  stopColor="#7c3aed" />
          <stop offset="100%" stopColor="#3b0764" />
        </radialGradient>
        <filter id="alien-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b" />
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      {/* ── Horns ── */}
      <path d="M 72 60 L 56 4  L 86 54" fill="rgba(220,212,255,.9)" stroke="rgba(167,139,250,.35)" strokeWidth=".7"/>
      <path d="M 128 60 L 144 4 L 114 54" fill="rgba(220,212,255,.9)" stroke="rgba(167,139,250,.35)" strokeWidth=".7"/>
      {/* Horn inner highlight */}
      <path d="M 72 60 L 66 28 L 78 57" fill="rgba(255,255,255,.22)" />
      <path d="M 128 60 L 134 28 L 122 57" fill="rgba(255,255,255,.22)" />

      {/* ── Head outer glass ── */}
      <ellipse cx="100" cy="135" rx="78" ry="96"
        fill="url(#alien-hg)" stroke="rgba(167,139,250,.3)" strokeWidth="1.5"/>
      {/* Head inner highlight (top-left catch-light) */}
      <ellipse cx="78" cy="100" rx="26" ry="30"
        fill="rgba(255,255,255,.04)" stroke="rgba(255,255,255,.07)" strokeWidth=".8"/>

      {/* ── Circuit veins (breathing) ── */}
      <g className="alien-circ" filter="url(#alien-glow)"
        stroke="rgba(167,139,250,.6)" strokeWidth=".9" fill="none">
        <path d="M 58 118 H 74 L 79 108 H 100 L 105 118 H 122 L 127 108 H 144"/>
        <path d="M 62 150 H 76 L 81 140 H 100 L 107 150 H 124 L 129 140 H 142"/>
        <line x1="74"  y1="108" x2="74"  y2="150"/>
        <line x1="126" y1="108" x2="126" y2="150"/>
        {/* Circuit nodes */}
        <circle cx="100" cy="118" r="3.5" fill="rgba(124,58,237,.75)" stroke="rgba(167,139,250,.7)" strokeWidth=".6"/>
        <circle cx="74"  cy="128" r="2"   fill="rgba(20,184,166,.9)"/>
        <circle cx="126" cy="128" r="2"   fill="rgba(20,184,166,.9)"/>
        <circle cx="100" cy="140" r="2"   fill="rgba(167,139,250,.7)"/>
        <circle cx="62"  cy="128" r="1.5" fill="rgba(124,58,237,.5)"/>
        <circle cx="138" cy="128" r="1.5" fill="rgba(124,58,237,.5)"/>
      </g>

      {/* ── Scan line (sweeps downward) ── */}
      <clipPath id="alien-clip">
        <ellipse cx="100" cy="135" rx="77" ry="95"/>
      </clipPath>
      <rect x="23" y="60" width="154" height="3" rx="1.5"
        fill="rgba(167,139,250,.25)" className="alien-scan"
        clipPath="url(#alien-clip)"/>

      {/* ── Eyes ── */}
      <g className="alien-eyes" filter="url(#alien-glow)">
        <ellipse cx="78"  cy="140" rx="17" ry="13" fill="url(#alien-eg)"/>
        <ellipse cx="122" cy="140" rx="17" ry="13" fill="url(#alien-eg)"/>
      </g>
      {/* Pupils */}
      <ellipse cx="78"  cy="140" rx="8"   ry="7.5" fill="rgba(15,5,35,.94)"/>
      <ellipse cx="122" cy="140" rx="8"   ry="7.5" fill="rgba(15,5,35,.94)"/>
      {/* Reflections */}
      <ellipse cx="74"  cy="135" rx="3.2" ry="2.6" fill="rgba(255,255,255,.48)"/>
      <ellipse cx="118" cy="135" rx="3.2" ry="2.6" fill="rgba(255,255,255,.48)"/>

      {/* ── Nose / face ── */}
      <path d="M 94 162 Q 100 172 106 162" fill="rgba(196,181,253,.12)"
        stroke="rgba(167,139,250,.22)" strokeWidth=".8"/>
      {/* Mouth */}
      <path d="M 86 184 Q 100 192 114 184" fill="none"
        stroke="rgba(167,139,250,.28)" strokeWidth="1"/>

      {/* ── Jaw line ── */}
      <path d="M 42 178 Q 50 218 100 228 Q 150 218 158 178"
        fill="rgba(79,70,229,.04)" stroke="rgba(124,58,237,.14)" strokeWidth=".8"/>

      {/* ── Neck ── */}
      <rect x="84" y="225" width="32" height="40" rx="3"
        fill="rgba(109,40,217,.1)" stroke="rgba(124,58,237,.32)" strokeWidth=".9"/>
      <g className="alien-circ" stroke="rgba(124,58,237,.5)" strokeWidth=".55" fill="none">
        <line x1="90" y1="231" x2="90" y2="260"/>
        <line x1="96" y1="231" x2="96" y2="260"/>
        <line x1="100" y1="231" x2="100" y2="260"/>
        <line x1="104" y1="231" x2="104" y2="260"/>
        <line x1="110" y1="231" x2="110" y2="260"/>
        <line x1="87"  y1="241" x2="113" y2="241"/>
        <line x1="87"  y1="252" x2="113" y2="252"/>
        <rect x="97" y="244" width="6" height="5" fill="rgba(20,184,166,.38)"/>
      </g>

      {/* ── Shoulders ── */}
      <path d="M 26 263 Q 52 250 84 262 L 84 287 Q 52 295 26 280 Z"
        fill="rgba(109,40,217,.08)" stroke="rgba(124,58,237,.22)" strokeWidth="1"/>
      <path d="M 174 263 Q 148 250 116 262 L 116 287 Q 148 295 174 280 Z"
        fill="rgba(109,40,217,.08)" stroke="rgba(124,58,237,.22)" strokeWidth="1"/>
      {/* Shoulder circuits */}
      <g stroke="rgba(20,184,166,.42)" strokeWidth=".55" fill="none">
        <line x1="40" y1="269" x2="74" y2="269"/><line x1="44" y1="276" x2="68" y2="276"/>
        <circle cx="50" cy="269" r="2" fill="rgba(20,184,166,.65)"/>
        <circle cx="63" cy="276" r="2" fill="rgba(124,58,237,.6)"/>
      </g>
      <g stroke="rgba(20,184,166,.42)" strokeWidth=".55" fill="none">
        <line x1="160" y1="269" x2="126" y2="269"/><line x1="156" y1="276" x2="132" y2="276"/>
        <circle cx="150" cy="269" r="2" fill="rgba(20,184,166,.65)"/>
        <circle cx="137" cy="276" r="2" fill="rgba(124,58,237,.6)"/>
      </g>
    </svg>
  )
}

/* ─────────────────────────────────────────────
   Components
───────────────────────────────────────────── */
function KnowledgeCard({ icon, title, children }) {
  return (
    <div style={S.card}>
      <div style={S.cardHeader}>
        <span style={S.cardIcon}>{icon}</span>
        <span style={S.cardTitle}>{title}</span>
      </div>
      {children}
    </div>
  )
}

function BulletList({ items }) {
  return (
    <div>
      {(items || []).map((item, i) => (
        <div key={i} style={S.listItem}>
          <div style={S.bullet} />
          <span>{item}</span>
        </div>
      ))}
    </div>
  )
}

/* ─────────────────────────────────────────────
   Main App
───────────────────────────────────────────── */
export default function App() {
  const [url, setUrl] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | done | error
  const [errorMsg, setErrorMsg] = useState('')
  const [result, setResult] = useState(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [progress, setProgress] = useState(0)
  const [cinemaMode, setCinemaMode] = useState(false)
  // Fix 4: track whether we're in native fullscreen
  const [isFullscreen, setIsFullscreen] = useState(false)

  const playerRef = useRef(null)
  const pollRef = useRef(null)
  const progressRef = useRef(null)
  const timelineScrollRef = useRef(null)
  const activeItemRef = useRef(null)

  /* ── YouTube IFrame API ── */
  useEffect(() => {
    if (!window.YT) {
      const tag = document.createElement('script')
      tag.src = 'https://www.youtube.com/iframe_api'
      document.head.appendChild(tag)
    }
  }, [])

  /* ── Init player when videoId is ready ── */
  useEffect(() => {
    if (!result) return

    const initPlayer = () => {
      if (playerRef.current) {
        playerRef.current.destroy()
        playerRef.current = null
      }
      playerRef.current = new window.YT.Player('yt-player', {
        videoId: result.videoId,
        playerVars: { rel: 0, modestbranding: 1 },
        events: { onReady: startPolling },
      })
    }

    if (window.YT && window.YT.Player) {
      initPlayer()
    } else {
      window.onYouTubeIframeAPIReady = initPlayer
    }

    return () => {
      stopPolling()
      if (playerRef.current) {
        playerRef.current.destroy()
        playerRef.current = null
      }
    }
  }, [result?.videoId])

  /* ── Polling ── */
  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(() => {
      if (playerRef.current?.getCurrentTime) {
        setCurrentTime(playerRef.current.getCurrentTime())
      }
    }, 500)
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  /* ── Simulated progress during loading ── */
  useEffect(() => {
    if (status === 'loading') {
      setProgress(1)
      const tick = () => {
        setProgress((prev) => {
          if (prev >= 90) return prev
          const remaining = 90 - prev
          const step = Math.random() * remaining * 0.08 + 0.3
          return Math.min(90, prev + step)
        })
        progressRef.current = setTimeout(tick, 400 + Math.random() * 800)
      }
      progressRef.current = setTimeout(tick, 500)
    } else {
      clearTimeout(progressRef.current)
      progressRef.current = null
      if (status === 'done' || status === 'error') {
        setProgress(100)
      }
    }
    return () => {
      clearTimeout(progressRef.current)
      progressRef.current = null
    }
  }, [status])

  /* ── Find active subtitle index ── */
  useEffect(() => {
    if (!result?.subtitles?.length) return
    const idx = result.subtitles.findLastIndex((s) => currentTime >= s.start)
    setActiveIdx(idx)
  }, [currentTime, result?.subtitles])

  /* ── Fix 2: Auto-scroll timeline — only scrolls the inner container ── */
  useEffect(() => {
    if (activeItemRef.current && timelineScrollRef.current) {
      const container = timelineScrollRef.current
      const item = activeItemRef.current
      const containerTop = container.scrollTop
      const containerBottom = containerTop + container.clientHeight
      const itemTop = item.offsetTop
      const itemBottom = itemTop + item.offsetHeight
      // Only scroll if item is outside visible area, keeping it centred
      if (itemTop < containerTop || itemBottom > containerBottom) {
        container.scrollTo({
          top: itemTop - container.clientHeight / 2 + item.offsetHeight / 2,
          behavior: 'smooth',
        })
      }
    }
  }, [activeIdx])

  /* ── Fullscreen subtitle — body-level fixed overlay (standard + webkit) ── */
  useEffect(() => {
    const handleFullscreenChange = () => {
      // document.webkitFullscreenElement covers Safari / iOS
      setIsFullscreen(!!(document.fullscreenElement || document.webkitFullscreenElement))
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange)
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
      document.removeEventListener('webkitfullscreenchange', handleFullscreenChange)
    }
  }, [])

  /* ── Seek on timeline click ── */
  const seekTo = (start) => {
    if (playerRef.current?.seekTo) {
      playerRef.current.seekTo(start, true)
    }
  }

  /* ── Analyze ── */
  const handleAnalyze = async () => {
    if (!url.trim() || status === 'loading') return
    setStatus('loading')
    setErrorMsg('')
    setResult(null)
    setCurrentTime(0)
    setActiveIdx(-1)
    setCinemaMode(false)

    try {
      const API_URL = import.meta.env.VITE_API_URL || ''
      const res = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      setResult(data)
      setStatus('done')
    } catch (e) {
      setErrorMsg(e.message)
      setStatus('error')
    }
  }

  const activeSub = activeIdx >= 0 ? result?.subtitles?.[activeIdx] : null

  /* ─────── Render ─────── */
  return (
    <div style={S.app}>

      {/* ── Header ── */}
      <header style={S.header}>
        <div style={S.logoIcon}>▶</div>
        <div>
          <div style={S.logoText}>YouLearn</div>
          <div style={S.headerSub}>将任意 YouTube 视频转化为结构化知识</div>
        </div>
      </header>

      {/* ── Input area ── */}
      <div style={S.inputSection}>
        <div style={S.inputRow}>
          <input
            style={S.input}
            placeholder="粘贴 YouTube 链接，例如 https://www.youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
            onFocus={(e) => (e.target.style.borderColor = '#7c3aed')}
            onBlur={(e) => (e.target.style.borderColor = '#2a2a42')}
          />
          <button
            style={{ ...S.btn, ...(status === 'loading' ? S.btnDisabled : {}) }}
            onClick={handleAnalyze}
            disabled={status === 'loading'}
            onMouseEnter={(e) => { if (status !== 'loading') e.target.style.opacity = '.85' }}
            onMouseLeave={(e) => (e.target.style.opacity = '1')}
          >
            开始分析
          </button>
        </div>

        {/* Status indicator */}
        <div style={S.statusRow}>
          {status === 'loading' && (
            <>
              <div style={S.spinner} />
              <span style={{ color: '#818cf8', fontWeight: 700 }}>
                {Math.floor(progress)}%
              </span>
              <span style={{ color: '#818cf8' }}>分析中，请稍候...</span>
            </>
          )}
          {status === 'done' && (
            <>
              <div style={S.checkCircle}>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2 5l2.5 2.5L8 3" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <span style={{ color: '#4ade80' }}>✓ 分析完成 Completed</span>
            </>
          )}
        </div>
      </div>

      {/* ── Error ── */}
      {status === 'error' && (
        <div style={S.errorBox}>⚠ {errorMsg}</div>
      )}

      {/* ── Empty state — animated alien welcome ── */}
      {status === 'idle' && (
        <div style={S.empty}>
          {/* Particle field background */}
          <WelcomeCanvas />

          {/* Alien figure */}
          <AlienFigure />

          {/* Text */}
          <div style={{ ...S.emptyTitle, zIndex: 1, marginTop: 8 }}>
            粘贴一个 YouTube 链接开始学习
          </div>
          <div style={{ color: '#4a4a6a', fontSize: 13, zIndex: 1, textAlign: 'center', maxWidth: 420 }}>
            YouLearn 将自动提取字幕、翻译并生成结构化知识框架
          </div>
          <div style={{ ...S.emptyHints, zIndex: 1 }}>
            {['教学讲座', '技术分享', 'TED 演讲', '纪录片', '新闻报道'].map((t) => (
              <span key={t} style={S.emptyHint}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* ── Main content ── */}
      {status === 'done' && result && (
        <div style={S.main}>

          {/* Left column */}
          <div style={{
            ...S.leftCol,
            borderRight: cinemaMode ? 'none' : '1px solid #1e1e32',
          }}>

            {/* Ambient glow backdrop + video player */}
            <div style={cinemaMode
              ? { ...S.playerGlowWrap, padding: '10px 0 0' }
              : S.playerGlowWrap
            }>
              <div style={S.playerWrapper}>
                <div id="yt-player" style={S.playerIframe} />
                {/* Normal (non-fullscreen) subtitle overlay */}
                {!isFullscreen && activeSub && (
                  <div style={S.subtitleOverlay}>
                    {activeSub.en && <div style={S.subEn}>{activeSub.en}</div>}
                    {activeSub.zh && <div style={S.subZh}>{activeSub.zh}</div>}
                  </div>
                )}
              </div>
            </div>

            {/* Fix 3: Cinema Mode button — sits BELOW playerWrapper, outside iframe */}
            <div style={S.cinemaBtnRow}>
              <button
                style={S.cinemaBtn}
                onClick={() => setCinemaMode((m) => !m)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = '#2e2e4a'
                  e.currentTarget.style.color = '#c4b5fd'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = '#1e1e32'
                  e.currentTarget.style.color = '#a78bfa'
                }}
              >
                {cinemaMode ? '⊠ Exit Cinema' : '⛶ Cinema Mode'}
              </button>
            </div>

            {/* Scrollable knowledge cards */}
            <div style={S.cardsArea}>

              <KnowledgeCard icon="🎯" title="核心主题">
                <div style={S.themeText}>{result.analysis.theme}</div>
              </KnowledgeCard>

              <KnowledgeCard icon="🔑" title="关键知识点">
                <BulletList items={result.analysis.keyPoints} />
              </KnowledgeCard>

              <KnowledgeCard icon="💡" title="可行动的洞察">
                <BulletList items={result.analysis.insights} />
              </KnowledgeCard>

              <KnowledgeCard icon="📚" title="延伸阅读建议">
                <BulletList items={result.analysis.further} />
              </KnowledgeCard>

              <button
                style={S.exportBtn}
                onClick={() => exportNotes(result.analysis, result.videoId, url)}
                onMouseEnter={(e) => (e.target.style.opacity = '.85')}
                onMouseLeave={(e) => (e.target.style.opacity = '1')}
              >
                📥 导出笔记（Markdown）
              </button>

            </div>
          </div>

          {/* Right column: fixed-height independent scroll timeline */}
          {!cinemaMode && (
            <div style={S.rightCol}>
              <div style={S.timelineHeader}>字幕时间轴</div>
              {/* Metro-line timeline — only this div scrolls */}
              <div style={S.timelineScroll} ref={timelineScrollRef} className="timeline-scroll">
                <div className="timeline-track">
                  {result.subtitles.map((s, i) => {
                    const active = i === activeIdx
                    const dotState = active ? 'active' : (i < activeIdx ? 'past' : 'future')
                    return (
                      <div
                        key={i}
                        ref={active ? activeItemRef : null}
                        style={S.timelineItem(active)}
                        onClick={() => seekTo(s.start)}
                      >
                        {/* Metro node */}
                        <div style={S.dotWrap}>
                          <div
                            style={S.timelineDot(dotState)}
                            className={active ? 'dot-active' : ''}
                          />
                        </div>
                        <span style={S.timelineTime}>{formatTime(s.start)}</span>
                        <div style={S.timelineTexts}>
                          {s.en && <div style={S.timelineEn(active)}>{s.en}</div>}
                          {s.zh && <div style={S.timelineZh(active)}>{s.zh}</div>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

        </div>
      )}

      {/* Fix 4: Body-level fullscreen subtitle overlay — position:fixed, z-index:99999 */}
      {isFullscreen && activeSub && (
        <div style={{
          position: 'fixed',
          bottom: 60,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 99999,
          textAlign: 'center',
          padding: '10px 20px 14px',
          background: 'linear-gradient(transparent, rgba(0,0,0,.85))',
          pointerEvents: 'none',
          width: '80%',
          maxWidth: 900,
        }}>
          {activeSub.en && (
            <div style={S.subEn}>{activeSub.en}</div>
          )}
          {activeSub.zh && (
            <div style={{ ...S.subZh, fontSize: 27 }}>{activeSub.zh}</div>
          )}
        </div>
      )}

    </div>
  )
}
