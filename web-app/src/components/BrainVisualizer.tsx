import { useEffect, useRef } from 'react';


export function BrainVisualizer({ isActive }: { isActive: boolean }) {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let animationFrameId: number;
        let particles: { x: number; y: number; vx: number; vy: number; life: number }[] = [];

        const resize = () => {
            canvas.width = canvas.parentElement?.clientWidth || 300;
            canvas.height = 200;
        };
        resize();
        window.addEventListener('resize', resize);

        const createParticle = () => {
            return {
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                vx: (Math.random() - 0.5) * 2,
                vy: (Math.random() - 0.5) * 2,
                life: 1.0,
            };
        };

        // Initialize some particles
        for (let i = 0; i < 50; i++) {
            particles.push(createParticle());
        }

        const render = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Update and draw particles
            particles.forEach((p, i) => {
                p.x += p.vx * (isActive ? 2 : 0.5);
                p.y += p.vy * (isActive ? 2 : 0.5);
                p.life -= 0.01;

                // Bounce off walls
                if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
                if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

                // Reset if dead
                if (p.life <= 0) {
                    particles[i] = createParticle();
                }

                ctx.beginPath();
                ctx.arc(p.x, p.y, isActive ? 3 : 2, 0, Math.PI * 2);
                ctx.fillStyle = isActive
                    ? `rgba(56, 189, 248, ${p.life})` // Blue/Cyan when active
                    : `rgba(148, 163, 184, ${p.life * 0.5})`; // Muted when idle
                ctx.fill();

                // Connections
                particles.forEach((p2, j) => {
                    if (i === j) return;
                    const dx = p.x - p2.x;
                    const dy = p.y - p2.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 60) {
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.strokeStyle = isActive
                            ? `rgba(56, 189, 248, ${0.2 * (1 - dist / 60)})`
                            : `rgba(148, 163, 184, ${0.1 * (1 - dist / 60)})`;
                        ctx.stroke();
                    }
                });
            });

            animationFrameId = requestAnimationFrame(render);
        };

        render();

        return () => {
            window.removeEventListener('resize', resize);
            cancelAnimationFrame(animationFrameId);
        };
    }, [isActive]);

    return <canvas ref={canvasRef} className="w-full h-[200px] rounded-md bg-slate-950/50 border border-slate-800" />;
}
