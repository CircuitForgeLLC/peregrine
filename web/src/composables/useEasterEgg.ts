import { onMounted, onUnmounted } from 'vue'

const KONAMI    = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a']
const KONAMI_AB = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','a','b']

export function useKeySequence(sequence: string[], onActivate: () => void) {
  let pos = 0

  function handler(e: KeyboardEvent) {
    if (e.key === sequence[pos]) {
      pos++
      if (pos === sequence.length) {
        pos = 0
        onActivate()
      }
    } else {
      pos = 0
    }
  }

  onMounted(()   => window.addEventListener('keydown', handler))
  onUnmounted(() => window.removeEventListener('keydown', handler))
}

export function useKonamiCode(onActivate: () => void) {
  useKeySequence(KONAMI, onActivate)
  useKeySequence(KONAMI_AB, onActivate)
}

export function useHackerMode() {
  function toggle() {
    const root = document.documentElement
    if (root.dataset.theme === 'hacker') {
      delete root.dataset.theme
      localStorage.removeItem('cf-hacker-mode')
    } else {
      root.dataset.theme = 'hacker'
      localStorage.setItem('cf-hacker-mode', 'true')
    }
  }

  function restore() {
    if (localStorage.getItem('cf-hacker-mode') === 'true') {
      document.documentElement.dataset.theme = 'hacker'
    }
  }

  return { toggle, restore }
}

/** Fire a confetti burst from a given x,y position. Pure canvas, no dependencies. */
export function fireConfetti(originX = window.innerWidth / 2, originY = window.innerHeight / 2) {
  if (typeof requestAnimationFrame === 'undefined') return

  const canvas = document.createElement('canvas')
  canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:9999;'
  canvas.width  = window.innerWidth
  canvas.height = window.innerHeight
  document.body.appendChild(canvas)
  const ctx = canvas.getContext('2d')!

  const COLORS = ['#2d5a27','#c4732a','#5A9DBF','#D4854A','#FFC107','#4CAF50']
  const particles = Array.from({ length: 80 }, () => ({
    x:     originX,
    y:     originY,
    vx:    (Math.random() - 0.5) * 14,
    vy:    (Math.random() - 0.6) * 12,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    size:  5 + Math.random() * 6,
    angle: Math.random() * Math.PI * 2,
    spin:  (Math.random() - 0.5) * 0.3,
    life:  1.0,
  }))

  let raf = 0
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    let alive = false
    for (const p of particles) {
      p.x     += p.vx
      p.y     += p.vy
      p.vy    += 0.35
      p.vx    *= 0.98
      p.angle += p.spin
      p.life  -= 0.016
      if (p.life <= 0) continue
      alive = true
      ctx.save()
      ctx.globalAlpha = p.life
      ctx.fillStyle   = p.color
      ctx.translate(p.x, p.y)
      ctx.rotate(p.angle)
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6)
      ctx.restore()
    }
    if (alive) {
      raf = requestAnimationFrame(draw)
    } else {
      cancelAnimationFrame(raf)
      canvas.remove()
    }
  }
  raf = requestAnimationFrame(draw)
}

/** Enable cursor trail in hacker mode — returns a cleanup function. */
export function useCursorTrail() {
  const DOT_COUNT = 10
  const dots: HTMLElement[] = []
  let positions: { x: number; y: number }[] = []
  let mouseX = 0
  let mouseY = 0
  let raf = 0

  for (let i = 0; i < DOT_COUNT; i++) {
    const dot = document.createElement('div')
    dot.style.cssText = [
      'position:fixed',
      'pointer-events:none',
      'z-index:9998',
      'border-radius:50%',
      'background:var(--color-accent)',
      'transition:opacity 0.1s',
    ].join(';')
    document.body.appendChild(dot)
    dots.push(dot)
  }

  function onMouseMove(e: MouseEvent) {
    mouseX = e.clientX
    mouseY = e.clientY
  }

  function animate() {
    positions.unshift({ x: mouseX, y: mouseY })
    if (positions.length > DOT_COUNT) positions = positions.slice(0, DOT_COUNT)

    dots.forEach((dot, i) => {
      const pos = positions[i]
      if (!pos) { dot.style.opacity = '0'; return }
      const scale = 1 - i / DOT_COUNT
      const size  = Math.round(8 * scale)
      dot.style.left    = `${pos.x - size / 2}px`
      dot.style.top     = `${pos.y - size / 2}px`
      dot.style.width   = `${size}px`
      dot.style.height  = `${size}px`
      dot.style.opacity = `${(1 - i / DOT_COUNT) * 0.7}`
    })
    raf = requestAnimationFrame(animate)
  }

  window.addEventListener('mousemove', onMouseMove)
  raf = requestAnimationFrame(animate)

  return function cleanup() {
    window.removeEventListener('mousemove', onMouseMove)
    cancelAnimationFrame(raf)
    dots.forEach(d => d.remove())
  }
}
