import { useEffect, useRef } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  energy: number
}

export function BrainVisualizer({ isActive }: { isActive: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    const context = canvas.getContext('2d')
    if (!context) {
      return
    }

    let frame = 0
    let animationFrameId = 0
    let particles: Particle[] = []

    const resize = () => {
      canvas.width = canvas.parentElement?.clientWidth || 320
      canvas.height = 220
    }

    const createParticle = (): Particle => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 1.2,
      vy: (Math.random() - 0.5) * 1.2,
      energy: 0.4 + Math.random() * 0.6,
    })

    resize()
    particles = Array.from({ length: 42 }, createParticle)
    window.addEventListener('resize', resize)

    const render = () => {
      frame += 1
      context.clearRect(0, 0, canvas.width, canvas.height)

      const gradient = context.createLinearGradient(0, 0, canvas.width, canvas.height)
      gradient.addColorStop(0, 'rgba(15, 23, 42, 0.25)')
      gradient.addColorStop(1, 'rgba(2, 6, 23, 0.8)')
      context.fillStyle = gradient
      context.fillRect(0, 0, canvas.width, canvas.height)

      particles.forEach((particle, index) => {
        const speed = isActive ? 1.8 : 0.45
        particle.x += particle.vx * speed
        particle.y += particle.vy * speed

        if (particle.x <= 0 || particle.x >= canvas.width) {
          particle.vx *= -1
        }
        if (particle.y <= 0 || particle.y >= canvas.height) {
          particle.vy *= -1
        }

        const pulse = isActive ? 2 + Math.sin((frame + index) / 12) * 0.8 : 1.8
        const alpha = isActive ? particle.energy : particle.energy * 0.35

        context.beginPath()
        context.arc(particle.x, particle.y, pulse, 0, Math.PI * 2)
        context.fillStyle = isActive
          ? `rgba(34, 211, 238, ${alpha})`
          : `rgba(148, 163, 184, ${alpha})`
        context.fill()

        particles.forEach((neighbor, neighborIndex) => {
          if (neighborIndex <= index) {
            return
          }

          const dx = particle.x - neighbor.x
          const dy = particle.y - neighbor.y
          const distance = Math.sqrt(dx * dx + dy * dy)
          const threshold = isActive ? 88 : 64
          if (distance > threshold) {
            return
          }

          context.beginPath()
          context.moveTo(particle.x, particle.y)
          context.lineTo(neighbor.x, neighbor.y)
          context.strokeStyle = isActive
            ? `rgba(245, 158, 11, ${0.18 * (1 - distance / threshold)})`
            : `rgba(148, 163, 184, ${0.08 * (1 - distance / threshold)})`
          context.lineWidth = isActive ? 1.2 : 0.8
          context.stroke()
        })
      })

      animationFrameId = requestAnimationFrame(render)
    }

    render()

    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(animationFrameId)
    }
  }, [isActive])

  return (
    <canvas
      ref={canvasRef}
      className="h-[220px] w-full rounded-[28px] border border-white/10 bg-slate-950/70"
    />
  )
}
